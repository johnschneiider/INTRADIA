"""
Comando para ejecutar el trading loop directamente
Evita problemas de Celery en Windows
"""
import time
import json
from django.core.management.base import BaseCommand
from engine.services.tick_trading_loop import TickTradingLoop
from engine.services.capital_manager import CapitalManager
from market.models import Tick
from monitoring.models import OrderAudit
from django.utils import timezone
from datetime import timedelta
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from decimal import Decimal


class Command(BaseCommand):
    help = 'Ejecuta el loop de trading cada 2 segundos'

    def handle(self, *args, **options):
        from connectors.deriv_client import DerivClient
        import os
        
        # Usar estrategia estadística híbrida (NUEVA)
        use_statistical = True
        
        loop = TickTradingLoop(use_statistical=use_statistical)
        channel_layer = get_channel_layer()
        
        # Obtener configuración de API desde la BD
        try:
            from trading_bot.models import DerivAPIConfig
            # Debug: ver todas las configuraciones
            all_configs = DerivAPIConfig.objects.all()
            print(f"🔍 DEBUG: Total configuraciones en BD: {all_configs.count()}")
            for c in all_configs:
                print(f"  - User: {c.user.username}, Active: {c.is_active}, Token: {c.api_token[:10]}...")
            
            api_config = DerivAPIConfig.objects.filter(is_active=True).only('api_token', 'is_demo', 'app_id').first()
            print(f"🔍 DEBUG: Config activa encontrada: {api_config}")
            
            if api_config:
                print(f"✅ Usando token: {api_config.api_token[:10]}...")
                client = DerivClient(
                    api_token=api_config.api_token,
                    is_demo=api_config.is_demo,
                    app_id=api_config.app_id
                )
            else:
                raise ValueError("No hay configuración de API activa. Configura tu token en: http://localhost:8000/trading/config/api/")
        except Exception as e:
            print(f"❌ Error al inicializar DerivClient: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        # Configurar Capital Manager desde la base de datos o variables de entorno
        try:
            from engine.models import CapitalConfig
            config = CapitalConfig.get_active()
            profit_target = config.profit_target
            max_loss = config.max_loss
            max_trades = config.max_trades
            profit_target_pct = config.profit_target_pct
            max_loss_pct = config.max_loss_pct
            protect_profits = config.protect_profits
            profit_protection_pct = config.profit_protection_pct
            # Nuevos controles rápidos
            disable_max_trades = config.disable_max_trades
            disable_profit_target = config.disable_profit_target
            stop_loss_amount = config.stop_loss_amount
            self.stdout.write(self.style.SUCCESS('✅ Configuración cargada desde base de datos'))
        except Exception as e:
            # Fallback a variables de entorno si no hay configuración en BD
            self.stdout.write(self.style.WARNING(f'⚠️ Usando valores por defecto: {e}'))
            profit_target = Decimal(os.getenv('DAILY_PROFIT_TARGET', '100.00'))
            max_loss = Decimal(os.getenv('DAILY_MAX_LOSS', '-50.00'))
            max_trades = int(os.getenv('DAILY_MAX_TRADES', '50'))
            profit_target_pct = float(os.getenv('DAILY_PROFIT_TARGET_PCT', '5.0'))
            max_loss_pct = float(os.getenv('DAILY_MAX_LOSS_PCT', '1.0'))
            protect_profits = True
            profit_protection_pct = 0.5
            disable_max_trades = False
            disable_profit_target = False
            stop_loss_amount = Decimal('0.00')
        
        # Aplicar controles rápidos
        # FORZAR ILIMITADO: sin límite de trades diarios
        max_trades = 999999
        self.stdout.write(self.style.WARNING('⚠️ Límite de trades DESACTIVADO (ilimitado)'))
        
        if disable_profit_target:
            profit_target = Decimal('999999.00')  # Prácticamente ilimitado
            profit_target_pct = 999.0
            self.stdout.write(self.style.WARNING('⚠️ Meta de ganancia DESACTIVADA (modo pruebas)'))
        
        # Si hay stop_loss_amount configurado, usarlo como max_loss
        if stop_loss_amount > 0:
            max_loss = -abs(stop_loss_amount)  # Negativo porque es pérdida
            self.stdout.write(self.style.WARNING(f'⚠️ Stop Loss por monto activado: ${stop_loss_amount}'))
        
        capital_manager = CapitalManager(
            profit_target=profit_target,
            max_loss=max_loss,
            max_trades=max_trades,
            profit_target_pct=profit_target_pct,
            max_loss_pct=max_loss_pct,
            protect_profits=protect_profits,
            profit_protection_pct=profit_protection_pct
        )
        
        self.stdout.write(self.style.SUCCESS('🚀 Iniciando trading loop...'))
        if use_statistical:
            self.stdout.write(self.style.SUCCESS('📊 Estrategia: ESTADÍSTICA HÍBRIDA (Mean Reversion + Momentum)'))
        else:
            self.stdout.write(self.style.SUCCESS('📊 Estrategia: TICK-BASED (tendencia simple)'))
        self.stdout.write(self.style.SUCCESS('📊 Analizando todos los símbolos cada 2 segundos'))
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('💰 GESTOR DE CAPITAL ACTIVO:'))
        self.stdout.write(self.style.SUCCESS(f'   • Meta de ganancia: ${profit_target} o {profit_target_pct}%'))
        self.stdout.write(self.style.SUCCESS(f'   • Pérdida máxima: ${max_loss} o {max_loss_pct}%'))
        self.stdout.write(self.style.SUCCESS(f'   • Máximo trades/día: {max_trades}'))
        self.stdout.write(self.style.SUCCESS('   • Protección de ganancias: ACTIVA'))
        self.stdout.write('')
        
        try:
            recovery_mode = False
            while True:
                # Recargar configuración desde BD en cada iteración (para aplicar cambios dinámicos)
                try:
                    from engine.models import CapitalConfig
                    config = CapitalConfig.get_active()
                    
                    # Aplicar controles rápidos
                    effective_max_trades = config.max_trades
                    effective_profit_target = config.profit_target
                    effective_profit_target_pct = config.profit_target_pct
                    effective_max_loss = config.max_loss
                    
                    # FORZAR ILIMITADO: siempre sin límite
                    effective_max_trades = 999999
                    if config.disable_profit_target:
                        effective_profit_target = Decimal('999999.00')
                        effective_profit_target_pct = 999.0
                    # Si hay stop_loss_amount configurado, tiene PRIORIDAD sobre max_loss
                    # Esto permite controlar el stop loss independientemente de otros límites
                    if config.stop_loss_amount > 0:
                        effective_max_loss = -abs(config.stop_loss_amount)
                    
                    # Actualizar configuración si cambió (max_trades siempre ilimitado)
                    if (capital_manager.targets.profit_target != effective_profit_target or
                        capital_manager.targets.max_loss != effective_max_loss):
                        capital_manager.targets.profit_target = effective_profit_target
                        capital_manager.targets.max_loss = effective_max_loss
                        capital_manager.targets.max_trades = 999999  # Siempre ilimitado
                        capital_manager.targets.profit_target_pct = effective_profit_target_pct
                        # Si stop_loss_amount está activo, desactivar max_loss_pct para evitar conflictos
                        if config.stop_loss_amount > 0:
                            capital_manager.max_loss_pct = None  # Desactivar porcentaje cuando stop_loss_amount está activo
                        else:
                            capital_manager.max_loss_pct = config.max_loss_pct
                        capital_manager.protect_profits = config.protect_profits
                        capital_manager.profit_protection_pct = config.profit_protection_pct
                        self.stdout.write(self.style.SUCCESS('🔄 Configuración de capital actualizada'))
                except Exception:
                    pass  # Continuar con configuración actual si hay error
                
                # Verificar si debe detenerse por metas diarias
                current_balance = Decimal(str(client.get_balance().get('balance', 0)))
                
                can_trade, reason = capital_manager.can_trade(current_balance)
                
                if not can_trade:
                    # Activar modo recuperación en vez de detener
                    recovery_mode = True
                    self.stdout.write('=' * 60)
                    self.stdout.write(self.style.WARNING(f'🟡 MODO RECUPERACIÓN: {reason}'))
                    self.stdout.write(self.style.SUCCESS('Operando solo con símbolos fuertes y mayor confianza hasta recuperarse'))
                    self.stdout.write('=' * 60)
                
                # Mostrar estado del Capital Manager
                status_msg = capital_manager.get_status_message(current_balance)
                self.stdout.write(self.style.SUCCESS(status_msg))
                
                # Obtener símbolos con ticks recientes - PROCESA TODOS LOS ACTIVOS
                since = timezone.now() - timedelta(hours=24)
                symbols = Tick.objects.filter(
                    timestamp__gte=since
                ).values_list('symbol', flat=True).distinct()
                
                # Si no hay símbolos en BD, usar active_symbols.json como fallback
                if not symbols:
                    import os
                    import json
                    active_symbols_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'active_symbols.json')
                    if os.path.exists(active_symbols_path):
                        try:
                            with open(active_symbols_path, 'r') as f:
                                data = json.load(f)
                                symbols = data.get('active_symbols', [])
                                self.stdout.write(self.style.WARNING(f'⚠️ No hay ticks en BD, usando {len(symbols)} símbolos de active_symbols.json'))
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f'❌ Error cargando active_symbols.json: {e}'))
                            symbols = []
                
                # Filtrar símbolos no operables (Crypto/OTC y BOOM/CRASH no ofrecidos en esta cuenta)
                excluded_symbols = [
                    s for s in list(symbols)
                    if s.startswith('cry') or s.startswith('OTC') or s.startswith('BOOM') or s.startswith('CRASH')
                ]
                symbols_list = [s for s in list(symbols) if s not in excluded_symbols]
                
                # PRIORIZACIÓN DINÁMICA POR RENDIMIENTO (última hora)
                def _compute_symbol_scores(candidates):
                    from monitoring.models import OrderAudit
                    horizon = timezone.now() - timedelta(hours=1)
                    base_scores = {}
                    # Pre-cargar trades por símbolo
                    trades = OrderAudit.objects.filter(timestamp__gte=horizon, symbol__in=candidates, status__in=['won','lost'])
                    by_symbol = {}
                    for t in trades:
                        by_symbol.setdefault(t.symbol, []).append(t)
                    # Calcular score: 0..1 combinando winrate y pnl normalizado
                    # pnl_norm: tanh(pnl/5) mapea ganancias moderadas hacia ±1 suavemente
                    import math
                    for s in candidates:
                        ts = by_symbol.get(s, [])
                        if not ts:
                            base_scores[s] = 0.5  # neutral si no hay datos
                            continue
                        wins = sum(1 for x in ts if x.status == 'won')
                        losses = sum(1 for x in ts if x.status == 'lost')
                        total = wins + losses
                        winrate = (wins/total) if total > 0 else 0.5
                        pnl = sum(float(x.pnl or 0) for x in ts)
                        pnl_norm = math.tanh(pnl / 5.0)
                        # mezcla ponderada
                        score = 0.7*winrate + 0.3*((pnl_norm+1)/2)  # pnl_norm (-1..1) -> (0..1)
                        base_scores[s] = max(0.0, min(1.0, score))
                    return base_scores

                symbol_scores = _compute_symbol_scores(list(symbols_list))
                # Reordenar por score desc
                symbols_list = sorted(symbols_list, key=lambda s: symbol_scores.get(s, 0.5), reverse=True)

                # En modo recuperación: concentrarse en los mejores
                if recovery_mode:
                    # filtrar a ganadores (score>=0.60) y limitar a top 12
                    winners = [s for s in symbols_list if symbol_scores.get(s, 0) >= 0.60]
                    symbols_list = (winners or symbols_list)[:12]

                # Publicar prioridades al loop para intervalos dinámicos
                try:
                    loop.symbol_priorities = symbol_scores
                    loop.recovery_mode = recovery_mode
                except Exception:
                    pass

                self.stdout.write('=' * 60)
                self.stdout.write(f'📊 Símbolos encontrados: {len(symbols_list)}')
                if symbols_list:
                    self.stdout.write(f'   Lista: {symbols_list[:10]}...' if len(symbols_list) > 10 else f'   Lista: {symbols_list}')
                else:
                    self.stdout.write(self.style.WARNING('   ⚠️ NO HAY SÍMBOLOS PARA PROCESAR'))
                    self.stdout.write(self.style.WARNING('   Verifica que save_ticks esté corriendo o que active_symbols.json exista'))
                self.stdout.write('')
                
                # Monitorear posiciones activas ANTES de procesar nuevos trades
                try:
                    from engine.services.position_monitor import PositionMonitor
                    from engine.services.risk_protection import RiskProtectionSystem
                    from engine.models import CapitalConfig
                    
                    config = CapitalConfig.get_active()
                    risk_protection = RiskProtectionSystem(
                        max_portfolio_risk_pct=getattr(config, 'max_portfolio_risk_pct', 15.0),
                        max_position_duration_minutes=getattr(config, 'max_position_duration_minutes', 60),
                        close_losing_positions_after_minutes=getattr(config, 'close_losing_positions_after_minutes', 30),
                        enable_trailing_stop=getattr(config, 'enable_trailing_stop', True),
                        trailing_stop_distance_pct=getattr(config, 'trailing_stop_distance_pct', 1.0),
                        min_profit_for_trailing_pct=getattr(config, 'min_profit_for_trailing_pct', 0.5),
                        emergency_drawdown_threshold_pct=getattr(config, 'emergency_drawdown_threshold_pct', 10.0),
                        # Permitir alta simultaneidad
                        max_active_positions=max(50, getattr(config, 'max_active_positions', 10)),
                    )
                    monitor = PositionMonitor(risk_protection)
                    position_actions = monitor.monitor_active_positions()
                    
                    if position_actions:
                        for action in position_actions:
                            if action.get('action') == 'closed_by_time':
                                self.stdout.write(
                                    self.style.WARNING(f'  ⏰ {action.get("symbol")}: Cierre por tiempo - {action.get("reason")}')
                                )
                            elif action.get('action') == 'contract_expired':
                                # Actualizar martingala cuando un contrato expira
                                try:
                                    if loop.capital_manager:
                                        trade_won = action.get('status') == 'won'
                                        trade_symbol = action.get('symbol')
                                        # Obtener monto del trade desde action si está disponible
                                        trade_amount = action.get('amount')
                                        if trade_amount:
                                            trade_amount = Decimal(str(trade_amount))
                                        else:
                                            trade_amount = None
                                        loop.capital_manager.update_martingale_level(trade_won, trade_amount)
                                        
                                        # Si es un trade ganador del símbolo permitido durante pausa, romper la pausa
                                        if trade_won and loop.adaptive_filter_manager.pause_active:
                                            allowed_symbol = loop.adaptive_filter_manager.pause_allowed_symbol
                                            if trade_symbol == allowed_symbol:
                                                # Recalcular métricas para verificar si la racha se rompió
                                                try:
                                                    balance_info = loop._client.get_balance() if loop._client else None
                                                    if isinstance(balance_info, dict):
                                                        current_balance = Decimal(str(balance_info.get('balance', 0)))
                                                    else:
                                                        current_balance = Decimal(str(balance_info)) if balance_info else Decimal('0')
                                                    
                                                    new_metrics = loop.adaptive_filter_manager.calculate_metrics(current_balance)
                                                    # Si la racha perdedora se rompió, desactivar pausa
                                                    if new_metrics.losing_streak < 5:
                                                        loop.adaptive_filter_manager.pause_active = False
                                                        loop.adaptive_filter_manager.pause_allowed_symbol = None
                                                        self.stdout.write(
                                                            self.style.SUCCESS(f'✅ Pausa rota: {trade_symbol} ganó (Racha: {new_metrics.losing_streak})')
                                                        )
                                                except Exception:
                                                    pass  # No detener si falla verificación
                                except Exception:
                                    pass  # No detener si falla actualización de martingala
                    
                    # Verificar trades recientemente completados para actualizar martingala
                    try:
                        from monitoring.models import OrderAudit
                        
                        # Buscar trades que cambiaron de pending a won/lost en los últimos minutos
                        recent_time = timezone.now() - timedelta(minutes=2)
                        completed_trades = OrderAudit.objects.filter(
                            timestamp__gte=recent_time,
                            status__in=['won', 'lost']
                        ).order_by('-timestamp')[:10]
                        
                        if loop.capital_manager and completed_trades.exists():
                            for trade in completed_trades:
                                # Actualizar martingala por cada trade completado
                                trade_won = trade.status == 'won'
                                trade_symbol = trade.symbol
                                
                                # Si es un trade ganador del símbolo permitido durante pausa, verificar si rompe la pausa
                                if trade_won and loop.adaptive_filter_manager.pause_active:
                                    allowed_symbol = loop.adaptive_filter_manager.pause_allowed_symbol
                                    if trade_symbol == allowed_symbol:
                                        # Recalcular métricas para verificar si la racha se rompió
                                        try:
                                            balance_info = loop._client.get_balance() if loop._client else None
                                            if isinstance(balance_info, dict):
                                                current_balance = Decimal(str(balance_info.get('balance', 0)))
                                            else:
                                                current_balance = Decimal(str(balance_info)) if balance_info else Decimal('0')
                                            
                                            new_metrics = loop.adaptive_filter_manager.calculate_metrics(current_balance)
                                            # Si la racha perdedora se rompió, desactivar pausa
                                            if new_metrics.losing_streak < 5:
                                                loop.adaptive_filter_manager.pause_active = False
                                                loop.adaptive_filter_manager.pause_allowed_symbol = None
                                                self.stdout.write(
                                                    self.style.SUCCESS(f'✅ Pausa rota: {trade_symbol} ganó (Racha: {new_metrics.losing_streak})')
                                                )
                                        except Exception:
                                            pass  # No detener si falla verificación
                                
                                # Obtener monto del trade desde request_payload o response_payload
                                trade_amount = None
                                if trade.request_payload:
                                    # Buscar amount en request_payload
                                    trade_amount = trade.request_payload.get('amount')
                                if not trade_amount and trade.response_payload:
                                    # Buscar amount en response_payload
                                    trade_amount = trade.response_payload.get('amount')
                                if not trade_amount and trade.size:
                                    # Usar size si está disponible
                                    trade_amount = trade.size
                                
                                if trade_amount:
                                    trade_amount = Decimal(str(trade_amount))
                                else:
                                    # Si no se encuentra el amount, usar 0 (no acumular)
                                    trade_amount = None
                                
                                loop.capital_manager.update_martingale_level(trade_won, trade_amount)
                    except Exception:
                        pass  # No detener si falla
                except Exception:
                    pass  # No detener si falla monitoreo
                
                # Procesar cada símbolo
                executed_count = 0
                skipped_count = 0
                rejected_count = 0
                
                if not symbols_list:
                    self.stdout.write(self.style.WARNING('⚠️ No hay símbolos para procesar. Esperando ticks...'))
                else:
                    self.stdout.write(self.style.SUCCESS(f'🔄 Procesando {len(symbols_list)} símbolos...'))
                
                for symbol in symbols_list:
                    try:
                        self.stdout.write(f'   🔍 Analizando {symbol}...', ending='')
                        result = loop.process_symbol(symbol)
                        
                        if not result:
                            self.stdout.write(' ⏭️ Sin resultado')
                            skipped_count += 1
                            continue
                        
                        status = result.get('status')
                        self.stdout.write(f' → {status}')
                        
                        if status == 'executed':
                            executed_count += 1
                            signal_info = result.get("signal", {})
                            pos_info = result.get("position_size", {})
                            
                            method = pos_info.get("method", "N/A")
                            risk = pos_info.get("risk_amount", 0)
                            
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'  ✅ {symbol} {signal_info.get("direction")} | Método: {method} | Riesgo: ${risk:.2f}'
                                )
                            )
                            
                            if pos_info.get("protections_applied"):
                                self.stdout.write(
                                    self.style.WARNING(f'     🛡️ {pos_info.get("protections_applied")}')
                                )
                            
                            # Enviar actualización WebSocket a la plantilla
                            try:
                                # Obtener última operación
                                last_trade = OrderAudit.objects.filter(
                                    symbol=symbol,
                                    accepted=True
                                ).order_by('-timestamp').first()
                                
                                if last_trade:
                                    # Enviar mensaje al grupo de WebSocket
                                    async_to_sync(channel_layer.group_send)(
                                        'trading_updates',
                                        {
                                            'type': 'trading_update',
                                            'message': {
                                                'trade_executed': True,
                                                'symbol': symbol,
                                                'direction': last_trade.action,
                                                'order_id': last_trade.request_payload.get('order_id') if last_trade.request_payload else None,
                                                'status': 'pending'
                                            }
                                        }
                                    )
                            except Exception as e:
                                pass  # Error silencioso
                        elif status == 'skipped':
                            skipped_count += 1
                            # No mostrar logs de símbolos omitidos (para reducir spam)
                            # Solo mostrar si hay algún problema específico
                            if result.get('reason') not in ['no_clear_trend', 'insufficient_confidence', 'not_available', 'rate_limit']:
                                self.stdout.write(
                                    self.style.WARNING(f'  ⏭️ {symbol}: {result.get("reason", "omitido")}')
                                )
                        elif status == 'rejected':
                            rejected_count += 1
                            # Mostrar rechazos solo si son importantes (balance, riesgo, etc.)
                            reason = result.get('reason', '')
                            if reason not in ['interval_limit', 'waiting']:
                                self.stdout.write(
                                    self.style.ERROR(f'  ❌ {symbol}: {reason}')
                                )
                        elif status == 'error':
                            self.stdout.write(
                                self.style.ERROR(f'  ❌ {symbol}: Error - {result.get("error", "unknown")}')
                            )
                    except Exception as e:
                        import traceback
                        error_msg = f'  ❌ Error en {symbol}: {type(e).__name__}: {e}'
                        self.stdout.write(self.style.ERROR(error_msg))
                        
                        # Log completo para debugging
                        import logging
                        logger = logging.getLogger('trading_loop')
                        logger.error(f"Error procesando símbolo {symbol}: {traceback.format_exc()}")
                        
                        # Si es un error crítico de BD, hacer pausa breve antes de continuar
                        from django.db import OperationalError, DatabaseError
                        if isinstance(e, (OperationalError, DatabaseError)):
                            self.stdout.write(self.style.WARNING('  ⏸️ Pausa breve por error de BD...'))
                            time.sleep(2)  # Pausa breve para que BD se recupere
                        
                        # Continuar con siguiente símbolo - no detener el loop
                        continue
                
                # Siempre mostrar resumen para diagnóstico
                self.stdout.write('')
                self.stdout.write(
                    self.style.SUCCESS(f'📊 Resumen: {executed_count} ejecutados, {rejected_count} rechazados, {skipped_count} omitidos')
                )
                self.stdout.write('')
                
                # Verificar operaciones pendientes (cada 2 segundos)
                self._check_pending_trades(client)
                
                # Verificar nuevamente si se alcanzó alguna meta después de procesar trades
                current_balance = Decimal(str(client.get_balance().get('balance', 0)))
                can_trade, reason = capital_manager.can_trade(current_balance)
                
                if not can_trade:
                    # Mantenerse en modo recuperación sin detener el loop
                    recovery_mode = True
                    self.stdout.write(self.style.WARNING(f'🟡 MODO RECUPERACIÓN (continúa): {reason}'))
                
                # VERIFICAR CONTRATOS PENDIENTES/ACTIVOS cada ciclo (cada ~10 segundos)
                # Esto previene que se queden "pegados"
                try:
                    if client:
                        self._check_pending_trades(client)
                except Exception as e:
                    # No detener el loop si falla la verificación
                    pass
                
                # Verificar trades huérfanos (cada 5 minutos aproximadamente)
                # Trades que se ejecutaron en Deriv pero no están en BD
                if not hasattr(self, '_last_orphan_check') or (timezone.now() - self._last_orphan_check).total_seconds() > 300:
                    try:
                        self._check_orphaned_trades(client)
                        self._last_orphan_check = timezone.now()
                    except Exception as e:
                        # No detener el loop si falla la verificación
                        pass
                
                self.stdout.write('=' * 60)
                self.stdout.write('')
                
                # Esperar 10 segundos (aumentado de 5 a 10 para reducir rate limit aún más)
                time.sleep(10)
                
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS('\n\n⚠️  Deteniendo trading loop...'))
            return
        except Exception as e:
            # Capturar cualquier error no manejado para evitar crash del servidor
            import traceback
            import logging
            logger = logging.getLogger('trading_loop')
            
            error_msg = f"❌ ERROR CRÍTICO NO MANEJADO en trading loop: {type(e).__name__}: {e}"
            self.stdout.write(self.style.ERROR(error_msg))
            logger.critical(f"{error_msg}\n{traceback.format_exc()}")
            
            # Esperar antes de reintentar para evitar loops infinitos de errores
            self.stdout.write(self.style.WARNING('⏸️ Esperando 30 segundos antes de reintentar...'))
            time.sleep(30)
            
            # Reintentar el loop (evitar crash completo)
            self.stdout.write(self.style.SUCCESS('🔄 Reintentando trading loop...'))
            # Recursivamente reintentar (pero limitar a 3 intentos para evitar loops infinitos)
            if not hasattr(self, '_retry_count'):
                self._retry_count = 0
            self._retry_count += 1
            if self._retry_count < 3:
                self.handle(*args, **options)
            else:
                self.stdout.write(self.style.ERROR('❌ Demasiados errores consecutivos. Deteniendo...'))
                raise
    
    def _check_pending_trades(self, client):
        """Verificar operaciones abiertas y actualizar su estado aunque se haya perdido la suscripción."""
        try:
            import json
            import logging
            logger = logging.getLogger('trading_loop')
            
            # Operaciones pendientes de la última hora
            since = timezone.now() - timedelta(hours=1)
            pending_trades = OrderAudit.objects.filter(
                status__in=['pending', 'active', 'open'],
                timestamp__gte=since
            )
            
            checked_count = 0
            updated_count = 0
            error_count = 0
            
            for trade in pending_trades:
                # Tiempo transcurrido desde la apertura
                elapsed = (timezone.now() - trade.timestamp).total_seconds()
                elapsed_hours = elapsed / 3600
                
                # AUTOLIMPIEZA: Si tiene más de 2 horas, marcarlo como expirado automáticamente
                if elapsed_hours > 2.0:
                    logger.warning(f"Trade {trade.id} ({trade.symbol}): Muy antiguo ({elapsed_hours:.2f}h), marcando como expirado")
                    try:
                        trade.status = 'lost'
                        trade.pnl = -Decimal(str(trade.size or 0))
                        
                        # Actualizar response_payload
                        if not trade.response_payload:
                            trade.response_payload = {}
                        elif isinstance(trade.response_payload, str):
                            try:
                                import json
                                trade.response_payload = json.loads(trade.response_payload)
                            except:
                                trade.response_payload = {}
                        
                        trade.response_payload['auto_expired'] = True
                        trade.response_payload['auto_expired_at'] = timezone.now().isoformat()
                        trade.response_payload['age_hours'] = round(elapsed_hours, 2)
                        trade.response_payload['reason'] = f'Auto-expirado: más de 2 horas en estado pending/active'
                        
                        trade.save(update_fields=['status', 'pnl', 'response_payload'])
                        updated_count += 1
                        
                        self.stdout.write(
                            self.style.WARNING(
                                f'  ⚠️ {trade.symbol}: Auto-expirado ({elapsed_hours:.1f}h) - P&L: ${trade.pnl:.2f}'
                            )
                        )
                    except Exception as e:
                        logger.error(f"Error auto-expirando trade {trade.id}: {e}")
                        error_count += 1
                    
                    continue  # Ya procesado, continuar con siguiente
                
                # Duración esperada por tipo de símbolo (binarias 30s, forex 60s)
                expected_duration = 60 if str(trade.symbol).startswith('frx') else 30
                # Gracia adicional para reconexiones
                if elapsed < max(30, expected_duration):
                    continue
                
                checked_count += 1
                
                # Obtener contract_id de múltiples formas posibles
                contract_id = None
                
                # Método 1: response_payload como dict
                if trade.response_payload:
                    if isinstance(trade.response_payload, dict):
                        contract_id = trade.response_payload.get('order_id') or trade.response_payload.get('contract_id')
                    elif isinstance(trade.response_payload, str):
                        try:
                            payload_dict = json.loads(trade.response_payload)
                            contract_id = payload_dict.get('order_id') or payload_dict.get('contract_id')
                        except json.JSONDecodeError:
                            logger.warning(f"Trade {trade.id}: response_payload no es JSON válido: {trade.response_payload[:100]}")
                            pass
                
                # Método 2: request_payload
                if not contract_id and trade.request_payload:
                    if isinstance(trade.request_payload, dict):
                        contract_id = trade.request_payload.get('order_id') or trade.request_payload.get('contract_id')
                    elif isinstance(trade.request_payload, str):
                        try:
                            payload_dict = json.loads(trade.request_payload)
                            contract_id = payload_dict.get('order_id') or payload_dict.get('contract_id')
                        except json.JSONDecodeError:
                            pass
                
                if not contract_id:
                    logger.warning(f"Trade {trade.id} ({trade.symbol}): No se encontró contract_id")
                    error_count += 1
                    continue
                
                # Consultar estado (reintentos breves para cubrir reconexiones)
                try:
                    attempts = 3
                    contract_info = None
                    last_error = None
                    
                    for attempt in range(attempts):
                        try:
                            contract_info = client.get_open_contract_info(contract_id)
                            if contract_info and not contract_info.get('error'):
                                break
                            last_error = contract_info.get('error') if contract_info else 'No response'
                            if attempt < attempts - 1:
                                time.sleep(1.0)
                        except Exception as e:
                            last_error = str(e)
                            logger.warning(f"Trade {trade.id} ({trade.symbol}): Error en intento {attempt + 1}: {e}")
                            if attempt < attempts - 1:
                                time.sleep(1.0)
                    
                    if not contract_info or contract_info.get('error'):
                        logger.warning(f"Trade {trade.id} ({trade.symbol}): No se pudo obtener info del contrato {contract_id}: {last_error}")
                        error_count += 1
                        continue
                    
                    # Deriv puede devolver is_sold como 1/0 (int) o True/False (bool)
                    is_sold_raw = contract_info.get('is_sold', False)
                    is_sold = bool(is_sold_raw) if is_sold_raw is not None else False
                    
                    # Si is_sold=True (o 1), el contrato se cerró en Deriv
                    if is_sold:
                        profit = float(contract_info.get('profit', 0) or 0)
                        new_status = 'won' if profit > 0 else 'lost'
                        trade.status = new_status
                        trade.pnl = profit
                        
                        sell_price = contract_info.get('sell_price')
                        if sell_price is not None:
                            trade.exit_price = float(sell_price)
                        
                        trade.save(update_fields=['status', 'pnl', 'exit_price'])
                        updated_count += 1
                        
                        status_emoji = "✅" if new_status == 'won' else "❌"
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'  {status_emoji} {trade.symbol} {trade.action.upper()}: {new_status.upper()} - P&L: ${profit:.2f}'
                            )
                        )
                        logger.info(f"Trade {trade.id} ({trade.symbol}) actualizado: {new_status}, P&L: ${profit:.2f}")
                    else:
                        # Contrato aún activo - verificar si debería haber expirado
                        elapsed_minutes = elapsed / 60
                        if elapsed_minutes > 2:  # Más de 2 minutos
                            logger.warning(f"Trade {trade.id} ({trade.symbol}): Aún activo después de {elapsed_minutes:.1f} minutos")
                except Exception as e:
                    logger.error(f"Trade {trade.id} ({trade.symbol}): Excepción al verificar: {e}", exc_info=True)
                    error_count += 1
            
            # Log resumen
            if checked_count > 0:
                logger.info(f"Verificación de trades: {checked_count} verificados, {updated_count} actualizados, {error_count} errores")
                if checked_count > 0:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  📊 Verificación: {checked_count} verificados, {updated_count} actualizados, {error_count} errores'
                        )
                    )
                    
        except Exception as e:
            import logging
            logger = logging.getLogger('trading_loop')
            logger.error(f"Error en _check_pending_trades: {e}", exc_info=True)
            # NO silenciar errores - mostrar para debugging
            self.stdout.write(self.style.ERROR(f'  ❌ Error verificando trades pendientes: {e}'))
    
    def _check_orphaned_trades(self, client):
        """
        Verificar si hay trades ejecutados en Deriv que no están registrados en BD.
        Esto detecta casos donde el balance cambia pero no hay registros en OrderAudit.
        """
        try:
            from monitoring.models import OrderAudit
            from django.db.models import Q
            import logging
            logger = logging.getLogger('trading_loop')
            
            # Obtener balance actual
            balance_info = client.get_balance()
            if not balance_info or balance_info.get('error'):
                return
            
            current_balance = Decimal(str(balance_info.get('balance', 0)))
            
            # Buscar trades muy recientes (últimos 5 minutos) que deberían estar en BD
            recent_window = timezone.now() - timedelta(minutes=5)
            
            # Verificar si hay cambios de balance sin trades correspondientes
            # Esto es una heurística: si el balance cambió significativamente pero no hay trades,
            # podría haber un trade huérfano
            
            # Obtener trades de los últimos 5 minutos
            recent_trades = OrderAudit.objects.filter(
                timestamp__gte=recent_window
            ).count()
            
            # Si no hay trades recientes pero el balance cambió, podría haber huérfanos
            # Nota: Esta es una verificación básica. Una verificación más completa requeriría
            # comparar el balance esperado vs el real, pero eso es complejo.
            
            # Verificar contratos abiertos en Deriv que no están en BD
            try:
                # Obtener todos los contratos abiertos de Deriv (si la API lo soporta)
                open_contracts = client.get_open_positions() if hasattr(client, 'get_open_positions') else []
                
                if open_contracts:
                    for contract in open_contracts:
                        contract_id = contract.get('contract_id') or contract.get('id')
                        if not contract_id:
                            continue
                        
                        # Verificar si este contrato está en BD
                        exists = OrderAudit.objects.filter(
                            Q(response_payload__order_id=contract_id) |
                            Q(response_payload__contains={'order_id': str(contract_id)})
                        ).exists()
                        
                        if not exists:
                            # Trade huérfano encontrado - intentar registrar
                            logger.warning(f"⚠️ Trade huérfano detectado: Contract ID {contract_id}")
                            self.stdout.write(
                                self.style.WARNING(f'  ⚠️ Trade huérfano detectado: Contract ID {contract_id}')
                            )
                            
                            # Intentar crear registro mínimo
                            try:
                                OrderAudit.objects.create(
                                    timestamp=timezone.now() - timedelta(minutes=2),  # Aproximado
                                    symbol=contract.get('symbol', 'UNKNOWN'),
                                    action=contract.get('contract_type', 'unknown').lower(),
                                    size=Decimal(str(contract.get('buy_price', '0.01'))),
                                    price=Decimal(str(contract.get('entry_spot', '0'))),
                                    status='active',
                                    request_payload={'recovered': True, 'contract_id': contract_id},
                                    response_payload={'order_id': contract_id, 'recovered': True},
                                    accepted=True,
                                    reason='orphan_recovery',
                                    error_message='Trade recuperado automáticamente - no estaba en BD'
                                )
                                logger.info(f"✅ Trade huérfano recuperado: {contract_id}")
                                self.stdout.write(
                                    self.style.SUCCESS(f'  ✅ Trade huérfano recuperado: {contract_id}')
                                )
                            except Exception as recovery_error:
                                logger.error(f"❌ No se pudo recuperar trade huérfano {contract_id}: {recovery_error}")
            except Exception:
                # Si get_open_positions no está disponible o falla, ignorar silenciosamente
                pass
                
        except Exception as e:
            import logging
            logger = logging.getLogger('trading_loop')
            logger.error(f"Error verificando trades huérfanos: {e}")
            # No detener el loop si falla

