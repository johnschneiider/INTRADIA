"""
Comando de Django para verificar y actualizar contratos pendientes/activos
Este comando debe ejecutarse periódicamente (cada 1-2 minutos) para limpiar contratos pegados
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from monitoring.models import OrderAudit
from connectors.deriv_client import DerivClient
from trading_bot.models import DerivAPIConfig


class Command(BaseCommand):
    help = 'Verifica y actualiza el estado de contratos pendientes/activos que pueden estar expirados'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Forzar verificación de todos los contratos pendientes/activos',
        )
        parser.add_argument(
            '--max-age-minutes',
            type=int,
            default=5,
            help='Solo verificar contratos más antiguos que X minutos (default: 5)',
        )

    def handle(self, *args, **options):
        force = options['force']
        max_age_minutes = options['max_age_minutes']
        
        # Obtener configuración de API
        api_config = DerivAPIConfig.objects.filter(is_active=True).first()
        if not api_config:
            self.stdout.write(self.style.ERROR('❌ No hay configuración de API activa'))
            return
        
        # Crear cliente Deriv
        client = DerivClient(
            api_token=api_config.api_token,
            is_demo=api_config.is_demo,
            app_id=api_config.app_id
        )
        
        if not client.authenticate():
            self.stdout.write(self.style.ERROR('❌ No se pudo autenticar con Deriv API'))
            return
        
        # Obtener contratos pendientes/activos
        if force:
            # Verificar todos los contratos pendientes/activos
            pending_trades = OrderAudit.objects.filter(
                status__in=['pending', 'active']
            ).order_by('timestamp')
        else:
            # Solo verificar contratos que tienen más de X minutos
            cutoff_time = timezone.now() - timedelta(minutes=max_age_minutes)
            pending_trades = OrderAudit.objects.filter(
                status__in=['pending', 'active'],
                timestamp__lt=cutoff_time
            ).order_by('timestamp')
        
        # También verificar contratos que tienen más de 2 horas (marcar como expirados automáticamente)
        old_cutoff = timezone.now() - timedelta(hours=2)
        very_old_trades = OrderAudit.objects.filter(
            status__in=['pending', 'active'],
            timestamp__lt=old_cutoff
        )
        
        # Marcar automáticamente como expirados los contratos muy antiguos
        for old_trade in very_old_trades:
            try:
                old_trade.status = 'lost'
                old_trade.pnl = -Decimal(str(old_trade.size or 0))
                if not old_trade.response_payload:
                    old_trade.response_payload = {}
                old_trade.response_payload['auto_expired'] = True
                old_trade.response_payload['auto_expired_at'] = timezone.now().isoformat()
                old_trade.response_payload['reason'] = 'Contrato expirado automáticamente (más de 2 horas en estado pending/active)'
                old_trade.save()
                expired_count += 1
                if not force:
                    self.stdout.write(
                        self.style.WARNING(
                            f'  ⚠️ Trade {old_trade.id} ({old_trade.symbol}): Auto-expirado (más de 2 horas)'
                        )
                    )
            except Exception:
                pass
        
        total_trades = pending_trades.count()
        if total_trades == 0:
            self.stdout.write(self.style.SUCCESS('✅ No hay contratos pendientes para verificar'))
            return
        
        self.stdout.write(f'🔍 Verificando {total_trades} contrato(s) pendiente(s)...')
        
        updated_count = 0
        error_count = 0
        expired_count = 0
        
        for trade in pending_trades:
            try:
                # Obtener contract_id del trade
                contract_id = None
                
                # Intentar desde response_payload
                if trade.response_payload:
                    if isinstance(trade.response_payload, dict):
                        contract_id = (
                            trade.response_payload.get('contract_id') or
                            trade.response_payload.get('order_id') or
                            (trade.response_payload.get('buy', {}).get('contract_id') 
                             if isinstance(trade.response_payload.get('buy'), dict) else None)
                        )
                
                # Si no hay contract_id, intentar marcar como expirado basado en el tiempo
                if not contract_id:
                    # Si el trade tiene más de 2 horas, probablemente expiró
                    trade_age = timezone.now() - trade.timestamp
                    if trade_age > timedelta(hours=2):
                        # Marcar como perdido (expirado)
                        trade.status = 'lost'
                        trade.pnl = -Decimal(str(trade.size or 0))
                        if not trade.response_payload:
                            trade.response_payload = {}
                        trade.response_payload['auto_expired'] = True
                        trade.response_payload['auto_expired_at'] = timezone.now().isoformat()
                        trade.response_payload['reason'] = 'Contrato expirado (sin contract_id, marcado automáticamente)'
                        trade.save()
                        expired_count += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f'  ⚠️ Trade {trade.id} ({trade.symbol}): Sin contract_id, marcado como expirado (edad: {int(trade_age.total_seconds()/60)} min)'
                            )
                        )
                        continue
                    else:
                        # Aún no tiene suficiente edad, saltarlo
                        continue
                
                # Verificar estado del contrato en Deriv
                contract_info = client.get_open_contract_info(str(contract_id))
                
                if contract_info.get('error'):
                    error_msg = contract_info.get('error', 'Error desconocido')
                    error_str = str(error_msg).lower()
                    
                    # Si el error indica que el contrato no existe o expiró
                    if any(keyword in error_str for keyword in ['not found', 'expired', 'invalid', 'does not exist', 'contract_id']):
                        # Marcar como perdido
                        trade.status = 'lost'
                        trade.pnl = -Decimal(str(trade.size or 0))
                        if not trade.response_payload:
                            trade.response_payload = {}
                        trade.response_payload['auto_expired'] = True
                        trade.response_payload['auto_expired_at'] = timezone.now().isoformat()
                        trade.response_payload['error'] = error_msg
                        trade.save()
                        expired_count += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f'  ⚠️ Trade {trade.id} ({trade.symbol}): Contrato expirado/no encontrado: {error_msg}'
                            )
                        )
                    else:
                        # Otro tipo de error, solo loguear
                        error_count += 1
                        self.stdout.write(
                            self.style.ERROR(
                                f'  ❌ Trade {trade.id} ({trade.symbol}): Error verificando contrato: {error_msg}'
                            )
                        )
                    continue
                
                # Verificar si el contrato ya se vendió/cerró
                if contract_info.get('is_sold', False):
                    # El contrato ya se cerró
                    status = contract_info.get('status')  # 'won' o 'lost'
                    profit = Decimal(str(contract_info.get('profit', 0)))
                    
                    trade.status = status if status else ('won' if profit > 0 else 'lost')
                    trade.pnl = profit
                    
                    if not trade.response_payload:
                        trade.response_payload = {}
                    trade.response_payload['auto_updated'] = True
                    trade.response_payload['auto_updated_at'] = timezone.now().isoformat()
                    trade.response_payload['contract_info'] = contract_info
                    
                    trade.save()
                    updated_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  ✅ Trade {trade.id} ({trade.symbol}): Actualizado - Status: {trade.status}, P&L: ${profit:.2f}'
                        )
                    )
                else:
                    # El contrato aún está activo, verificar si debería haber expirado
                    # Basado en la duración del contrato (si está disponible)
                    # Por ahora, solo loguear que está activo
                    trade_age = timezone.now() - trade.timestamp
                    if trade_age > timedelta(hours=1):
                        # Si tiene más de 1 hora, probablemente debería haber expirado
                        # Pero no lo marcamos automáticamente sin confirmar
                        self.stdout.write(
                            self.style.WARNING(
                                f'  ⏳ Trade {trade.id} ({trade.symbol}): Aún activo pero tiene {int(trade_age.total_seconds()/60)} minutos (contract_id: {contract_id})'
                            )
                        )
                
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(
                        f'  ❌ Error procesando trade {trade.id} ({trade.symbol}): {str(e)}'
                    )
                )
                continue
        
        # Resumen
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'📊 Resumen: {updated_count} actualizados, {expired_count} expirados, {error_count} errores'
        ))

