"""
Script de diagnóstico completo del flujo de trades
Prueba paso a paso desde la ejecución hasta la finalización
"""
import json
import time
import sys
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from monitoring.models import OrderAudit
from connectors.deriv_client import DerivClient
from trading_bot.models import DerivAPIConfig


class Command(BaseCommand):
    help = 'Diagnóstico completo del flujo de trades: desde ejecución hasta finalización'

    def add_arguments(self, parser):
        parser.add_argument(
            '--trade-id',
            type=int,
            help='Probar un trade específico por ID'
        )
        parser.add_argument(
            '--contract-id',
            type=str,
            help='Probar un contract_id específico directamente con API'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(self.style.SUCCESS('🔍 DIAGNÓSTICO COMPLETO DEL FLUJO DE TRADES'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        
        # Inicializar cliente
        try:
            api_config = DerivAPIConfig.objects.filter(is_active=True).only('api_token', 'is_demo', 'app_id').first()
            if not api_config:
                self.stdout.write(self.style.ERROR('❌ No hay configuración de API activa'))
                return
            
            self.stdout.write(f'\n📋 Configuración API:')
            self.stdout.write(f'   - Demo: {api_config.is_demo}')
            self.stdout.write(f'   - Token: {api_config.api_token[:20]}...')
            
            client = DerivClient(
                api_token=api_config.api_token,
                is_demo=api_config.is_demo,
                app_id=api_config.app_id
            )
            
            self.stdout.write(f'\n🔌 Paso 1: Autenticación con Deriv...')
            if not client.authenticate():
                self.stdout.write(self.style.ERROR('❌ No se pudo autenticar con Deriv'))
                return
            
            self.stdout.write(self.style.SUCCESS('✅ Autenticación exitosa'))
            self.stdout.write(f'   - Connected: {client.connected}')
            self.stdout.write(f'   - WebSocket existe: {client.ws is not None}')
            if client.ws:
                self.stdout.write(f'   - WebSocket sock existe: {client.ws.sock is not None}')
                if client.ws.sock:
                    self.stdout.write(f'   - WebSocket connected: {getattr(client.ws.sock, "connected", "N/A")}')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error inicializando cliente: {e}'))
            import traceback
            traceback.print_exc()
            return
        
        # Si se especificó un contract_id, probarlo directamente
        if options['contract_id']:
            self._test_contract_direct(client, options['contract_id'])
            return
        
        # Si se especificó un trade_id, probarlo
        if options['trade_id']:
            try:
                trade = OrderAudit.objects.get(id=options['trade_id'])
                self._diagnose_trade_complete(client, trade)
            except OrderAudit.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'❌ Trade {options["trade_id"]} no encontrado'))
            return
        
        # Diagnóstico de todos los trades pendientes
        self.stdout.write(f'\n📊 PASO 2: Buscando trades pendientes...')
        since = timezone.now() - timedelta(hours=24)
        pending_trades = OrderAudit.objects.filter(
            status__in=['pending', 'active', 'open'],
            timestamp__gte=since
        ).order_by('-timestamp')
        
        self.stdout.write(f'   Encontrados: {pending_trades.count()} trades pendientes')
        
        if pending_trades.count() == 0:
            self.stdout.write(self.style.WARNING('⚠️ No hay trades pendientes para diagnosticar'))
            return
        
        # Probar los más antiguos primero (más probables de estar pegados)
        old_trades = pending_trades.filter(
            timestamp__lt=timezone.now() - timedelta(minutes=2)
        )[:5]
        
        if old_trades.count() == 0:
            old_trades = pending_trades[:3]
        
        self.stdout.write(f'\n🔍 Probando {old_trades.count()} trades (los más antiguos):')
        self.stdout.write('=' * 80)
        
        for trade in old_trades:
            self._diagnose_trade_complete(client, trade)
            self.stdout.write('=' * 80)
    
    def _diagnose_trade_complete(self, client, trade):
        """Diagnóstico completo de un trade: paso a paso"""
        self.stdout.write(f'\n📋 TRADE ID: {trade.id}')
        self.stdout.write(f'   Símbolo: {trade.symbol}')
        self.stdout.write(f'   Estado BD: {trade.status}')
        self.stdout.write(f'   Timestamp: {trade.timestamp}')
        self.stdout.write(f'   Tiempo transcurrido: {(timezone.now() - trade.timestamp).total_seconds():.0f} segundos')
        self.stdout.write(f'   Aceptado: {trade.accepted}')
        
        # PASO 1: Extraer contract_id
        self.stdout.write(f'\n🔍 PASO 1: Extrayendo contract_id...')
        contract_id = self._extract_contract_id(trade)
        
        if not contract_id:
            self.stdout.write(self.style.ERROR('   ❌ NO SE ENCONTRÓ CONTRACT_ID'))
            self._show_payload_structure(trade)
            return
        
        self.stdout.write(self.style.SUCCESS(f'   ✅ Contract ID encontrado: {contract_id}'))
        
        # PASO 2: Verificar conexión WebSocket
        self.stdout.write(f'\n🔍 PASO 2: Verificando conexión WebSocket...')
        if not client.connected:
            self.stdout.write(self.style.WARNING('   ⚠️ Cliente no conectado, intentando reconectar...'))
            if not client.authenticate():
                self.stdout.write(self.style.ERROR('   ❌ No se pudo reconectar'))
                return
            self.stdout.write(self.style.SUCCESS('   ✅ Reconectado'))
        else:
            self.stdout.write(self.style.SUCCESS('   ✅ Cliente conectado'))
        
        # Verificar estado WebSocket
        if not client.ws:
            self.stdout.write(self.style.ERROR('   ❌ WebSocket no existe'))
            return
        
        if not client.ws.sock:
            self.stdout.write(self.style.ERROR('   ❌ WebSocket sock no existe'))
            return
        
        sock_connected = getattr(client.ws.sock, 'connected', False)
        if not sock_connected:
            self.stdout.write(self.style.WARNING('   ⚠️ WebSocket sock no está conectado, intentando reconectar...'))
            if not client.authenticate():
                self.stdout.write(self.style.ERROR('   ❌ No se pudo reconectar WebSocket'))
                return
            self.stdout.write(self.style.SUCCESS('   ✅ WebSocket reconectado'))
        else:
            self.stdout.write(self.style.SUCCESS('   ✅ WebSocket sock conectado'))
        
        # PASO 3: Probar consulta de contrato
        self.stdout.write(f'\n🔍 PASO 3: Consultando estado del contrato en Deriv API...')
        self.stdout.write(f'   Enviando: proposal_open_contract con contract_id={contract_id}')
        
        result = self._test_contract_with_logging(client, contract_id)
        
        if result.get('error'):
            self.stdout.write(self.style.ERROR(f'   ❌ Error: {result.get("error")}'))
            self._analyze_error(result.get('error'), trade)
        else:
            self.stdout.write(self.style.SUCCESS(f'   ✅ Respuesta recibida'))
            self.stdout.write(f'   - is_sold: {result.get("is_sold", False)}')
            self.stdout.write(f'   - profit: ${result.get("profit", 0):.2f}')
            self.stdout.write(f'   - status: {result.get("status", "N/A")}')
            
            if result.get('is_sold'):
                self.stdout.write(f'\n🔍 PASO 4: Contrato finalizado, actualizando BD...')
                new_status = 'won' if result.get('profit', 0) > 0 else 'lost'
                trade.status = new_status
                trade.pnl = float(result.get('profit', 0))
                if result.get('sell_price'):
                    trade.exit_price = float(result.get('sell_price'))
                trade.save(update_fields=['status', 'pnl', 'exit_price'])
                self.stdout.write(self.style.SUCCESS(f'   ✅ Trade actualizado: {new_status}, P&L: ${trade.pnl:.2f}'))
            else:
                self.stdout.write(f'\n⚠️ PASO 4: Contrato aún activo en Deriv')
                elapsed_minutes = (timezone.now() - trade.timestamp).total_seconds() / 60
                expected_minutes = 1 if str(trade.symbol).startswith('frx') else 0.5
                if elapsed_minutes > expected_minutes + 0.5:
                    self.stdout.write(self.style.WARNING(f'   ⚠️ Contrato tiene {elapsed_minutes:.1f} minutos, esperado {expected_minutes} min'))
                    self.stdout.write(self.style.WARNING(f'   ⚠️ Puede estar esperando que expire o hay un problema'))
    
    def _extract_contract_id(self, trade):
        """Extraer contract_id de múltiples formas posibles"""
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
        
        return contract_id
    
    def _show_payload_structure(self, trade):
        """Mostrar estructura de payloads para debugging"""
        self.stdout.write(f'\n   📦 Estructura de payloads:')
        self.stdout.write(f'   - response_payload tipo: {type(trade.response_payload)}')
        if trade.response_payload:
            if isinstance(trade.response_payload, str):
                self.stdout.write(f'   - response_payload (primeros 200 chars): {str(trade.response_payload)[:200]}')
            else:
                self.stdout.write(f'   - response_payload keys: {list(trade.response_payload.keys()) if isinstance(trade.response_payload, dict) else "N/A"}')
        
        self.stdout.write(f'   - request_payload tipo: {type(trade.request_payload)}')
        if trade.request_payload:
            if isinstance(trade.request_payload, str):
                self.stdout.write(f'   - request_payload (primeros 200 chars): {str(trade.request_payload)[:200]}')
            else:
                self.stdout.write(f'   - request_payload keys: {list(trade.request_payload.keys()) if isinstance(trade.request_payload, dict) else "N/A"}')
    
    def _test_contract_with_logging(self, client, contract_id):
        """Probar consulta de contrato con logging detallado"""
        try:
            import json
            from threading import Event
            
            # Verificar conexión
            if not client.connected:
                if not client.authenticate():
                    return {'error': 'Not connected'}
            
            # Limpiar evento anterior
            client.response_event.clear()
            
            # Preparar mensaje
            contract_msg = {
                'proposal_open_contract': 1,
                'contract_id': contract_id
            }
            
            self.stdout.write(f'   📤 Mensaje enviado: {json.dumps(contract_msg)}')
            
            # Enviar mensaje
            client.ws.send(json.dumps(contract_msg))
            self.stdout.write(f'   ✅ Mensaje enviado por WebSocket')
            
            # Esperar respuesta con timeout
            timeout = 10
            self.stdout.write(f'   ⏳ Esperando respuesta (timeout: {timeout}s)...')
            
            if client.response_event.wait(timeout=timeout):
                self.stdout.write(f'   ✅ Evento recibido')
                data = client.response_data
                
                self.stdout.write(f'   📥 Respuesta completa: {json.dumps(data, indent=2, default=str)[:500]}')
                
                if data.get('error'):
                    return {'error': data['error']}
                
                contract_info = data.get('proposal_open_contract', {})
                
                if not contract_info:
                    self.stdout.write(self.style.WARNING(f'   ⚠️ Respuesta sin "proposal_open_contract"'))
                    self.stdout.write(f'   📥 Keys en respuesta: {list(data.keys())}')
                    return {'error': 'No proposal_open_contract in response'}
                
                is_sold = contract_info.get('is_sold', False)
                profit = contract_info.get('profit', 0)
                status = 'won' if profit > 0 else 'lost' if is_sold else None
                
                return {
                    'is_sold': is_sold,
                    'status': status,
                    'profit': profit,
                    'buy_price': contract_info.get('buy_price', 0),
                    'sell_price': contract_info.get('sell_price', 0),
                    'raw_data': contract_info
                }
            else:
                self.stdout.write(self.style.ERROR(f'   ❌ TIMEOUT: No se recibió respuesta en {timeout}s'))
                return {'error': 'timeout'}
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ❌ Excepción: {e}'))
            import traceback
            traceback.print_exc()
            return {'error': str(e)}
    
    def _test_contract_direct(self, client, contract_id):
        """Probar un contract_id directamente"""
        self.stdout.write(f'\n🔍 Probando contract_id directamente: {contract_id}')
        result = self._test_contract_with_logging(client, contract_id)
        
        if result.get('error'):
            self.stdout.write(self.style.ERROR(f'❌ Error: {result.get("error")}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'✅ Resultado:'))
            self.stdout.write(f'   - is_sold: {result.get("is_sold")}')
            self.stdout.write(f'   - profit: ${result.get("profit", 0):.2f}')
            self.stdout.write(f'   - status: {result.get("status")}')
    
    def _analyze_error(self, error, trade):
        """Analizar tipo de error y sugerir solución"""
        error_str = str(error).lower()
        
        self.stdout.write(f'\n🔍 Análisis del error:')
        
        if 'timeout' in error_str:
            self.stdout.write(self.style.WARNING('   ⚠️ TIMEOUT: La API no respondió en 10 segundos'))
            self.stdout.write('   💡 Posibles causas:')
            self.stdout.write('      - WebSocket desconectado')
            self.stdout.write('      - API de Deriv lenta o sobrecargada')
            self.stdout.write('      - El contrato ya expiró y no se puede consultar')
        elif 'not connected' in error_str:
            self.stdout.write(self.style.WARNING('   ⚠️ NO CONECTADO: WebSocket no está activo'))
            self.stdout.write('   💡 Solución: Reiniciar el servicio trading-loop')
        elif 'not found' in error_str or 'invalid' in error_str:
            self.stdout.write(self.style.WARNING('   ⚠️ CONTRATO NO ENCONTRADO: El contract_id no existe en Deriv'))
            self.stdout.write('   💡 Posible causa: El contrato ya expiró y fue eliminado')
            self.stdout.write('   💡 Solución: Marcar trade como "lost" manualmente')
        else:
            self.stdout.write(self.style.WARNING(f'   ⚠️ Error desconocido: {error}'))

