from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from decimal import Decimal
from engine.services.execution_gateway import place_order_through_gateway
from engine.services.backtester import run_backtest
from learning.models import PolicyState
from monitoring.models import OrderAudit
from monitoring.metrics import hash_payload, record_order, update_pnl_metrics, get_metrics
import time
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@api_view(['GET'])
def status(request):
    return Response({'status': 'ok'})


@api_view(['GET'])
def get_balance(request):
    """Obtener balance de Deriv con manejo de rate limiting"""
    try:
        from connectors.deriv_client import DerivClient
        from trading_bot.models import DerivAPIConfig
        
        # Obtener configuraciÃ³n activa (usar only() para evitar campos scope_*)
        api_token = None
        is_demo = False  # Default a REAL (mÃ¡s seguro)
        app_id = '1089'
        
        try:
            # Obtener configuraciÃ³n activa sin filtrar por usuario especÃ­fico
            # Usar only() para evitar campos scope_* que no existen
            config = DerivAPIConfig.objects.filter(is_active=True).only('api_token', 'is_demo', 'app_id').first()
            if config:
                api_token = config.api_token
                is_demo = config.is_demo
                app_id = config.app_id
        except Exception as e:
            print(f"âš ï¸ Error al obtener configuraciÃ³n en get_balance: {e}")
            # Si hay error, intentar obtener de forma alternativa
            try:
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT api_token, is_demo, app_id 
                        FROM trading_bot_derivapiconfig 
                        WHERE is_active = 1 
                        LIMIT 1
                    """)
                    row = cursor.fetchone()
                    if row:
                        api_token = row[0] or ''
                        is_demo = bool(row[1]) if row[1] is not None else False
                        app_id = row[2] or '1089'
            except Exception as e2:
                print(f"âš ï¸ Error al obtener configuraciÃ³n con SQL: {e2}")
                pass  # Usar defaults si no hay configuraciÃ³n
        
        # Reutilizar cliente compartido global para evitar mÃºltiples conexiones
        global _shared_deriv_client_web
        try:
            _shared_deriv_client_web
        except NameError:
            # Crear cliente compartido solo una vez
            _shared_deriv_client_web = DerivClient(api_token=api_token, is_demo=is_demo, app_id=app_id)
        else:
            # Actualizar configuraciÃ³n si cambiÃ³
            if (_shared_deriv_client_web.api_token != api_token or 
                _shared_deriv_client_web.is_demo != is_demo or
                _shared_deriv_client_web.app_id != app_id):
                # Cerrar conexiÃ³n anterior si existe
                try:
                    if _shared_deriv_client_web.ws:
                        _shared_deriv_client_web.ws.close()
                except:
                    pass
                # Crear nuevo cliente con nueva configuraciÃ³n
                _shared_deriv_client_web = DerivClient(api_token=api_token, is_demo=is_demo, app_id=app_id)
        
        client = _shared_deriv_client_web
        balance_info = client.get_balance()
        
        # Verificar si hay error de rate limit pero hay balance en cachÃ©
        if balance_info.get('error_code') == 'RateLimit':
            # Balance estÃ¡ en cachÃ© (Ãºltimo conocido)
            return JsonResponse({
                'success': True,
                'balance': balance_info.get('balance', 0),
                'currency': balance_info.get('currency', 'USD'),
                'account_type': balance_info.get('account_type', 'demo'),
                'cached': True,
                'warning': 'Rate limit alcanzado, mostrando balance en cachÃ©',
                'source': balance_info.get('source', 'cache')
            })
        
        return JsonResponse({
            'success': True,
            'balance': balance_info.get('balance', 0),
            'currency': balance_info.get('currency', 'USD'),
            'account_type': balance_info.get('account_type', 'demo'),
            'cached': False
        })
    except Exception as e:
        # Si hay error, intentar obtener del Ãºltimo trade
        try:
            from monitoring.models import OrderAudit
            last_trade = OrderAudit.objects.filter(
                accepted=True
            ).order_by('-timestamp').first()
            if last_trade and last_trade.response_payload:
                balance_after = last_trade.response_payload.get('balance_after')
                if balance_after:
                    return JsonResponse({
                        'success': True,
                        'balance': float(balance_after),
                        'currency': 'USD',
                        'account_type': 'demo',
                        'cached': True,
                        'source': 'last_trade',
                        'warning': f'Error obteniendo balance: {str(e)}, usando Ãºltimo trade conocido'
                    })
        except:
            pass
        
        return JsonResponse({
            'success': False,
            'error': str(e),
            'balance': 0
        }, status=500)


@api_view(['GET'])
def get_trades(request):
    """Obtener operaciones activas y finalizadas"""
    try:
        from datetime import timedelta
        from django.utils import timezone
        
        # Historial persistente desde la BD (no limitar a 30 minutos)
        # Mostrar las Ãºltimas 200 operaciones, incluyendo finalizadas antiguas
        trades = OrderAudit.objects.all().order_by('-timestamp')[:200]
        
        active = []
        completed = []
        
        for trade in trades:
            # Obtener monto/stake REAL del trade (prioridad al monto final usado)
            amount = None
            
            # 1. Primero intentar desde response_payload['amount'] (monto REAL usado despuÃ©s de ajustes)
            if trade.response_payload:
                amount = trade.response_payload.get('amount')
                if amount:
                    amount = float(amount)
            
            # 2. Si no estÃ¡ en response_payload, usar size (campo directo del modelo)
            if not amount and trade.size:
                amount = float(trade.size)
            
            # 3. Si aÃºn no tenemos monto, intentar desde request_payload
            if not amount and trade.request_payload:
                # Intentar obtener desde position_sizing (monto calculado, puede diferir del real)
                position_sizing = trade.request_payload.get('position_sizing', {})
                if position_sizing:
                    amount = position_sizing.get('risk_amount') or position_sizing.get('amount')
                    if amount:
                        amount = float(amount)
                # Si no estÃ¡ en position_sizing, buscar en el request directamente
                if not amount:
                    amount = trade.request_payload.get('amount') or trade.request_payload.get('stake')
                    if amount:
                        amount = float(amount)
            
            # Si aÃºn no tenemos monto, usar 0.0 (no deberÃ­a pasar)
            if not amount:
                amount = 0.0
            
            # Extraer contract_id del payload si existe
            contract_id = None
            try:
                if trade.response_payload and isinstance(trade.response_payload, dict):
                    contract_id = (
                        trade.response_payload.get('order_id') or
                        trade.response_payload.get('contract_id') or
                        (trade.response_payload.get('buy', {}).get('contract_id') if isinstance(trade.response_payload.get('buy'), dict) else None)
                    )
            except Exception:
                contract_id = None

            # Extraer confianza (0-1) y convertir a porcentaje (0-100)
            confidence_pct = None
            try:
                # Preferir la confianza guardada en position_sizing
                if trade.request_payload and isinstance(trade.request_payload, dict):
                    pos_sizing = trade.request_payload.get('position_sizing') or {}
                    conf_val = pos_sizing.get('confidence')
                    if conf_val is None:
                        # Alternativa: confianza del propio signal (estrategia estadÃ­stica)
                        conf_val = trade.request_payload.get('confidence')
                    if conf_val is not None:
                        confidence_pct = float(conf_val) * 100.0 if float(conf_val) <= 1.0 else float(conf_val)
            except Exception:
                confidence_pct = None

            # Extraer estrategia del request_payload
            strategy_name = None
            try:
                internal_name = trade.request_payload.get('strategy')
                # Fallback heurÃ­stico si 'strategy' no estÃ¡ presente en el payload
                if not internal_name:
                    if 'z_score' in trade.request_payload or 'signal_type' in trade.request_payload:
                        internal_name = 'statistical_hybrid'
                    elif 'ema200' in trade.request_payload or 'recent_high' in trade.request_payload:
                        internal_name = 'ema200_extrema'
                    elif 'force_pct' in trade.request_payload:
                        internal_name = 'tick_based'
                    elif 'fatigue_count' in trade.request_payload or 'momentum_extreme' in trade.request_payload or 'divergence_score' in trade.request_payload:
                        internal_name = 'momentum_reversal'
                # Mapear a nombres cortos y dicientes
                if internal_name == 'statistical_hybrid':
                    strategy_name = 'HÃ­brida'
                elif internal_name == 'ema200_extrema':
                    # Mostramos el periodo si viene configurado en el payload (opcional)
                    strategy_name = 'EMA100'
                elif internal_name == 'tick_based':
                    strategy_name = 'Ticks'
                elif internal_name == 'momentum_reversal':
                    strategy_name = 'ReversiÃ³n'
                else:
                    strategy_name = 'Desconocida'
            except Exception:
                strategy_name = 'Desconocida'
            
            trade_data = {
                'id': trade.id,
                'symbol': trade.symbol,
                'direction': trade.action.upper(),
                'price': float(trade.price) if trade.price else 0.0,
                'timestamp': trade.timestamp.isoformat(),
                'status': trade.status,
                'amount': amount,  # Monto REAL usado en el trade
                'pnl': float(trade.pnl) if trade.pnl else 0.0,  # P&L para operaciones finalizadas
                'contract_id': contract_id,
                'confidence_pct': confidence_pct,
                'strategy': strategy_name
            }
            
            if trade.status == 'pending':
                active.append(trade_data)
            else:
                completed.append(trade_data)
        
        # MÃ‰TRICAS: Operaciones en las Ãºltimas 24 horas
        since_metrics = timezone.now() - timedelta(hours=24)
        recent_trades = OrderAudit.objects.filter(timestamp__gte=since_metrics)
        
        total_trades = recent_trades.count()
        won_trades = recent_trades.filter(status='won').count()
        lost_trades = recent_trades.filter(status='lost').count()
        active_trades = recent_trades.filter(status__in=['pending', 'active']).count()
        
        # P&L total de las Ãºltimas 24 horas
        total_pnl = sum(float(t.pnl or 0) for t in recent_trades)
        
        # Win rate
        win_rate = (won_trades / (won_trades + lost_trades)) * 100 if (won_trades + lost_trades) > 0 else 0
        
        return JsonResponse({
            'success': True,
            'active': active,
            'completed': completed,
            'metrics': {
                'total_pnl': total_pnl,
                'win_rate': win_rate,
                'total_trades': total_trades,
                'active_trades': active_trades
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@api_view(['GET'])
def metrics(request):
    """MÃ©tricas en tiempo real del sistema"""
    try:
        # Obtener Ã³rdenes de la base de datos
        orders = OrderAudit.objects.all()
        
        # Calcular mÃ©tricas
        total_trades = orders.count()
        won_trades = orders.filter(status='won').count()
        lost_trades = orders.filter(status='lost').count()
        active_trades = orders.filter(status='active').count()
        
        # P&L total
        total_pnl = sum(float(order.pnl or 0) for order in orders)
        
        # Tasa de acierto
        completed_trades = won_trades + lost_trades
        win_rate = (won_trades / completed_trades) if completed_trades > 0 else 0
        
        # Drawdown mÃ¡ximo
        max_drawdown = 0
        running_pnl = 0
        peak = 0
        
        for order in orders.order_by('timestamp'):
            running_pnl += float(order.pnl or 0)
            if running_pnl > peak:
                peak = running_pnl
            drawdown = peak - running_pnl
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        max_drawdown_pct = (max_drawdown / abs(peak)) * 100 if peak != 0 else 0
        
        return Response({
            'pnl': total_pnl,
            'winrate': win_rate,
            'expectancy': total_pnl / completed_trades if completed_trades > 0 else 0,
            'max_drawdown_pct': max_drawdown_pct,
            'trades_per_hour': total_trades / 24,  # AproximaciÃ³n
            'latency_ms_avg': sum(float(order.latency_ms or 0) for order in orders) / total_trades if total_trades > 0 else 0,
            'fill_rate': (total_trades - orders.filter(status='pending').count()) / total_trades if total_trades > 0 else 0,
            'total_trades': total_trades,
            'won_trades': won_trades,
            'lost_trades': lost_trades,
            'active_trades': active_trades,
        })
    except Exception as e:
        return Response({
            'error': str(e),
            'pnl': 0.0,
            'winrate': 0.0,
            'total_trades': 0,
            'active_trades': 0,
        })


@api_view(['GET'])
def prometheus_metrics(request):
    """Exponer mÃ©tricas para Prometheus"""
    # TODO: Implementar mÃ©tricas reales de Prometheus
    return Response({
        'intradia_pnl_total': 0.0,
        'intradia_trades_total': 0,
        'intradia_active_trades': 0,
        'intradia_winrate': 0.0,
        'intradia_max_drawdown_pct': 0.0,
    })


@api_view(['POST', 'GET'])
def orders(request):
    """Manejar Ã³rdenes: POST para crear, GET para listar"""
    if request.method == 'POST':
        try:
            data = request.data
            symbol = data.get('symbol', 'EURUSD')
            side = data.get('side', 'buy')  # 'buy' o 'sell'
            size = float(data.get('size', 1.0))
            price = float(data.get('price', 0.0))
            stop_loss = float(data.get('stop_loss', 0.0))
            take_profit = float(data.get('take_profit', 0.0))
            
            # Crear request de orden
            from engine.services.execution_gateway import OrderRequest
            order_req = OrderRequest(
                symbol=symbol,
                side=side,
                size=size,
                price=price,
                stop=stop_loss,
                take_profit=take_profit
            )
            
            # Ejecutar a travÃ©s del gateway
            result = place_order_through_gateway(order_req)
            
            if result['accepted']:
                # Registrar en auditorÃ­a
                audit = OrderAudit.objects.create(
                    symbol=symbol,
                    action=side,
                    size=size,
                    price=result.get('price', price),
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    status='active',
                    response_hash=hash_payload(result),
                    latency_ms=result.get('latency_ms', 0)
                )
                
                return Response({
                    'accepted': True,
                    'order_id': result.get('order_id'),
                    'audit_id': audit.id,
                    'message': 'Orden ejecutada exitosamente'
                })
            else:
                return Response({
                    'accepted': False,
                    'reason': result.get('reason', 'Error desconocido')
                }, status=400)
                
        except Exception as e:
            return Response({
                'accepted': False,
                'reason': str(e)
            }, status=500)
    
    elif request.method == 'GET':
        """Listar Ã³rdenes recientes"""
        try:
            orders = OrderAudit.objects.all().order_by('-timestamp')[:50]
            orders_data = []
            
            for order in orders:
                orders_data.append({
                    'id': order.id,
                    'timestamp': order.timestamp.isoformat(),
                    'symbol': order.symbol,
                    'action': order.action,
                    'size': float(order.size or 0),
                    'price': float(order.price or 0),
                    'stop_loss': float(order.stop_loss or 0),
                    'take_profit': float(order.take_profit or 0),
                    'exit_price': float(order.exit_price or 0),
                    'pnl': float(order.pnl or 0),
                    'status': order.status,
                    'latency_ms': float(order.latency_ms or 0)
                })
            
            return Response({
                'orders': orders_data,
                'count': len(orders_data)
            })
            
        except Exception as e:
            return Response({
                'error': str(e),
                'orders': [],
                'count': 0
            })


@api_view(['POST'])
def backtest_run(request):
    """Ejecutar backtest"""
    try:
        data = request.data
        symbol = data.get('symbol', 'EURUSD')
        timeframe = data.get('timeframe', '1h')
        period_days = int(data.get('period_days', 30))
        
        # Ejecutar backtest
        result = run_backtest(symbol, timeframe)
        
        return Response({
            'success': True,
            'symbol': symbol,
            'timeframe': timeframe,
            'period_days': period_days,
            'results': result
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


@api_view(['POST'])
def trader_kill(request):
    """Kill switch para detener el sistema"""
    # TODO: Implementar kill switch real
    return Response({'killed': True, 'message': 'Sistema detenido'})


@api_view(['POST'])
def policy_promote(request):
    """Promover polÃ­tica de RL de shadow a active"""
    thresholds = {
        'min_trades': 100,
        'min_winrate': 0.55,
        'max_drawdown': 15.0
    }
    
    metrics = get_metrics()
    if not metrics:
        return Response({'promoted': False, 'reason': 'no_metrics'}, status=400)
    if metrics.get('max_drawdown', 100.0) > thresholds['max_drawdown']:
        return Response({'promoted': False, 'reason': 'dd_exceeds'}, status=400)
    if metrics.get('winrate', 0.0) < thresholds['min_winrate']:
        return Response({'promoted': False, 'reason': 'winrate_below'}, status=400)
    state, _ = PolicyState.objects.get_or_create(id=1)
    state.promote_to_rl(metrics)
    return Response({'promoted': True, 'mode': state.mode})


@api_view(['GET'])
def candles(request):
    """Obtener datos de velas para el grÃ¡fico"""
    from market.models import Candle
    
    symbol = request.GET.get('symbol', 'EURUSD')
    timeframe = request.GET.get('timeframe', '1h')
    limit = int(request.GET.get('limit', 100))
    
    # Obtener velas de la base de datos
    candles_qs = Candle.objects.filter(
        symbol=symbol, 
        timeframe=timeframe
    ).order_by('-timestamp')[:limit]
    
    # Convertir a formato para el grÃ¡fico
    candles_data = []
    for candle in candles_qs:
        candles_data.append({
            'timestamp': candle.timestamp.isoformat(),
            'open': float(candle.open),
            'high': float(candle.high),
            'low': float(candle.low),
            'close': float(candle.close),
            'volume': float(candle.volume)
        })
    
    return Response({
        'symbol': symbol,
        'timeframe': timeframe,
        'candles': candles_data,
        'count': len(candles_data)
    })


@api_view(['GET'])
def ticks_realtime(request):
    """Obtener ticks en tiempo real"""
    from market.models import Tick
    
    symbol = request.GET.get('symbol', 'R_10')
    limit = int(request.GET.get('limit', 100))
    
    # Obtener ticks mÃ¡s recientes
    ticks_qs = Tick.objects.filter(symbol=symbol).order_by('-timestamp')[:limit]
    
    ticks_data = []
    for tick in ticks_qs:
        ticks_data.append({
            'timestamp': tick.timestamp.isoformat(),
            'price': float(tick.price),
            'volume': float(tick.volume)
        })
    
    return Response({
        'symbol': symbol,
        'ticks': ticks_data,
        'count': len(ticks_data)
    })


def test_deriv_connection(request):
    """Test de conexiÃ³n con Deriv API"""
    try:
        from connectors.deriv_client import DerivClient
        from trading_bot.models import DerivAPIConfig
        
        # Obtener configuraciÃ³n activa para DerivClient
        api_config = DerivAPIConfig.objects.filter(is_active=True).only('api_token', 'is_demo', 'app_id').first()
        if api_config:
            client = DerivClient(
                api_token=api_config.api_token,
                is_demo=api_config.is_demo,
                app_id=api_config.app_id
            )
        else:
            client = DerivClient()
        authenticated = client.authenticate()
        
        if authenticated:
            balance_info = client.get_balance()
            return Response({
                'connected': True,
                'authenticated': True,
                'balance': balance_info,
                'message': 'ConexiÃ³n exitosa con Deriv'
            })
        else:
            return Response({
                'connected': False,
                'authenticated': False,
                'message': 'Error de autenticaciÃ³n con Deriv'
            }, status=400)
            
    except Exception as e:
        return Response({
            'connected': False,
            'error': str(e),
            'message': 'Error de conexiÃ³n con Deriv'
        }, status=500)


def dashboard(request):
    """Renderizar el dashboard principal con precios en tiempo real"""
    return render(request, 'dashboard_precios_realtime_v2.html')


@api_view(['GET', 'POST'])
def trading_config_api(request):
    """API para obtener y guardar configuraciÃ³n de trading"""
    from engine.models import CapitalConfig
    from django.http import JsonResponse
    
    if request.method == 'GET':
        config = CapitalConfig.get_active()
        return JsonResponse({
            'max_amount_pct_balance': config.max_amount_pct_balance,
            'max_amount_absolute': config.max_amount_absolute,
            'min_amount_per_trade': config.min_amount_per_trade,
            'min_trade_interval_seconds': config.min_trade_interval_seconds,
            'default_duration_forex': config.default_duration_forex,
            'default_duration_metals': config.default_duration_metals,
            'default_duration_indices': config.default_duration_indices,
            'symbol_amount_limits': config.symbol_amount_limits or {},
        })
    
    elif request.method == 'POST':
        config = CapitalConfig.get_active()
        data = json.loads(request.body) if request.body else {}
        
        # Actualizar campos
        if 'max_amount_pct_balance' in data:
            config.max_amount_pct_balance = float(data['max_amount_pct_balance'])
        if 'max_amount_absolute' in data:
            config.max_amount_absolute = float(data['max_amount_absolute'])
        if 'min_amount_per_trade' in data:
            config.min_amount_per_trade = float(data['min_amount_per_trade'])
        if 'min_trade_interval_seconds' in data:
            config.min_trade_interval_seconds = int(data['min_trade_interval_seconds'])
        if 'default_duration_forex' in data:
            config.default_duration_forex = int(data['default_duration_forex'])
        if 'default_duration_metals' in data:
            config.default_duration_metals = int(data['default_duration_metals'])
        if 'default_duration_indices' in data:
            config.default_duration_indices = int(data['default_duration_indices'])
        if 'symbol_amount_limits' in data:
            config.symbol_amount_limits = data['symbol_amount_limits']
        
        config.save()
        return JsonResponse({'success': True, 'message': 'ConfiguraciÃ³n actualizada'})

@login_required
def capital_config(request):
    """Vista para mostrar y editar configuraciÃ³n de capital"""
    from engine.models import CapitalConfig
    from decimal import Decimal
    
    if request.method == 'POST':
        config = CapitalConfig.get_active()
        
        # Actualizar valores del formulario - BÃ¡sicos
        config.profit_target = Decimal(request.POST.get('profit_target', '100.00'))
        config.max_loss = Decimal(request.POST.get('max_loss', '-50.00'))
        config.max_trades = int(request.POST.get('max_trades', '50'))
        config.profit_target_pct = float(request.POST.get('profit_target_pct', '5.0'))
        config.max_loss_pct = float(request.POST.get('max_loss_pct', '1.0'))
        config.protect_profits = request.POST.get('protect_profits') == 'on'
        config.profit_protection_pct = float(request.POST.get('profit_protection_pct', '0.5'))
        
        # Estrategias avanzadas
        config.position_sizing_method = request.POST.get('position_sizing_method', 'kelly_fractional')
        config.kelly_fraction = float(request.POST.get('kelly_fraction', '0.25'))
        config.risk_per_trade_pct = float(request.POST.get('risk_per_trade_pct', '1.0'))
        config.anti_martingale_multiplier = float(request.POST.get('anti_martingale_multiplier', '1.5'))
        config.anti_martingale_reset_on_loss = request.POST.get('anti_martingale_reset_on_loss') == 'on'
        config.atr_multiplier = float(request.POST.get('atr_multiplier', '2.0'))
        config.max_risk_per_trade_pct = float(request.POST.get('max_risk_per_trade_pct', '2.0'))
        config.max_drawdown_pct = float(request.POST.get('max_drawdown_pct', '10.0'))
        config.reduce_size_on_drawdown = request.POST.get('reduce_size_on_drawdown') == 'on'
        config.var_confidence = float(request.POST.get('var_confidence', '0.95'))
        config.max_concurrent_positions = int(request.POST.get('max_concurrent_positions', '5'))
        config.target_volatility = float(request.POST.get('target_volatility', '15.0'))
        
        # Protecciones avanzadas
        config.max_portfolio_risk_pct = float(request.POST.get('max_portfolio_risk_pct', '15.0'))
        config.max_single_position_risk_pct = float(request.POST.get('max_single_position_risk_pct', '5.0'))
        config.max_correlated_exposure_pct = float(request.POST.get('max_correlated_exposure_pct', '10.0'))
        config.max_active_positions = int(request.POST.get('max_active_positions', '10'))
        config.enable_volatility_scaling = request.POST.get('enable_volatility_scaling') == 'on'
        config.high_volatility_threshold = float(request.POST.get('high_volatility_threshold', '2.0'))
        config.volatility_reduction_pct = float(request.POST.get('volatility_reduction_pct', '50.0'))
        config.enable_time_based_stops = request.POST.get('enable_time_based_stops') == 'on'
        config.max_position_duration_minutes = int(request.POST.get('max_position_duration_minutes', '60'))
        config.close_losing_positions_after_minutes = int(request.POST.get('close_losing_positions_after_minutes', '30'))
        config.enable_emergency_stop = request.POST.get('enable_emergency_stop') == 'on'
        config.emergency_drawdown_threshold_pct = float(request.POST.get('emergency_drawdown_threshold_pct', '5.0'))
        config.enable_trailing_stop = request.POST.get('enable_trailing_stop') == 'on'
        config.trailing_stop_distance_pct = float(request.POST.get('trailing_stop_distance_pct', '1.0'))
        config.min_profit_for_trailing_pct = float(request.POST.get('min_profit_for_trailing_pct', '0.5'))
        
        # Configuraciones de Trading (Amounts y LÃ­mites)
        config.max_amount_pct_balance = float(request.POST.get('max_amount_pct_balance', '5.0'))
        config.max_amount_absolute = float(request.POST.get('max_amount_absolute', '500.0'))
        config.min_amount_per_trade = float(request.POST.get('min_amount_per_trade', '1.0'))
        config.min_trade_interval_seconds = int(request.POST.get('min_trade_interval_seconds', '60'))
        config.default_duration_forex = int(request.POST.get('default_duration_forex', '900'))
        config.default_duration_metals = int(request.POST.get('default_duration_metals', '300'))
        config.default_duration_indices = int(request.POST.get('default_duration_indices', '30'))
        
        # LÃ­mites por sÃ­mbolo (JSON)
        symbol_limits = {}
        # Recibir lÃ­mites por sÃ­mbolo desde el formulario
        for key in request.POST.keys():
            if key.startswith('symbol_limit_'):
                symbol = key.replace('symbol_limit_', '')
                try:
                    limit_value = float(request.POST.get(key))
                    if limit_value > 0:
                        symbol_limits[symbol] = limit_value
                except (ValueError, TypeError):
                    pass
        
        # Si hay sÃ­mbolos nuevos en el formulario
        new_symbol = request.POST.get('new_symbol', '').strip()
        new_symbol_limit = request.POST.get('new_symbol_limit', '0')
        if new_symbol and new_symbol_limit:
            try:
                limit_value = float(new_symbol_limit)
                if limit_value > 0:
                    symbol_limits[new_symbol] = limit_value
            except (ValueError, TypeError):
                pass
        
        config.symbol_amount_limits = symbol_limits if symbol_limits else config.symbol_amount_limits
        
        config.save()
        
        messages.success(request, 'âœ… ConfiguraciÃ³n de capital actualizada exitosamente')
        
        # Si es una peticiÃ³n AJAX, retornar JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from django.http import JsonResponse
            return JsonResponse({'success': True, 'message': 'ConfiguraciÃ³n actualizada exitosamente'})
        
        return redirect('engine:capital-config')
    
    config = CapitalConfig.get_active()
    
    # Obtener estadÃ­sticas actuales con Advanced Capital Manager
    from engine.services.advanced_capital_manager import AdvancedCapitalManager
    from connectors.deriv_client import DerivClient
    
    try:
        # Obtener configuraciÃ³n activa para DerivClient
        from trading_bot.models import DerivAPIConfig
        api_config = DerivAPIConfig.objects.filter(is_active=True).only('api_token', 'is_demo', 'app_id').first()
        if api_config:
            client = DerivClient(
                api_token=api_config.api_token,
                is_demo=api_config.is_demo,
                app_id=api_config.app_id
            )
        else:
            client = DerivClient()
        current_balance = Decimal(str(client.get_balance().get('balance', 0)))
        
        # Obtener estadÃ­sticas diarias primero
        from django.utils import timezone
        from datetime import datetime, timedelta
        today = timezone.localdate()
        start_of_day = timezone.make_aware(datetime(today.year, today.month, today.day, 0, 0, 0))
        
        daily_trades = OrderAudit.objects.filter(
            timestamp__gte=start_of_day,
            status__in=['won', 'lost']
        )
        
        total_pnl = sum(trade.pnl for trade in daily_trades if trade.pnl is not None)
        trades_count = daily_trades.count()
        won_trades = daily_trades.filter(status='won').count()
        lost_trades = daily_trades.filter(status='lost').count()
        active_trades = OrderAudit.objects.filter(status='open').count()
        
        win_rate = (won_trades / trades_count * 100) if trades_count > 0 else 0
        
        # Crear Advanced Capital Manager
        advanced_manager = AdvancedCapitalManager(
            profit_target=config.profit_target,
            max_loss=config.max_loss,
            max_trades=config.max_trades,
            profit_target_pct=config.profit_target_pct,
            max_loss_pct=config.max_loss_pct,
            position_sizing_method=getattr(config, 'position_sizing_method', 'kelly_fractional'),
            kelly_fraction=getattr(config, 'kelly_fraction', 0.25),
            risk_per_trade_pct=getattr(config, 'risk_per_trade_pct', 1.0),
            anti_martingale_multiplier=getattr(config, 'anti_martingale_multiplier', 1.5),
            anti_martingale_reset_on_loss=getattr(config, 'anti_martingale_reset_on_loss', True),
            atr_multiplier=getattr(config, 'atr_multiplier', 2.0),
            max_risk_per_trade_pct=getattr(config, 'max_risk_per_trade_pct', 2.0),
            max_drawdown_pct=getattr(config, 'max_drawdown_pct', 10.0),
            reduce_size_on_drawdown=getattr(config, 'reduce_size_on_drawdown', True),
            var_confidence=getattr(config, 'var_confidence', 0.95),
            max_concurrent_positions=getattr(config, 'max_concurrent_positions', 5),
            target_volatility=getattr(config, 'target_volatility', 15.0),
        )
        
        can_trade, reason = advanced_manager.can_trade(current_balance)
        
        # Obtener estadÃ­sticas avanzadas
        advanced_stats = advanced_manager.get_advanced_statistics(current_balance)
        
        # Obtener mÃ©tricas de protecciÃ³n de riesgo
        from engine.services.risk_protection import RiskProtectionSystem
        risk_protection = RiskProtectionSystem(
            max_portfolio_risk_pct=getattr(config, 'max_portfolio_risk_pct', 15.0),
            max_single_position_risk_pct=getattr(config, 'max_single_position_risk_pct', 5.0),
            max_correlated_exposure_pct=getattr(config, 'max_correlated_exposure_pct', 10.0),
            max_active_positions=getattr(config, 'max_active_positions', 10),
            enable_emergency_stop=getattr(config, 'enable_emergency_stop', True),
            emergency_drawdown_threshold_pct=getattr(config, 'emergency_drawdown_threshold_pct', 10.0),
        )
        
        portfolio_metrics = risk_protection.get_portfolio_metrics(current_balance)
        
        # Verificar emergencia
        emergency_active, emergency_reason = risk_protection.check_emergency_conditions(current_balance)
        
        # Mensaje de estado con informaciÃ³n avanzada
        status_message = f"P&L: ${total_pnl:.2f} | Win Rate: {win_rate:.1f}% | Drawdown: {advanced_stats['drawdown_pct']:.2f}% | VaR: ${advanced_stats['var']['var_usd']:.2f} | Kelly: {advanced_stats['trading_stats']['kelly_percentage']*100:.1f}%"
        if emergency_active:
            status_message += f" | ðŸš¨ EMERGENCIA: {emergency_reason}"
        
        context = {
            'config': config,
            'current_balance': current_balance,
            'can_trade': can_trade and not emergency_active,
            'reason': reason or (emergency_reason if emergency_active else None),
            'status_message': status_message,
            'trades_count': trades_count,
            'won_trades': won_trades,
            'lost_trades': lost_trades,
            'active_trades': active_trades,
            'daily_pnl': total_pnl,
            'win_rate': win_rate,
            'advanced_stats': advanced_stats,
            'portfolio_metrics': portfolio_metrics,
            'emergency_active': emergency_active,
            'emergency_reason': emergency_reason,
        }
    except Exception as e:
        context = {
            'config': config,
            'error': str(e),
            'can_trade': True,
            'reason': None,
            'status_message': None,
            'current_balance': Decimal('0.00'),
            'trades_count': 0,
            'daily_pnl': Decimal('0.00'),
            'win_rate': 0,
        }
    
    return render(request, 'engine/capital_config.html', context)


@login_required
def quick_controls_api(request):
    """API para obtener y actualizar controles rÃ¡pidos (lÃ­mites para pruebas)"""
    from engine.models import CapitalConfig
    from decimal import Decimal
    
    if request.method == 'GET':
        # Obtener configuraciÃ³n actual
        config = CapitalConfig.get_active()
        return JsonResponse({
            'success': True,
            'disable_max_trades': config.disable_max_trades,
            'disable_profit_target': config.disable_profit_target,
            'stop_loss_amount': float(config.stop_loss_amount) if config.stop_loss_amount else 0
        })
    
    elif request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            
            config = CapitalConfig.get_active()
            
            # Actualizar valores
            config.disable_max_trades = data.get('disable_max_trades', False)
            config.disable_profit_target = data.get('disable_profit_target', False)
            stop_loss = data.get('stop_loss_amount', 0)
            config.stop_loss_amount = Decimal(str(stop_loss)) if stop_loss else Decimal('0.00')
            
            config.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Controles rÃ¡pidos actualizados exitosamente'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=400)
    
    return JsonResponse({'success': False, 'message': 'MÃ©todo no permitido'}, status=405)


@login_required
def services_admin(request):
    """Panel de administraciÃ³n de servicios (trading loop, daphne, gunicorn)"""
    return render(request, 'engine/services_admin.html')


@login_required
def services_status_api(request):
    """API para obtener el estado de los servicios systemd"""
    import subprocess
    import json
    
    services = {
        'trading-loop': 'intradia-trading-loop.service',
        'daphne': 'intradia-daphne.service',
        'save-ticks': 'intradia-save-ticks.service',
        'gunicorn': 'intradia-gunicorn.service',
    }
    
    status_data = {}
    
    for service_key, service_name in services.items():
        try:
            # Ejecutar systemctl is-active de forma segura (con sudo si es necesario)
            result = subprocess.run(
                ['/usr/bin/sudo', 'systemctl', 'is-active', service_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            is_active = result.returncode == 0
            status_text = result.stdout.strip() if result.returncode == 0 else 'inactive'
            
            # Obtener mÃ¡s informaciÃ³n con systemctl show
            show_result = subprocess.run(
                ['/usr/bin/sudo', 'systemctl', 'show', service_name, '--property=ActiveState,SubState,MainPID'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            details = {}
            if show_result.returncode == 0:
                for line in show_result.stdout.strip().split('\n'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        details[key] = value
            
            # Intentar obtener las Ãºltimas lÃ­neas del log
            log_lines = []
            try:
                if service_key == 'trading-loop':
                    log_file = '/var/log/intradia/trading_loop.log'
                elif service_key == 'daphne':
                    log_file = '/var/log/intradia/daphne.log'
                elif service_key == 'save-ticks':
                    log_file = '/var/log/intradia/save_ticks.log'
                else:
                    log_file = '/var/log/gunicorn/intradia_error.log'
                
                tail_result = subprocess.run(
                    ['/usr/bin/tail', '-n', '20', log_file],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if tail_result.returncode == 0:
                    log_lines = tail_result.stdout.strip().split('\n')[-10:]  # Ãšltimas 10 lÃ­neas
            except Exception:
                log_lines = []
            
            status_data[service_key] = {
                'active': is_active,
                'status': status_text,
                'details': details,
                'log_preview': log_lines,
                'service_name': service_name
            }
            
        except subprocess.TimeoutExpired:
            status_data[service_key] = {
                'active': False,
                'status': 'timeout',
                'error': 'Timeout al consultar el servicio',
                'service_name': service_name
            }
        except FileNotFoundError as e:
            status_data[service_key] = {
                'active': False,
                'status': 'error',
                'error': f'Comando no encontrado: {str(e)}. Verifique que /usr/bin/sudo existe.',
                'service_name': service_name
            }
        except Exception as e:
            status_data[service_key] = {
                'active': False,
                'status': 'error',
                'error': str(e),
                'service_name': service_name
            }
    
    return JsonResponse({
        'success': True,
        'services': status_data
    })


@login_required
def services_restart_api(request):
    """API para reiniciar un servicio especÃ­fico"""
    import subprocess
    import json
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'MÃ©todo no permitido'}, status=405)
    
    try:
        data = json.loads(request.body)
        service_key = data.get('service')
        
        # Mapeo de servicios permitidos
        services_map = {
            'trading-loop': 'intradia-trading-loop.service',
            'daphne': 'intradia-daphne.service',
            'save-ticks': 'intradia-save-ticks.service',
            'gunicorn': 'intradia-gunicorn.service',
        }
        
        if service_key not in services_map:
            return JsonResponse({
                'success': False,
                'message': f'Servicio "{service_key}" no vÃ¡lido'
            }, status=400)
        
        service_name = services_map[service_key]
        
        # Ejecutar systemctl restart de forma segura (con sudo)
        result = subprocess.run(
            ['/usr/bin/sudo', 'systemctl', 'restart', service_name],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            # Esperar un momento y verificar que se reiniciÃ³ correctamente
            import time
            time.sleep(2)
            
            check_result = subprocess.run(
                ['/usr/bin/sudo', 'systemctl', 'is-active', service_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            is_active = check_result.returncode == 0
            
            return JsonResponse({
                'success': True,
                'message': f'Servicio {service_key} reiniciado exitosamente',
                'active': is_active
            })
        else:
            return JsonResponse({
                'success': False,
                'message': f'Error al reiniciar: {result.stderr}'
            }, status=500)
            
    except subprocess.TimeoutExpired:
        return JsonResponse({
            'success': False,
            'message': 'Timeout al reiniciar el servicio'
        }, status=500)
    except FileNotFoundError as e:
        return JsonResponse({
            'success': False,
            'message': f'Comando no encontrado: {str(e)}. Verifique que /usr/bin/sudo existe en el servidor.'
        }, status=500)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)


@login_required
def services_logs_api(request):
    """API para obtener los Ãºltimos logs de un servicio"""
    import subprocess
    import json
    
    service_key = request.GET.get('service')
    lines = int(request.GET.get('lines', 50))
    
    # Mapeo de servicios y sus archivos de log
    log_files = {
        'trading-loop': '/var/log/intradia/trading_loop.log',
        'daphne': '/var/log/intradia/daphne.log',
        'save-ticks': '/var/log/intradia/save_ticks.log',
        'gunicorn': '/var/log/gunicorn/intradia_error.log',
    }
    
    if service_key not in log_files:
        return JsonResponse({
            'success': False,
            'message': f'Servicio "{service_key}" no vÃ¡lido'
        }, status=400)
    
    log_file = log_files[service_key]
    
    try:
        result = subprocess.run(
            ['/usr/bin/tail', '-n', str(lines), log_file],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            log_lines = result.stdout.strip().split('\n')
            return JsonResponse({
                'success': True,
                'logs': log_lines,
                'service': service_key
            })
        else:
            return JsonResponse({
                'success': False,
                'message': f'Error al leer logs: {result.stderr}'
            }, status=500)
            
    except subprocess.TimeoutExpired:
        return JsonResponse({
            'success': False,
            'message': 'Timeout al leer logs'
        }, status=500)
    except FileNotFoundError as e:
        return JsonResponse({
            'success': False,
            'message': f'Comando no encontrado: {str(e)}. Verifique que /usr/bin/tail existe en el servidor.'
        }, status=500)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)


@login_required
def trading_loop_control_api(request):
    """API para pausar/reanudar el trading loop"""
    import subprocess
    import json
    
    if request.method == 'GET':
        # Para GET, solo retornar el estado actual
        try:
            service_name = 'intradia-trading-loop.service'
            result = subprocess.run(
                ['/usr/bin/sudo', 'systemctl', 'is-active', service_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            is_active = result.returncode == 0
            return JsonResponse({
                'success': True,
                'is_active': is_active,
                'status': 'active' if is_active else 'inactive'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=500)
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'MÃ©todo no permitido'}, status=405)
    
    try:
        data = json.loads(request.body)
        action = data.get('action')  # 'pause' o 'resume'
        
        if action not in ['pause', 'resume']:
            return JsonResponse({
                'success': False,
                'message': 'AcciÃ³n no vÃ¡lida. Use "pause" o "resume"'
            }, status=400)
        
        service_name = 'intradia-trading-loop.service'
        
        if action == 'pause':
            # Detener el servicio
            result = subprocess.run(
                ['/usr/bin/sudo', 'systemctl', 'stop', service_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            message = 'Trading loop pausado'
        else:  # resume
            # Iniciar el servicio
            result = subprocess.run(
                ['/usr/bin/sudo', 'systemctl', 'start', service_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            message = 'Trading loop reanudado'
        
        if result.returncode == 0:
            # Esperar un momento y verificar estado
            import time
            time.sleep(1)
            
            check_result = subprocess.run(
                ['/usr/bin/sudo', 'systemctl', 'is-active', service_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            is_active = check_result.returncode == 0
            
            return JsonResponse({
                'success': True,
                'message': message,
                'is_active': is_active
            })
        else:
            return JsonResponse({
                'success': False,
                'message': f'Error: {result.stderr}'
            }, status=500)
            
    except subprocess.TimeoutExpired:
        return JsonResponse({
            'success': False,
            'message': 'Timeout al ejecutar la acciÃ³n'
        }, status=500)
    except FileNotFoundError as e:
        return JsonResponse({
            'success': False,
            'message': f'Comando no encontrado: {str(e)}. Verifique que /usr/bin/sudo existe en el servidor.'
        }, status=500)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)
 #   E s t a s   f u n c i o n e s   s e   a g r e g a r Ã ¡ n   a l   f i n a l   d e   e n g i n e / v i e w s . p y  
  
 @ l o g i n _ r e q u i r e d  
 d e f   a c t i v e _ t r a d e s _ a p i ( r e q u e s t ) :  
         " " " A P I   p a r a   o b t e n e r   t r a d e s   a c t i v o s / p e n d i e n t e s " " "  
         t r y :  
                 f r o m   m o n i t o r i n g . m o d e l s   i m p o r t   O r d e r A u d i t  
                 f r o m   d j a n g o . u t i l s   i m p o r t   t i m e z o n e  
                  
                 #   O b t e n e r   t r a d e s   a c t i v o s / p e n d i e n t e s  
                 a c t i v e _ t r a d e s   =   O r d e r A u d i t . o b j e c t s . f i l t e r (  
                         s t a t u s _ _ i n = [ ' p e n d i n g ' ,   ' a c t i v e ' ]  
                 ) . o r d e r _ b y ( ' - t i m e s t a m p ' ) [ : 5 0 ]  
                  
                 t r a d e s _ d a t a   =   [ ]  
                 f o r   t r a d e   i n   a c t i v e _ t r a d e s :  
                         c o n t r a c t _ i d   =   N o n e  
                         i f   t r a d e . r e q u e s t _ p a y l o a d :  
                                 c o n t r a c t _ i d   =   t r a d e . r e q u e s t _ p a y l o a d . g e t ( ' c o n t r a c t _ i d ' )   o r   t r a d e . r e q u e s t _ p a y l o a d . g e t ( ' o r d e r _ i d ' )  
                          
                         t r a d e s _ d a t a . a p p e n d ( {  
                                 ' i d ' :   t r a d e . i d ,  
                                 ' s y m b o l ' :   t r a d e . s y m b o l ,  
                                 ' d i r e c t i o n ' :   t r a d e . a c t i o n . u p p e r ( )   i f   t r a d e . a c t i o n   e l s e   ' N / A ' ,  
                                 ' p r i c e ' :   f l o a t ( t r a d e . p r i c e )   i f   t r a d e . p r i c e   e l s e   0 . 0 ,  
                                 ' a m o u n t ' :   f l o a t ( t r a d e . s i z e )   i f   t r a d e . s i z e   e l s e   0 . 0 ,  
                                 ' t i m e s t a m p ' :   t r a d e . t i m e s t a m p . i s o f o r m a t ( ) ,  
                                 ' s t a t u s ' :   t r a d e . s t a t u s ,  
                                 ' c o n t r a c t _ i d ' :   c o n t r a c t _ i d ,  
                                 ' h o u r s _ a g o ' :   r o u n d ( ( t i m e z o n e . n o w ( )   -   t r a d e . t i m e s t a m p ) . t o t a l _ s e c o n d s ( )   /   3 6 0 0 ,   2 )  
                         } )  
                  
                 r e t u r n   J s o n R e s p o n s e ( {  
                         ' s u c c e s s ' :   T r u e ,  
                         ' t r a d e s ' :   t r a d e s _ d a t a ,  
                         ' c o u n t ' :   l e n ( t r a d e s _ d a t a )  
                 } )  
         e x c e p t   E x c e p t i o n   a s   e :  
                 r e t u r n   J s o n R e s p o n s e ( {  
                         ' s u c c e s s ' :   F a l s e ,  
                         ' e r r o r ' :   s t r ( e )  
                 } ,   s t a t u s = 5 0 0 )  
  
  
 @ l o g i n _ r e q u i r e d  
 @ c s r f _ e x e m p t  
 d e f   c l o s e _ t r a d e _ a p i ( r e q u e s t ) :  
         " " " A P I   p a r a   c e r r a r   u n   t r a d e   a c t i v o " " "  
         i f   r e q u e s t . m e t h o d   ! =   ' P O S T ' :  
                 r e t u r n   J s o n R e s p o n s e ( {  
                         ' s u c c e s s ' :   F a l s e ,  
                         ' e r r o r ' :   ' M Ã © t o d o   n o   p e r m i t i d o '  
                 } ,   s t a t u s = 4 0 5 )  
          
         t r y :  
                 i m p o r t   j s o n  
                 f r o m   c o n n e c t o r s . d e r i v _ c l i e n t   i m p o r t   D e r i v C l i e n t  
                 f r o m   t r a d i n g _ b o t . m o d e l s   i m p o r t   D e r i v A P I C o n f i g  
                 f r o m   m o n i t o r i n g . m o d e l s   i m p o r t   O r d e r A u d i t  
                  
                 d a t a   =   j s o n . l o a d s ( r e q u e s t . b o d y )  
                 c o n t r a c t _ i d   =   d a t a . g e t ( ' c o n t r a c t _ i d ' )  
                 t r a d e _ i d   =   d a t a . g e t ( ' t r a d e _ i d ' )  
                  
                 i f   n o t   c o n t r a c t _ i d   a n d   n o t   t r a d e _ i d :  
                         r e t u r n   J s o n R e s p o n s e ( {  
                                 ' s u c c e s s ' :   F a l s e ,  
                                 ' e r r o r ' :   ' S e   r e q u i e r e   c o n t r a c t _ i d   o   t r a d e _ i d '  
                         } ,   s t a t u s = 4 0 0 )  
                  
                 #   S i   s o l o   t e n e m o s   t r a d e _ i d ,   o b t e n e r   c o n t r a c t _ i d   d e l   t r a d e  
                 t r a d e   =   N o n e  
                 i f   n o t   c o n t r a c t _ i d   a n d   t r a d e _ i d :  
                         t r y :  
                                 t r a d e   =   O r d e r A u d i t . o b j e c t s . g e t ( i d = t r a d e _ i d )  
                                 i f   t r a d e . r e q u e s t _ p a y l o a d :  
                                         c o n t r a c t _ i d   =   t r a d e . r e q u e s t _ p a y l o a d . g e t ( ' c o n t r a c t _ i d ' )   o r   t r a d e . r e q u e s t _ p a y l o a d . g e t ( ' o r d e r _ i d ' )  
                         e x c e p t   O r d e r A u d i t . D o e s N o t E x i s t :  
                                 r e t u r n   J s o n R e s p o n s e ( {  
                                         ' s u c c e s s ' :   F a l s e ,  
                                         ' e r r o r ' :   ' T r a d e   n o   e n c o n t r a d o '  
                                 } ,   s t a t u s = 4 0 4 )  
                  
                 i f   n o t   c o n t r a c t _ i d :  
                         r e t u r n   J s o n R e s p o n s e ( {  
                                 ' s u c c e s s ' :   F a l s e ,  
                                 ' e r r o r ' :   ' N o   s e   p u d o   o b t e n e r   c o n t r a c t _ i d '  
                         } ,   s t a t u s = 4 0 0 )  
                  
                 #   O b t e n e r   c o n f i g u r a c i Ã ³ n   d e   A P I  
                 c o n f i g   =   D e r i v A P I C o n f i g . o b j e c t s . f i l t e r ( i s _ a c t i v e = T r u e ) . f i r s t ( )  
                 i f   n o t   c o n f i g :  
                         r e t u r n   J s o n R e s p o n s e ( {  
                                 ' s u c c e s s ' :   F a l s e ,  
                                 ' e r r o r ' :   ' N o   h a y   c o n f i g u r a c i Ã ³ n   d e   A P I   a c t i v a '  
                         } ,   s t a t u s = 5 0 0 )  
                  
                 #   C e r r a r   e l   c o n t r a t o  
                 c l i e n t   =   D e r i v C l i e n t (  
                         a p i _ t o k e n = c o n f i g . a p i _ t o k e n ,  
                         i s _ d e m o = c o n f i g . i s _ d e m o ,  
                         a p p _ i d = c o n f i g . a p p _ i d  
                 )  
                  
                 r e s u l t   =   c l i e n t . s e l l _ c o n t r a c t ( s t r ( c o n t r a c t _ i d ) )  
                  
                 i f   r e s u l t . g e t ( ' e r r o r ' ) :  
                         r e t u r n   J s o n R e s p o n s e ( {  
                                 ' s u c c e s s ' :   F a l s e ,  
                                 ' e r r o r ' :   r e s u l t [ ' e r r o r ' ]  
                         } ,   s t a t u s = 5 0 0 )  
                  
                 #   A c t u a l i z a r   e l   t r a d e   e n   l a   b a s e   d e   d a t o s  
                 i f   t r a d e _ i d :  
                         t r y :  
                                 i f   n o t   t r a d e :  
                                         t r a d e   =   O r d e r A u d i t . o b j e c t s . g e t ( i d = t r a d e _ i d )  
                                 t r a d e . s t a t u s   =   ' w o n '   i f   r e s u l t . g e t ( ' p r o f i t ' ,   0 )   >   0   e l s e   ' l o s t '  
                                 t r a d e . p n l   =   D e c i m a l ( s t r ( r e s u l t . g e t ( ' p r o f i t ' ,   0 ) ) )  
                                  
                                 #   G u a r d a r   r e s p u e s t a   d e   l a   v e n t a  
                                 i f   n o t   t r a d e . r e s p o n s e _ p a y l o a d :  
                                         t r a d e . r e s p o n s e _ p a y l o a d   =   { }  
                                 t r a d e . r e s p o n s e _ p a y l o a d [ ' s e l l _ r e s u l t ' ]   =   r e s u l t  
                                  
                                 t r a d e . s a v e ( )  
                         e x c e p t   O r d e r A u d i t . D o e s N o t E x i s t :  
                                 p a s s  
                  
                 r e t u r n   J s o n R e s p o n s e ( {  
                         ' s u c c e s s ' :   T r u e ,  
                         ' r e s u l t ' :   r e s u l t ,  
                         ' m e s s a g e ' :   f ' C o n t r a t o   { c o n t r a c t _ i d }   c e r r a d o   e x i t o s a m e n t e '  
                 } )  
                  
         e x c e p t   E x c e p t i o n   a s   e :  
                 r e t u r n   J s o n R e s p o n s e ( {  
                         ' s u c c e s s ' :   F a l s e ,  
                         ' e r r o r ' :   s t r ( e )  
                 } ,   s t a t u s = 5 0 0 )  
  
 
