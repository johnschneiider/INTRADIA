from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import render
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
    """Obtener balance de Deriv"""
    try:
        from connectors.deriv_client import DerivClient
        
        client = DerivClient()
        balance_info = client.get_balance()
        
        return JsonResponse({
            'success': True,
            'balance': balance_info.get('balance', 0),
            'currency': balance_info.get('currency', 'USD'),
            'account_type': balance_info.get('account_type', 'demo')
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@api_view(['GET'])
def get_trades(request):
    """Obtener operaciones activas y finalizadas"""
    try:
        from datetime import timedelta
        from django.utils import timezone
        
        # Operaciones en las últimas 30 minutos
        since = timezone.now() - timedelta(minutes=30)
        
        trades = OrderAudit.objects.filter(
            timestamp__gte=since
        ).order_by('-timestamp')[:100]
        
        active = []
        completed = []
        
        for trade in trades:
            trade_data = {
                'id': trade.id,
                'symbol': trade.symbol,
                'direction': trade.action.upper(),
                'price': float(trade.price),
                'timestamp': trade.timestamp.isoformat(),
                'status': trade.status
            }
            
            if trade.status == 'pending':
                active.append(trade_data)
            else:
                completed.append(trade_data)
        
        # MÉTRICAS: Operaciones en las últimas 24 horas
        since_metrics = timezone.now() - timedelta(hours=24)
        recent_trades = OrderAudit.objects.filter(timestamp__gte=since_metrics)
        
        total_trades = recent_trades.count()
        won_trades = recent_trades.filter(status='won').count()
        lost_trades = recent_trades.filter(status='lost').count()
        active_trades = recent_trades.filter(status__in=['pending', 'active']).count()
        
        # P&L total de las últimas 24 horas
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
    """Métricas en tiempo real del sistema"""
    try:
        # Obtener órdenes de la base de datos
        orders = OrderAudit.objects.all()
        
        # Calcular métricas
        total_trades = orders.count()
        won_trades = orders.filter(status='won').count()
        lost_trades = orders.filter(status='lost').count()
        active_trades = orders.filter(status='active').count()
        
        # P&L total
        total_pnl = sum(float(order.pnl or 0) for order in orders)
        
        # Tasa de acierto
        completed_trades = won_trades + lost_trades
        win_rate = (won_trades / completed_trades) if completed_trades > 0 else 0
        
        # Drawdown máximo
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
            'trades_per_hour': total_trades / 24,  # Aproximación
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
    """Exponer métricas para Prometheus"""
    # TODO: Implementar métricas reales de Prometheus
    return Response({
        'intradia_pnl_total': 0.0,
        'intradia_trades_total': 0,
        'intradia_active_trades': 0,
        'intradia_winrate': 0.0,
        'intradia_max_drawdown_pct': 0.0,
    })


@api_view(['POST', 'GET'])
def orders(request):
    """Manejar órdenes: POST para crear, GET para listar"""
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
            
            # Ejecutar a través del gateway
            result = place_order_through_gateway(order_req)
            
            if result['accepted']:
                # Registrar en auditoría
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
        """Listar órdenes recientes"""
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
    """Promover política de RL de shadow a active"""
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
    """Obtener datos de velas para el gráfico"""
    from market.models import Candle
    
    symbol = request.GET.get('symbol', 'EURUSD')
    timeframe = request.GET.get('timeframe', '1h')
    limit = int(request.GET.get('limit', 100))
    
    # Obtener velas de la base de datos
    candles_qs = Candle.objects.filter(
        symbol=symbol, 
        timeframe=timeframe
    ).order_by('-timestamp')[:limit]
    
    # Convertir a formato para el gráfico
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
    
    # Obtener ticks más recientes
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
    """Test de conexión con Deriv API"""
    try:
        from connectors.deriv_client import DerivClient
        
        client = DerivClient()
        authenticated = client.authenticate()
        
        if authenticated:
            balance_info = client.get_balance()
            return Response({
                'connected': True,
                'authenticated': True,
                'balance': balance_info,
                'message': 'Conexión exitosa con Deriv'
            })
        else:
            return Response({
                'connected': False,
                'authenticated': False,
                'message': 'Error de autenticación con Deriv'
            }, status=400)
            
    except Exception as e:
        return Response({
            'connected': False,
            'error': str(e),
            'message': 'Error de conexión con Deriv'
        }, status=500)


def dashboard(request):
    """Renderizar el dashboard principal con precios en tiempo real"""
    return render(request, 'dashboard_precios_realtime_v2.html')