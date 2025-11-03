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
            api_config = DerivAPIConfig.objects.filter(is_active=True).only('api_token', 'is_demo', 'app_id').first()
            if api_config:
                client = DerivClient(
                    api_token=api_config.api_token,
                    is_demo=api_config.is_demo,
                    app_id=api_config.app_id
                )
            else:
                raise ValueError("No hay configuración de API activa. Configura tu token en: http://localhost:8000/trading/config/api/")
        except Exception as e:
            print(f"❌ Error al inicializar DerivClient: {e}")
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
        if disable_max_trades:
            max_trades = 999999  # Prácticamente ilimitado
            self.stdout.write(self.style.WARNING('⚠️ Límite de trades DESACTIVADO (modo pruebas)'))
        
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
                    
                    if config.disable_max_trades:
                        effective_max_trades = 999999
                    if config.disable_profit_target:
                        effective_profit_target = Decimal('999999.00')
                        effective_profit_target_pct = 999.0
                    # Si hay stop_loss_amount configurado, tiene PRIORIDAD sobre max_loss
                    # Esto permite controlar el stop loss independientemente de otros límites
                    if config.stop_loss_amount > 0:
                        effective_max_loss = -abs(config.stop_loss_amount)
                    
                    # Actualizar configuración si cambió
                    if (capital_manager.profit_target != effective_profit_target or
                        capital_manager.max_loss != effective_max_loss or
                        capital_manager.max_trades != effective_max_trades):
                        capital_manager.profit_target = effective_profit_target
                        capital_manager.max_loss = effective_max_loss
                        capital_manager.max_trades = effective_max_trades
                        capital_manager.profit_target_pct = effective_profit_target_pct
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
                    self.stdout.write('=' * 60)
                    self.stdout.write(self.style.ERROR(f'🛑 TRADING DETENIDO: {reason}'))
                    self.stdout.write('')
                    self.stdout.write(self.style.SUCCESS(capital_manager.get_status_message(current_balance)))
                    self.stdout.write('')
                    self.stdout.write(self.style.SUCCESS('💡 El trading se reanudará mañana a las 00:00'))
                    self.stdout.write(self.style.SUCCESS('💡 Para continuar manualmente, reinicia el comando'))
                    self.stdout.write('=' * 60)
                    break  # Salir del loop
                
                # Mostrar estado del Capital Manager
                status_msg = capital_manager.get_status_message(current_balance)
                self.stdout.write(self.style.SUCCESS(status_msg))
                
                # Obtener símbolos con ticks recientes - PROCESA TODOS LOS ACTIVOS
                since = timezone.now() - timedelta(hours=24)
                symbols = Tick.objects.filter(
                    timestamp__gte=since
                ).values_list('symbol', flat=True).distinct()
                
                # Filtrar símbolos no operables (Crypto/OTC y BOOM/CRASH no ofrecidos en esta cuenta)
                excluded_symbols = [
                    s for s in list(symbols)
                    if s.startswith('cry') or s.startswith('OTC') or s.startswith('BOOM') or s.startswith('CRASH')
                ]
                symbols_list = [s for s in list(symbols) if s not in excluded_symbols]
                
                self.stdout.write('=' * 60)
                self.stdout.write(f'📊 Símbolos: {symbols_list}')
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
                                        # Obtener monto del trade desde action si está disponible
                                        trade_amount = action.get('amount')
                                        if trade_amount:
                                            trade_amount = Decimal(str(trade_amount))
                                        else:
                                            trade_amount = None
                                        loop.capital_manager.update_martingale_level(trade_won, trade_amount)
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
                
                for symbol in symbols_list:
                    try:
                        result = loop.process_symbol(symbol)
                        
                        if not result:
                            continue
                        
                        status = result.get('status')
                        
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
                        self.stdout.write(
                            self.style.ERROR(f'  ❌ Error en {symbol}: {e}')
                        )
                
                # Mostrar resumen solo si hay actividad
                if executed_count > 0 or rejected_count > 0:
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
                    self.stdout.write('=' * 60)
                    self.stdout.write(self.style.ERROR(f'🛑 TRADING DETENIDO: {reason}'))
                    self.stdout.write(self.style.SUCCESS(capital_manager.get_status_message(current_balance)))
                    self.stdout.write('=' * 60)
                    break
                
                self.stdout.write('=' * 60)
                self.stdout.write('')
                
                # Esperar 10 segundos (aumentado de 5 a 10 para reducir rate limit aún más)
                time.sleep(10)
                
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS('\n\n⚠️  Deteniendo trading loop...'))
            return
    
    def _check_pending_trades(self, client):
        """Verificar operaciones pendientes y actualizar estado"""
        try:
            # Operaciones pendientes de la última hora
            since = timezone.now() - timedelta(hours=1)
            pending_trades = OrderAudit.objects.filter(
                status='pending',
                timestamp__gte=since
            )
            
            for trade in pending_trades:
                # Solo verificar si pasaron al menos 30 segundos
                elapsed = (timezone.now() - trade.timestamp).total_seconds()
                
                if elapsed < 30:
                    continue
                
                # Obtener contract_id
                contract_id = None
                if trade.response_payload and isinstance(trade.response_payload, dict):
                    contract_id = trade.response_payload.get('order_id')
                
                if not contract_id:
                    continue
                
                # Consultar estado
                try:
                    contract_info = client.get_open_contract_info(contract_id)
                    
                    if contract_info.get('error'):
                        continue
                    
                    # Si is_sold=True, el contrato se cerró
                    if contract_info.get('is_sold'):
                        new_status = 'won' if contract_info.get('profit', 0) > 0 else 'lost'
                        trade.status = new_status
                        
                        if contract_info.get('profit'):
                            trade.pnl = float(contract_info['profit'])
                        if contract_info.get('sell_price'):
                            trade.exit_price = float(contract_info['sell_price'])
                        
                        trade.save()
                        
                        status_emoji = "✅" if new_status == 'won' else "❌"
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'  {status_emoji} {trade.symbol} {trade.action.upper()}: {new_status.upper()} - P&L: ${contract_info.get("profit", 0):.2f}'
                            )
                        )
                except:
                    pass  # Ignorar errores
                    
        except Exception as e:
            pass  # Error silencioso

