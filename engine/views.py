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
        except Exception as e:
            print(f"⚠️ Error al obtener configuración en get_balance: {e}")
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
                print(f"⚠️ Error al obtener configuración con SQL: {e2}")
                pass  # Usar defaults si no hay configuración
        
        # Reutilizar cliente compartido global para evitar múltiples conexiones
        global _shared_deriv_client_web
        try:
            _shared_deriv_client_web
        except NameError:
            # Crear cliente compartido solo una vez
            _shared_deriv_client_web = DerivClient(api_token=api_token, is_demo=is_demo, app_id=app_id)
        else:
            # Actualizar configuración si cambió
            if (_shared_deriv_client_web.api_token != api_token or 
                _shared_deriv_client_web.is_demo != is_demo or
                _shared_deriv_client_web.app_id != app_id):
                # Cerrar conexión anterior si existe
                try:
                    if _shared_deriv_client_web.ws:
                        _shared_deriv_client_web.ws.close()
                except:
                    pass
                # Crear nuevo cliente con nueva configuración
                _shared_deriv_client_web = DerivClient(api_token=api_token, is_demo=is_demo, app_id=app_id)
        
        client = _shared_deriv_client_web
        balance_info = client.get_balance()
        
        # Verificar si hay error de rate limit pero hay balance en caché
        if balance_info.get('error_code') == 'RateLimit':
            # Balance está en caché (último conocido)
            return JsonResponse({
                'success': True,
                'balance': balance_info.get('balance', 0),
                'currency': balance_info.get('currency', 'USD'),
                'account_type': balance_info.get('account_type', 'demo'),
                'cached': True,
                'warning': 'Rate limit alcanzado, mostrando balance en caché',
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
        }, status=500)#   F u n c i o n e s   a d i c i o n a l e s   p a r a   g e s t i � � n   d e   t r a d e s   a c t i v o s  
 #   E s t a s   f u n c i o n e s   s e   a g r e g a r � � n   a l   f i n a l   d e   e n g i n e / v i e w s . p y  
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
                         ' e r r o r ' :   ' M � � t o d o   n o   p e r m i t i d o '  
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
                 #   O b t e n e r   c o n f i g u r a c i � � n   d e   A P I  
                 c o n f i g   =   D e r i v A P I C o n f i g . o b j e c t s . f i l t e r ( i s _ a c t i v e = T r u e ) . f i r s t ( )  
                 i f   n o t   c o n f i g :  
                         r e t u r n   J s o n R e s p o n s e ( {  
                                 ' s u c c e s s ' :   F a l s e ,  
                                 ' e r r o r ' :   ' N o   h a y   c o n f i g u r a c i � � n   d e   A P I   a c t i v a '  
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