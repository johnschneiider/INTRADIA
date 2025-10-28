"""
Comando para verificar operaciones pendientes y actualizar su estado
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from monitoring.models import OrderAudit
from connectors.deriv_client import DerivClient


class Command(BaseCommand):
    help = 'Verifica operaciones pendientes y actualiza su estado'

    def handle(self, *args, **options):
        client = DerivClient()
        
        # Obtener operaciones pendientes de las últimas 2 horas
        since = timezone.now() - timedelta(hours=2)
        pending_trades = OrderAudit.objects.filter(
            status='pending',
            timestamp__gte=since
        )
        
        print(f"\n🔍 Verificando {pending_trades.count()} operaciones pendientes...")
        
        for trade in pending_trades:
            # Si pasaron más de 60 segundos desde la creación, verificar estado
            elapsed = (timezone.now() - trade.timestamp).total_seconds()
            
            if elapsed < 30:
                print(f"  ⏳ {trade.symbol} {trade.action.upper()}: Esperando (faltan {30 - elapsed:.0f}s)")
                continue
            
            # Obtener contract_id del response_payload
            contract_id = None
            if trade.response_payload and isinstance(trade.response_payload, dict):
                contract_id = trade.response_payload.get('order_id')
            
            if not contract_id:
                print(f"  ❌ {trade.symbol} {trade.action.upper()}: Sin contract_id")
                continue
            
            # Consultar estado del contrato
            try:
                contract_info = client.get_open_contract_info(contract_id)
                
                if contract_info.get('error'):
                    print(f"  ❌ {trade.symbol} {trade.action.upper()}: Error - {contract_info['error']}")
                    continue
                
                # Si is_sold=True, el contrato se cerró
                if contract_info.get('is_sold'):
                    new_status = 'won' if contract_info.get('profit', 0) > 0 else 'lost'
                    trade.status = new_status
                    
                    # Actualizar campos adicionales
                    if contract_info.get('profit'):
                        trade.pnl = float(contract_info['profit'])
                    if contract_info.get('sell_price'):
                        trade.exit_price = float(contract_info['sell_price'])
                    
                    trade.save()
                    
                    status_emoji = "✅" if new_status == 'won' else "❌"
                    print(f"  {status_emoji} {trade.symbol} {trade.action.upper()}: {new_status.upper()} - P&L: ${contract_info.get('profit', 0):.2f}")
                else:
                    print(f"  ⏳ {trade.symbol} {trade.action.upper()}: Aún abierto")
                    
            except Exception as e:
                print(f"  ❌ {trade.symbol} {trade.action.upper()}: Excepción - {str(e)}")
        
        print("\n✅ Verificación completada")

