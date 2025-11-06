"""
Comando de diagnóstico para identificar por qué los trades se quedan pegados
"""
import json
import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from monitoring.models import OrderAudit
from connectors.deriv_client import DerivClient
from trading_bot.models import DerivAPIConfig


class Command(BaseCommand):
    help = 'Diagnosticar trades que se quedan pegados en estado activo/pending'

    def add_arguments(self, parser):
        parser.add_argument(
            '--contract-id',
            type=str,
            help='Probar un contract_id específico'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Probar todos los trades pendientes'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🔍 DIAGNÓSTICO DE TRADES PEGADOS'))
        self.stdout.write('=' * 80)
        
        # Inicializar cliente
        try:
            api_config = DerivAPIConfig.objects.filter(is_active=True).only('api_token', 'is_demo', 'app_id').first()
            if not api_config:
                self.stdout.write(self.style.ERROR('❌ No hay configuración de API activa'))
                return
            
            client = DerivClient(
                api_token=api_config.api_token,
                is_demo=api_config.is_demo,
                app_id=api_config.app_id
            )
            
            if not client.authenticate():
                self.stdout.write(self.style.ERROR('❌ No se pudo autenticar con Deriv'))
                return
            
            self.stdout.write(self.style.SUCCESS('✅ Cliente Deriv inicializado'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error inicializando cliente: {e}'))
            import traceback
            traceback.print_exc()
            return
        
        # Si se especificó un contract_id específico
        if options['contract_id']:
            self._test_contract_id(client, options['contract_id'])
            return
        
        # Obtener todos los trades pendientes
        since = timezone.now() - timedelta(hours=24)
        pending_trades = OrderAudit.objects.filter(
            status__in=['pending', 'active', 'open'],
            timestamp__gte=since
        ).order_by('-timestamp')
        
        self.stdout.write(f'\n📊 Trades pendientes encontrados: {pending_trades.count()}')
        self.stdout.write('=' * 80)
        
        if options['all'] or pending_trades.count() <= 10:
            # Probar todos
            for trade in pending_trades:
                self._diagnose_trade(client, trade)
        else:
            # Probar solo los más antiguos (los que probablemente están pegados)
            old_trades = pending_trades.filter(
                timestamp__lt=timezone.now() - timedelta(minutes=5)
            )[:10]
            
            self.stdout.write(f'\n🔍 Probando los {old_trades.count()} trades más antiguos (>5 min):')
            for trade in old_trades:
                self._diagnose_trade(client, trade)
    
    def _diagnose_trade(self, client, trade):
        """Diagnosticar un trade específico"""
        self.stdout.write(f'\n{"="*80}')
        self.stdout.write(f'📋 Trade ID: {trade.id}')
        self.stdout.write(f'   Símbolo: {trade.symbol}')
        self.stdout.write(f'   Estado: {trade.status}')
        self.stdout.write(f'   Timestamp: {trade.timestamp}')
        self.stdout.write(f'   Tiempo transcurrido: {(timezone.now() - trade.timestamp).total_seconds():.0f} segundos')
        
        # Extraer contract_id de diferentes formas posibles
        contract_id = None
        
        # Método 1: response_payload como dict
        if trade.response_payload:
            if isinstance(trade.response_payload, dict):
                contract_id = trade.response_payload.get('order_id') or trade.response_payload.get('contract_id')
            elif isinstance(trade.response_payload, str):
                try:
                    payload_dict = json.loads(trade.response_payload)
                    contract_id = payload_dict.get('order_id') or payload_dict.get('contract_id')
                except:
                    pass
        
        # Método 2: request_payload
        if not contract_id and trade.request_payload:
            if isinstance(trade.request_payload, dict):
                contract_id = trade.request_payload.get('order_id') or trade.request_payload.get('contract_id')
            elif isinstance(trade.request_payload, str):
                try:
                    payload_dict = json.loads(trade.request_payload)
                    contract_id = payload_dict.get('order_id') or payload_dict.get('contract_id')
                except:
                    pass
        
        if not contract_id:
            self.stdout.write(self.style.ERROR('   ❌ NO SE ENCONTRÓ CONTRACT_ID'))
            self.stdout.write(f'   response_payload tipo: {type(trade.response_payload)}')
            if trade.response_payload:
                self.stdout.write(f'   response_payload: {str(trade.response_payload)[:200]}')
            return
        
        self.stdout.write(f'   ✅ Contract ID encontrado: {contract_id}')
        
        # Probar la API
        self._test_contract_id(client, contract_id, trade)
    
    def _test_contract_id(self, client, contract_id, trade=None):
        """Probar un contract_id específico con la API"""
        self.stdout.write(f'\n🔬 Probando contract_id: {contract_id}')
        
        # Método 1: get_open_contract_info
        self.stdout.write('\n   Método 1: get_open_contract_info')
        try:
            result = client.get_open_contract_info(contract_id)
            self.stdout.write(f'   Resultado: {result}')
            
            if result.get('error'):
                self.stdout.write(self.style.ERROR(f'   ❌ Error: {result.get("error")}'))
            else:
                is_sold = result.get('is_sold', False)
                profit = result.get('profit', 0)
                status = 'won' if profit > 0 else 'lost' if is_sold else 'pending'
                
                self.stdout.write(self.style.SUCCESS(f'   ✅ is_sold: {is_sold}'))
                self.stdout.write(self.style.SUCCESS(f'   ✅ profit: ${profit:.2f}'))
                self.stdout.write(self.style.SUCCESS(f'   ✅ status: {status}'))
                
                # Si está vendido, actualizar el trade
                if is_sold and trade:
                    self.stdout.write(f'\n   🔄 Actualizando trade {trade.id}...')
                    trade.status = 'won' if profit > 0 else 'lost'
                    trade.pnl = float(profit)
                    if result.get('sell_price'):
                        trade.exit_price = float(result.get('sell_price'))
                    trade.save(update_fields=['status', 'pnl', 'exit_price'])
                    self.stdout.write(self.style.SUCCESS(f'   ✅ Trade actualizado: {trade.status}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ❌ Excepción: {e}'))
            import traceback
            traceback.print_exc()
        
        # Método 2: get_contract_status (alternativo)
        self.stdout.write('\n   Método 2: get_contract_status')
        try:
            result2 = client.get_contract_status(contract_id)
            self.stdout.write(f'   Resultado: {str(result2)[:300]}')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ❌ Excepción: {e}'))
        
        # Verificar conexión WebSocket
        self.stdout.write('\n   Estado WebSocket:')
        self.stdout.write(f'   - connected: {client.connected}')
        if hasattr(client, 'ws') and client.ws:
            self.stdout.write(f'   - ws existe: True')
            if hasattr(client.ws, 'sock') and client.ws.sock:
                self.stdout.write(f'   - sock existe: True')
                self.stdout.write(f'   - sock.connected: {client.ws.sock.connected if hasattr(client.ws.sock, "connected") else "N/A"}')
            else:
                self.stdout.write(self.style.WARNING('   - sock NO existe'))
        else:
            self.stdout.write(self.style.WARNING('   - ws NO existe'))

