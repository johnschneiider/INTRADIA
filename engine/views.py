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


@login_required
def dashboard(request):
    """Renderizar el dashboard principal con precios en tiempo real"""
    return render(request, 'dashboard_precios_realtime_v2.html')


@api_view(['GET'])
def get_trades(request):
    """Obtener operaciones activas y finalizadas"""
    try:
        from datetime import timedelta
        from django.utils import timezone
        
        # Historial persistente desde la BD (no limitar a 30 minutos)
        # Mostrar las últimas 200 operaciones, incluyendo finalizadas antiguas
        # Incluir TODOS los trades sin filtrar por estado
        # Usar list() para evaluar el QuerySet y obtener todos los resultados
        trades = list(OrderAudit.objects.all().order_by('-timestamp')[:200])
        
        # Debug: mostrar cantidad de trades encontrados
        print(f"📊 Total trades encontrados: {len(trades)}")
        
        active = []
        completed = []
        
        for trade in trades:
            # Obtener monto/stake REAL del trade (prioridad al monto final usado)
            amount = None
            
            # 1. Primero intentar desde response_payload['amount'] (monto REAL usado después de ajustes)
            if trade.response_payload:
                amount = trade.response_payload.get('amount')
                if amount:
                    amount = float(amount)
            
            # 2. Si no está en response_payload, usar size (campo directo del modelo)
            if not amount and trade.size:
                amount = float(trade.size)
            
            # 3. Si aún no tenemos monto, intentar desde request_payload
            if not amount and trade.request_payload:
                # Intentar obtener desde position_sizing (monto calculado, puede diferir del real)
                position_sizing = trade.request_payload.get('position_sizing', {})
                if position_sizing:
                    amount = position_sizing.get('risk_amount') or position_sizing.get('amount')
                    if amount:
                        amount = float(amount)
                # Si no está en position_sizing, buscar en el request directamente
                if not amount:
                    amount = trade.request_payload.get('amount') or trade.request_payload.get('stake')
                    if amount:
                        amount = float(amount)
            
            # Si aún no tenemos monto, usar 0.0 (no debería pasar)
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
                        # Alternativa: confianza del propio signal (estrategia estadística)
                        conf_val = trade.request_payload.get('confidence')
                    if conf_val is not None:
                        confidence_pct = float(conf_val) * 100.0 if float(conf_val) <= 1.0 else float(conf_val)
            except Exception:
                confidence_pct = None

            # Extraer estrategia del request_payload
            strategy_name = None
            try:
                internal_name = trade.request_payload.get('strategy')
                # Fallback heurístico si 'strategy' no está presente en el payload
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
                    strategy_name = 'Híbrida'
                elif internal_name == 'ema200_extrema':
                    strategy_name = 'EMA100'
                elif internal_name == 'tick_based':
                    strategy_name = 'Ticks'
                elif internal_name == 'momentum_reversal':
                    strategy_name = 'Reversión'
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
            
            # Mostrar como activo si está pending o active
            # Mostrar como completado si está won, lost, rejected, o cualquier otro estado
            if trade.status in ['pending', 'active']:
                active.append(trade_data)
            else:
                # Incluir todos los estados finalizados: won, lost, rejected, expired, etc.
                completed.append(trade_data)
        
        # Debug: mostrar cantidad de trades por categoría
        print(f"📊 Trades activos: {len(active)}, Trades completados: {len(completed)}")
        
        # MÉTRICAS: Operaciones en las últimas 24 horas
        since_metrics = timezone.now() - timedelta(hours=24)
        recent_trades = OrderAudit.objects.filter(timestamp__gte=since_metrics)
        
        total_trades = recent_trades.count()
        won_trades = recent_trades.filter(status='won').count()
        lost_trades = recent_trades.filter(status='lost').count()
        active_trades = recent_trades.filter(status__in=['pending', 'active']).count()
        
        # P&L total de las últimas 24 horas
        total_pnl = sum(float(t.pnl or 0) for t in recent_trades)
        
        # Win rate general (últimas 24 horas)
        win_rate = (won_trades / (won_trades + lost_trades)) * 100 if (won_trades + lost_trades) > 0 else 0
        
        # Calcular winrate de últimos 20 trades (más preciso para control de pérdidas)
        try:
            recent_20_trades = list(OrderAudit.objects.filter(
                accepted=True,
                status__in=['won', 'lost']
            ).order_by('-timestamp')[:20])
            
            recent_20_total = len(recent_20_trades)
            recent_20_won = sum(1 for t in recent_20_trades if t.status == 'won')
            win_rate_recent = (recent_20_won / recent_20_total) if recent_20_total > 0 else (win_rate / 100)
        except Exception:
            win_rate_recent = win_rate / 100  # Fallback a winrate general
        
        # Calcular drawdown y estado de pausa para métricas
        drawdown_pct = 0.0
        pause_active = False
        pause_allowed_symbol = None
        losing_streak = 0
        try:
            from engine.services.adaptive_filter_manager import AdaptiveFilterManager
            from decimal import Decimal
            # Obtener balance actual para calcular drawdown correctamente
            try:
                from connectors.deriv_client import DerivClient
                from trading_bot.models import DerivAPIConfig
                api_config = DerivAPIConfig.objects.filter(is_active=True).only('api_token', 'is_demo', 'app_id').first()
                if api_config:
                    client = DerivClient(api_token=api_config.api_token, is_demo=api_config.is_demo, app_id=api_config.app_id)
                    balance_info = client.get_balance()
                    current_balance = Decimal(str(balance_info.get('balance', 0) if isinstance(balance_info, dict) else balance_info))
                else:
                    current_balance = Decimal('0')
            except:
                current_balance = Decimal('0')
            
            adaptive_manager = AdaptiveFilterManager()
            metrics_obj = adaptive_manager.calculate_metrics(current_balance)
            drawdown_pct = metrics_obj.drawdown_pct
            losing_streak = metrics_obj.losing_streak
            # Evaluar pausa y símbolo permitido
            try:
                top_list = adaptive_manager.get_top_symbols_by_performance(lookback=20, top_n=1)
                best_symbol = top_list[0][0] if top_list else None
            except Exception:
                best_symbol = None
            pause_info = adaptive_manager.should_pause_trading(metrics_obj, best_symbol=best_symbol)
            pause_active = bool(pause_info.get('should_pause'))
            pause_allowed_symbol = pause_info.get('allowed_symbol')
        except Exception as e:
            print(f"Error calculando drawdown: {e}")
            drawdown_pct = 0.0
            pause_active = False
            pause_allowed_symbol = None
        
        return JsonResponse({
            'success': True,
            'active': active,
            'completed': completed,
            'metrics': {
                'total_pnl': total_pnl,
                'win_rate': win_rate_recent,  # Winrate últimos 20 trades (decimal 0-1)
                'win_rate_pct': win_rate_recent * 100,  # Mantener porcentaje para display
                'drawdown_pct': drawdown_pct,
                'losing_streak': losing_streak,
                'total_trades': total_trades,
                'active_trades': active_trades,
                'pause_active': pause_active,
                'pause_allowed_symbol': pause_allowed_symbol
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@csrf_exempt
def diagnose_stuck_trades_api(request):
    """Diagnosticar trades que se quedan pegados"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)
    
    try:
        from django.core.management import call_command
        from io import StringIO
        import sys
        
        # Capturar output del comando
        old_stdout = sys.stdout
        sys.stdout = output = StringIO()
        
        try:
            # Ejecutar diagnóstico
            call_command('diagnose_stuck_trades', '--all', verbosity=2)
            output_str = output.getvalue()
        finally:
            sys.stdout = old_stdout
        
        return JsonResponse({
            'success': True,
            'output': output_str,
            'message': 'Diagnóstico completado'
        })
    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@api_view(['GET'])
def get_balance(request):
    """Obtener balance de Deriv con manejo de rate limiting"""
    try:
        from connectors.deriv_client import DerivClient
        from trading_bot.models import DerivAPIConfig
        
        # Obtener configuración activa (usar only() para evitar campos scope_*)
        api_token = None
        is_demo = False  # Default a REAL (más seguro)
        app_id = '1089'
        
        try:
            # Obtener configuración activa sin filtrar por usuario específico
            # Usar only() para evitar campos scope_* que no existen
            config = DerivAPIConfig.objects.filter(is_active=True).only('api_token', 'is_demo', 'app_id').first()
            if config:
                api_token = config.api_token
                is_demo = config.is_demo
                app_id = config.app_id
                print(f"✅ Configuración encontrada: is_demo={is_demo}, app_id={app_id}, token={api_token[:10] if api_token else 'None'}...")
            else:
                print("⚠️ No se encontró configuración activa de DerivAPIConfig")
                return JsonResponse({
                    'success': False,
                    'error': 'No hay configuración de API activa',
                    'balance': 0.0,
                    'currency': 'USD',
                    'account_type': 'unknown'
                }, status=500)
        except Exception as e:
            print(f"⚠️ Error al obtener configuración en get_balance: {e}")
            import traceback
            traceback.print_exc()
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
                        print(f"✅ Configuración obtenida vía SQL: is_demo={is_demo}, app_id={app_id}")
            except Exception as e2:
                print(f"⚠️ Error al obtener configuración con SQL: {e2}")
                return JsonResponse({
                    'success': False,
                    'error': f'Error obteniendo configuración: {str(e2)}',
                    'balance': 0.0,
                    'currency': 'USD',
                    'account_type': 'unknown'
                }, status=500)
        
        if not api_token:
            print("❌ No hay token de API disponible")
            return JsonResponse({
                'success': False,
                'error': 'No hay token de API configurado',
                'balance': 0.0,
                'currency': 'USD',
                'account_type': 'unknown'
            }, status=500)
        
        # Reutilizar cliente compartido global para evitar múltiples conexiones
        global _shared_deriv_client_web
        try:
            _shared_deriv_client_web
        except NameError:
            # Crear cliente compartido solo una vez
            print("🔧 Creando nuevo cliente Deriv compartido")
            _shared_deriv_client_web = DerivClient(api_token=api_token, is_demo=is_demo, app_id=app_id)
        else:
            # Actualizar configuración si cambió
            if (_shared_deriv_client_web.api_token != api_token or 
                _shared_deriv_client_web.is_demo != is_demo or
                _shared_deriv_client_web.app_id != app_id):
                print("🔧 Configuración cambió, recreando cliente")
                # Cerrar conexión anterior si existe
                try:
                    if _shared_deriv_client_web.ws:
                        _shared_deriv_client_web.ws.close()
                except:
                    pass
                # Crear nuevo cliente con nueva configuración
                _shared_deriv_client_web = DerivClient(api_token=api_token, is_demo=is_demo, app_id=app_id)
        
        client = _shared_deriv_client_web
        
        # Verificar estado de conexión antes de obtener balance
        print(f"🔍 Estado del cliente: connected={client.connected}, ws={client.ws is not None}, ws_connected={client.ws.sock.connected if client.ws and client.ws.sock else False}")
        
        # Si no está conectado, intentar autenticar
        if not client.connected or not client.ws or not client.ws.sock or not client.ws.sock.connected:
            print("⚠️ Cliente no conectado, intentando autenticar...")
            if not client.authenticate():
                print("❌ Fallo en autenticación")
                return JsonResponse({
                    'success': False,
                    'error': 'No se pudo conectar/autenticar con Deriv API',
                    'balance': 0.0,
                    'currency': 'USD',
                    'account_type': 'demo' if is_demo else 'real',
                    'connected': False
                }, status=500)
            print("✅ Autenticación exitosa")
        
        balance_info = client.get_balance()
        
        # Verificar si hay error en la respuesta
        if balance_info.get('error'):
            error_msg = balance_info.get('error', 'Error desconocido')
            print(f"❌ Error obteniendo balance: {error_msg}")
            return JsonResponse({
                'success': False,
                'error': str(error_msg),
                'balance': balance_info.get('balance', 0),
                'currency': balance_info.get('currency', 'USD'),
                'account_type': balance_info.get('account_type', 'demo' if is_demo else 'real'),
                'connected': False
            }, status=500)
        
        # Verificar si hay error de rate limit pero hay balance en caché
        if balance_info.get('error_code') == 'RateLimit':
            # Balance está en caché (último conocido)
            print("⚠️ Rate limit alcanzado, usando balance en caché")
            return JsonResponse({
                'success': True,
                'balance': balance_info.get('balance', 0),
                'currency': balance_info.get('currency', 'USD'),
                'account_type': balance_info.get('account_type', 'demo'),
                'cached': True,
                'warning': 'Rate limit alcanzado, mostrando balance en caché',
                'source': balance_info.get('source', 'cache'),
                'connected': True
            })
        
        balance_value = balance_info.get('balance', 0)
        print(f"✅ Balance obtenido: ${balance_value}")
        
        return JsonResponse({
            'success': True,
            'balance': balance_value,
            'currency': balance_info.get('currency', 'USD'),
            'account_type': balance_info.get('account_type', 'demo'),
            'cached': False,
            'connected': True
        })
    except Exception as e:
        print(f"❌ Excepción en get_balance: {e}")
        import traceback
        traceback.print_exc()
        # Si hay error, intentar obtener del último trade
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
                        'warning': f'Error obteniendo balance: {str(e)}, usando último trade conocido'
                    })
        except:
            pass
        
        return JsonResponse({
            'success': False,
            'error': str(e),
            'balance': 0
        }, status=500)


@api_view(['GET'])
def metrics(request):
    """Métricas en tiempo real del sistema"""
    try:
        from datetime import timedelta
        from django.utils import timezone
        
        # Operaciones en las últimas 24 horas
        since_metrics = timezone.now() - timedelta(hours=24)
        recent_trades = OrderAudit.objects.filter(timestamp__gte=since_metrics)
        
        total_trades = recent_trades.count()
        won_trades = recent_trades.filter(status='won').count()
        lost_trades = recent_trades.filter(status='lost').count()
        active_trades = recent_trades.filter(status__in=['pending', 'active']).count()
        
        # P&L total de las últimas 24 horas
        total_pnl = sum(float(t.pnl or 0) for t in recent_trades)
        
        # Win rate
        completed_trades = won_trades + lost_trades
        winrate = (won_trades / completed_trades) if completed_trades > 0 else 0
        
        return JsonResponse({
            'pnl': total_pnl,
            'winrate': winrate,
            'total_trades': total_trades,
            'active_trades': active_trades,
            'won_trades': won_trades,
            'lost_trades': lost_trades
        })
    except Exception as e:
        return JsonResponse({
            'error': str(e),
            'pnl': 0.0,
            'winrate': 0.0,
            'total_trades': 0,
            'active_trades': 0,
            'won_trades': 0,
            'lost_trades': 0
        }, status=500)


@login_required
def capital_config(request):
    """Vista para mostrar y editar configuración de capital"""
    from engine.models import CapitalConfig
    from decimal import Decimal
    
    if request.method == 'POST':
        config = CapitalConfig.get_active()
        
        # Actualizar valores del formulario - Básicos
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
        
        # Configuraciones de Trading (Amounts y Límites)
        config.max_amount_pct_balance = float(request.POST.get('max_amount_pct_balance', '5.0'))
        config.max_amount_absolute = float(request.POST.get('max_amount_absolute', '500.0'))
        config.min_amount_per_trade = float(request.POST.get('min_amount_per_trade', '1.0'))
        config.min_trade_interval_seconds = int(request.POST.get('min_trade_interval_seconds', '60'))
        config.default_duration_forex = int(request.POST.get('default_duration_forex', '900'))
        config.default_duration_metals = int(request.POST.get('default_duration_metals', '300'))
        config.default_duration_indices = int(request.POST.get('default_duration_indices', '30'))
        
        # Límites por símbolo (JSON)
        symbol_limits = {}
        # Recibir límites por símbolo desde el formulario
        for key in request.POST.keys():
            if key.startswith('symbol_limit_'):
                symbol = key.replace('symbol_limit_', '')
                try:
                    limit_value = float(request.POST.get(key))
                    if limit_value > 0:
                        symbol_limits[symbol] = limit_value
                except (ValueError, TypeError):
                    pass
        
        # Si hay símbolos nuevos en el formulario
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
        
        messages.success(request, '✅ Configuración de capital actualizada exitosamente')
        
        # Si es una petición AJAX, retornar JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from django.http import JsonResponse
            return JsonResponse({'success': True, 'message': 'Configuración actualizada exitosamente'})
        
        return redirect('engine:capital-config')
    
    config = CapitalConfig.get_active()
    
    # Obtener estadísticas actuales con Advanced Capital Manager
    from engine.services.advanced_capital_manager import AdvancedCapitalManager
    from connectors.deriv_client import DerivClient
    
    try:
        # Obtener configuración activa para DerivClient
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
        
        # Obtener estadísticas diarias primero
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
        
        # Obtener estadísticas avanzadas
        advanced_stats = advanced_manager.get_advanced_statistics(current_balance)
        
        # Obtener métricas de protección de riesgo
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
        
        # Mensaje de estado con información avanzada
        status_message = f"P&L: ${total_pnl:.2f} | Win Rate: {win_rate:.1f}% | Drawdown: {advanced_stats['drawdown_pct']:.2f}% | VaR: ${advanced_stats['var']['var_usd']:.2f} | Kelly: {advanced_stats['trading_stats']['kelly_percentage']*100:.1f}%"
        if emergency_active:
            status_message += f" | 🚨 EMERGENCIA: {emergency_reason}"
        
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
def trading_config_api(request):
    """API para obtener y guardar configuración de trading"""
    from engine.models import CapitalConfig
    
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
        return JsonResponse({'success': True, 'message': 'Configuración actualizada'})
    
    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)


@login_required
def quick_controls_api(request):
    """API para obtener y actualizar controles rápidos (límites para pruebas)"""
    from engine.models import CapitalConfig
    from decimal import Decimal
    
    if request.method == 'GET':
        # Obtener configuración actual
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
                'message': 'Controles rápidos actualizados exitosamente'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=400)
    
    return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)


@login_required
def services_admin(request):
    """Panel de administración de servicios (trading loop, daphne, gunicorn)"""
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
            
            # Obtener más información con systemctl show
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
            
            # Intentar obtener las últimas líneas del log
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
                    log_lines = tail_result.stdout.strip().split('\n')[-10:]  # Últimas 10 líneas
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
    """API para reiniciar un servicio específico"""
    import subprocess
    import json
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)
    
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
                'message': f'Servicio "{service_key}" no válido'
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
            # Esperar un momento y verificar que se reinició correctamente
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
    """API para obtener los últimos logs de un servicio"""
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
            'message': f'Servicio "{service_key}" no válido'
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
        return JsonResponse({'success': False, 'message': 'Método no permitido'}, status=405)
    
    try:
        data = json.loads(request.body)
        action = data.get('action')  # 'pause' o 'resume'
        
        if action not in ['pause', 'resume']:
            return JsonResponse({
                'success': False,
                'message': 'Acción no válida. Use "pause" o "resume"'
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
            'message': 'Timeout al ejecutar la acción'
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
def active_trades_api(request):
    """API para obtener trades activos/pendientes"""
    try:
        from monitoring.models import OrderAudit
        from django.utils import timezone
        
        # Obtener trades activos/pendientes (incluir también 'rejected' si se muestran como activos temporalmente)
        active_trades = OrderAudit.objects.filter(
            status__in=['pending', 'active']
        ).order_by('-timestamp')[:100]  # Aumentar límite para mostrar más trades
        
        trades_data = []
        for trade in active_trades:
            contract_id = None
            if trade.request_payload:
                contract_id = trade.request_payload.get('contract_id') or trade.request_payload.get('order_id')
            
            trades_data.append({
                'id': trade.id,
                'symbol': trade.symbol,
                'direction': trade.action.upper() if trade.action else 'N/A',
                'price': float(trade.price) if trade.price else 0.0,
                'amount': float(trade.size) if trade.size else 0.0,
                'timestamp': trade.timestamp.isoformat(),
                'status': trade.status,
                'contract_id': contract_id,
                'hours_ago': round((timezone.now() - trade.timestamp).total_seconds() / 3600, 2)
            })
        
        return JsonResponse({
            'success': True,
            'trades': trades_data,
            'count': len(trades_data)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@csrf_exempt
def close_trade_api(request):
    """API para cerrar un trade activo"""
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'Método no permitido'
        }, status=405)
    
    try:
        import json
        from connectors.deriv_client import DerivClient
        from trading_bot.models import DerivAPIConfig
        from monitoring.models import OrderAudit
        
        data = json.loads(request.body)
        contract_id = data.get('contract_id')
        trade_id = data.get('trade_id')
        
        if not contract_id and not trade_id:
            return JsonResponse({
                'success': False,
                'error': 'Se requiere contract_id o trade_id'
            }, status=400)
        
        # Si solo tenemos trade_id, obtener contract_id del trade
        trade = None
        if not contract_id and trade_id:
            try:
                trade = OrderAudit.objects.get(id=trade_id)
                if trade.request_payload:
                    contract_id = trade.request_payload.get('contract_id') or trade.request_payload.get('order_id')
            except OrderAudit.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Trade no encontrado'
                }, status=404)
        
        if not contract_id:
            return JsonResponse({
                'success': False,
                'error': 'No se pudo obtener contract_id'
            }, status=400)
        
        # Obtener configuración de API
        config = DerivAPIConfig.objects.filter(is_active=True).first()
        if not config:
            return JsonResponse({
                'success': False,
                'error': 'No hay configuración de API activa'
            }, status=500)
        
        # Cerrar el contrato
        client = DerivClient(
            api_token=config.api_token,
            is_demo=config.is_demo,
            app_id=config.app_id
        )
        
        result = client.sell_contract(str(contract_id))
        
        if result.get('error'):
            return JsonResponse({
                'success': False,
                'error': result['error']
            }, status=500)
        
        # Actualizar el trade en la base de datos
        if trade_id:
            try:
                if not trade:
                    trade = OrderAudit.objects.get(id=trade_id)
                trade.status = 'won' if result.get('profit', 0) > 0 else 'lost'
                trade.pnl = Decimal(str(result.get('profit', 0)))
                
                # Guardar respuesta de la venta
                if not trade.response_payload:
                    trade.response_payload = {}
                trade.response_payload['sell_result'] = result
                
                trade.save()
            except OrderAudit.DoesNotExist:
                pass
        
        return JsonResponse({
            'success': True,
            'result': result,
            'message': f'Contrato {contract_id} cerrado exitosamente'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@csrf_exempt
def close_all_trades_api(request):
    """API para cerrar todos los trades activos/pendientes"""
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'Método no permitido'
        }, status=405)
    
    try:
        from connectors.deriv_client import DerivClient
        from trading_bot.models import DerivAPIConfig
        from monitoring.models import OrderAudit
        from decimal import Decimal
        
        # Obtener todos los trades activos/pendientes
        active_trades = OrderAudit.objects.filter(
            status__in=['pending', 'active']
        )
        
        if not active_trades.exists():
            return JsonResponse({
                'success': True,
                'message': 'No hay trades activos para cerrar',
                'closed_count': 0,
                'total_pnl': 0
            })
        
        # Obtener configuración de API
        config = DerivAPIConfig.objects.filter(is_active=True).first()
        if not config:
            return JsonResponse({
                'success': False,
                'error': 'No hay configuración de API activa'
            }, status=500)
        
        # Crear cliente Deriv (solo una vez para todos los trades)
        client = DerivClient(
            api_token=config.api_token,
            is_demo=config.is_demo,
            app_id=config.app_id
        )
        
        # Autenticar el cliente una sola vez
        if not client.authenticate():
            return JsonResponse({
                'success': False,
                'error': 'No se pudo autenticar con Deriv API'
            }, status=500)
        
        closed_count = 0
        failed_count = 0
        total_pnl = Decimal('0.00')
        errors = []
        
        # Cerrar cada trade
        total_trades = active_trades.count()
        processed = 0
        
        # Importar time para delays
        import time
        
        for trade in active_trades:
            processed += 1
            contract_id = None
            
            # Intentar obtener contract_id del trade (múltiples formas)
            try:
                # 1. Desde response_payload (múltiples ubicaciones)
                if trade.response_payload:
                    if isinstance(trade.response_payload, dict):
                        # Primero intentar contract_id directo
                        contract_id = trade.response_payload.get('contract_id')
                        
                        # Si no hay, intentar desde objeto 'buy'
                        if not contract_id and 'buy' in trade.response_payload:
                            buy_obj = trade.response_payload.get('buy')
                            if isinstance(buy_obj, dict):
                                contract_id = buy_obj.get('contract_id')
                        
                        # Si aún no hay, usar order_id como fallback (en Deriv a veces son iguales)
                        if not contract_id:
                            contract_id = trade.response_payload.get('order_id')
                
                # 2. Desde request_payload
                if not contract_id and trade.request_payload:
                    if isinstance(trade.request_payload, dict):
                        contract_id = trade.request_payload.get('contract_id') or trade.request_payload.get('order_id')
                
                # 3. Si aún no hay contract_id, marcar como fallido
                if not contract_id:
                    failed_count += 1
                    errors.append(f"Trade {trade.id} ({trade.symbol}): No hay contract_id disponible")
                    # Marcar el trade como "lost" ya que no se puede cerrar
                    try:
                        trade.status = 'lost'
                        trade.pnl = Decimal('0.00')
                        trade.save()
                    except:
                        pass
                    continue
                
                # Cerrar el contrato
                # Intentar cerrar el contrato
                result = client.sell_contract(str(contract_id))
                
                if result.get('error'):
                    failed_count += 1
                    error_msg = result.get('error', {}).get('message', str(result.get('error'))) if isinstance(result.get('error'), dict) else str(result.get('error'))
                    errors.append(f"Trade {trade.id} ({trade.symbol}): {error_msg}")
                    
                    # Si el error es que el contrato no existe o ya expiró, marcar como lost
                    error_str = str(error_msg).lower()
                    if any(keyword in error_str for keyword in ['not found', 'expired', 'invalid', 'does not exist']):
                        try:
                            trade.status = 'lost'
                            trade.pnl = Decimal('0.00')
                            if not trade.response_payload:
                                trade.response_payload = {}
                            trade.response_payload['sell_error'] = result.get('error')
                            trade.save()
                        except:
                            pass
                    continue
                
                # Actualizar el trade en la base de datos
                profit = Decimal(str(result.get('profit', 0)))
                trade.status = 'won' if profit > 0 else 'lost'
                trade.pnl = profit
                
                if not trade.response_payload:
                    trade.response_payload = {}
                trade.response_payload['sell_result'] = result
                
                trade.save()
                
                closed_count += 1
                total_pnl += profit
                
                # Pequeño delay para evitar rate limiting
                time.sleep(0.2)
                
            except Exception as e:
                failed_count += 1
                error_msg = str(e)
                errors.append(f"Trade {trade.id} ({trade.symbol}): {error_msg}")
                # Intentar marcar como lost si hay error
                try:
                    trade.status = 'lost'
                    trade.pnl = Decimal('0.00')
                    trade.save()
                except:
                    pass
        
        # Mensaje final
        if closed_count > 0:
            message = f'Cerrados {closed_count} trades exitosamente'
        elif failed_count > 0:
            message = f'No se pudieron cerrar los trades ({failed_count} fallidos)'
        else:
            message = 'No había trades para cerrar'
        
        return JsonResponse({
            'success': True,
            'message': message,
            'closed_count': closed_count,
            'failed_count': failed_count,
            'total_count': total_trades,
            'total_pnl': float(total_pnl),
            'errors': errors[:20] if errors else None  # Limitar a 20 errores para no saturar
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@csrf_exempt
def mark_all_expired_api(request):
    """API para marcar todos los trades activos/pendientes como expirados/perdidos (sin intentar cerrarlos en Deriv)"""
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'Método no permitido'
        }, status=405)
    
    try:
        from monitoring.models import OrderAudit
        from decimal import Decimal
        from django.utils import timezone
        
        # Obtener todos los trades activos/pendientes
        active_trades = OrderAudit.objects.filter(
            status__in=['pending', 'active']
        )
        
        if not active_trades.exists():
            return JsonResponse({
                'success': True,
                'message': 'No hay trades activos para marcar',
                'marked_count': 0,
                'total_pnl': 0
            })
        
        marked_count = 0
        total_pnl = Decimal('0.00')
        
        # Marcar cada trade como "lost" (expirado/perdido)
        for trade in active_trades:
            try:
                # Calcular P&L aproximado (negativo ya que se marca como perdido)
                # Si hay amount en response_payload, usar ese como pérdida aproximada
                loss_amount = Decimal('0.00')
                if trade.response_payload:
                    amount = trade.response_payload.get('amount') or trade.response_payload.get('risk_amount')
                    if amount:
                        loss_amount = -Decimal(str(amount))
                elif trade.request_payload:
                    # Intentar obtener amount desde request_payload
                    position_sizing = trade.request_payload.get('position_sizing', {})
                    if position_sizing:
                        amount = position_sizing.get('risk_amount') or position_sizing.get('amount')
                        if amount:
                            loss_amount = -Decimal(str(amount))
                    else:
                        amount = trade.request_payload.get('amount') or trade.request_payload.get('stake')
                        if amount:
                            loss_amount = -Decimal(str(amount))
                elif trade.size:
                    # Usar el campo size del modelo
                    loss_amount = -Decimal(str(trade.size))
                
                # Marcar como perdido
                trade.status = 'lost'
                trade.pnl = loss_amount
                
                # Guardar información adicional
                if not trade.response_payload:
                    trade.response_payload = {}
                trade.response_payload['marked_as_expired'] = True
                trade.response_payload['marked_at'] = timezone.now().isoformat()
                
                trade.save()
                
                marked_count += 1
                total_pnl += loss_amount
                
            except Exception as e:
                # Si hay error con un trade específico, continuar con los demás
                print(f"Error marcando trade {trade.id}: {e}")
                continue
        
        return JsonResponse({
            'success': True,
            'message': f'Marcados {marked_count} trades como expirados/perdidos',
            'marked_count': marked_count,
            'total_pnl': float(total_pnl)
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@csrf_exempt
def clear_completed_trades_api(request):
    """API para limpiar todas las operaciones finalizadas y resetear métricas"""
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'Método no permitido'
        }, status=405)
    
    try:
        from monitoring.models import OrderAudit
        
        # Eliminar todas las operaciones finalizadas (won, lost, rejected)
        deleted_count = OrderAudit.objects.filter(
            status__in=['won', 'lost', 'rejected', 'expired']
        ).delete()[0]
        
        return JsonResponse({
            'success': True,
            'message': f'Se eliminaron {deleted_count} operaciones finalizadas',
            'deleted_count': deleted_count
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

