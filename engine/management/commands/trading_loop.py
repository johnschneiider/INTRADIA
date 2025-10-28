"""
Comando para ejecutar el trading loop directamente
Evita problemas de Celery en Windows
"""
import time
import json
from django.core.management.base import BaseCommand
from engine.services.tick_trading_loop import TickTradingLoop
from market.models import Tick
from monitoring.models import OrderAudit
from django.utils import timezone
from datetime import timedelta
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


class Command(BaseCommand):
    help = 'Ejecuta el loop de trading cada 2 segundos'

    def handle(self, *args, **options):
        from connectors.deriv_client import DerivClient
        
        # Usar estrategia estadística híbrida (NUEVA)
        use_statistical = True
        
        loop = TickTradingLoop(use_statistical=use_statistical)
        channel_layer = get_channel_layer()
        client = DerivClient()
        
        self.stdout.write(self.style.SUCCESS('🚀 Iniciando trading loop...'))
        if use_statistical:
            self.stdout.write(self.style.SUCCESS('📊 Estrategia: ESTADÍSTICA HÍBRIDA (Mean Reversion + Momentum)'))
        else:
            self.stdout.write(self.style.SUCCESS('📊 Estrategia: TICK-BASED (tendencia simple)'))
        self.stdout.write(self.style.SUCCESS('📊 Analizando todos los símbolos cada 2 segundos'))
        self.stdout.write('')
        
        try:
            while True:
                # Obtener símbolos con ticks recientes
                since = timezone.now() - timedelta(hours=24)
                symbols = Tick.objects.filter(
                    timestamp__gte=since
                ).values_list('symbol', flat=True).distinct()
                
                # EXCLUIR símbolos no disponibles para trading
                excluded_symbols = ['BOOM1000', 'CRASH1000']
                symbols_list = [s for s in list(symbols) if s not in excluded_symbols]
                
                self.stdout.write('=' * 60)
                self.stdout.write(f'📊 Símbolos: {symbols_list}')
                self.stdout.write('')
                
                # Procesar cada símbolo
                for symbol in symbols_list:
                    try:
                        result = loop.process_symbol(symbol)
                        
                        if result and result.get('status') == 'executed':
                            signal_info = result.get("signal", {})
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'  ✅ {symbol} {signal_info.get("direction")} - Balance: ${result.get("result", {}).get("balance_after", 0)}'
                                )
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
                                                'order_id': last_trade.request_payload.get('order_id'),
                                                'status': 'pending'
                                            }
                                        }
                                    )
                            except Exception as e:
                                pass  # Error silencioso
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f'  ❌ Error en {symbol}: {e}')
                        )
                
                # Verificar operaciones pendientes (cada 2 segundos)
                self._check_pending_trades(client)
                
                self.stdout.write('=' * 60)
                self.stdout.write('')
                
                # Esperar 2 segundos
                time.sleep(2)
                
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

