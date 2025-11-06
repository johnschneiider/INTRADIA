"""
Comando para limpiar trades antiguos que están pendientes desde hace horas
Marca automáticamente como perdidos los trades que tienen más de X horas
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from monitoring.models import OrderAudit


class Command(BaseCommand):
    help = 'Limpiar trades antiguos marcándolos como expirados/perdidos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=float,
            default=2.0,
            help='Marcar como expirados trades más antiguos que X horas (default: 2.0)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar qué se haría sin hacer cambios',
        )

    def handle(self, *args, **options):
        hours = options['hours']
        dry_run = options['dry_run']
        
        cutoff_time = timezone.now() - timedelta(hours=hours)
        
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(self.style.SUCCESS(f'🧹 LIMPIEZA DE TRADES ANTIGUOS'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(f'\n📅 Marcando como expirados trades más antiguos que {hours} horas')
        self.stdout.write(f'   Fecha límite: {cutoff_time.strftime("%Y-%m-%d %H:%M:%S")}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n⚠️  MODO DRY-RUN: No se harán cambios'))
        
        # Buscar trades antiguos pendientes/activos
        old_trades = OrderAudit.objects.filter(
            status__in=['pending', 'active', 'open'],
            timestamp__lt=cutoff_time
        ).order_by('timestamp')
        
        total = old_trades.count()
        
        if total == 0:
            self.stdout.write(self.style.SUCCESS('\n✅ No hay trades antiguos para limpiar'))
            return
        
        self.stdout.write(f'\n📊 Trades encontrados: {total}')
        self.stdout.write('=' * 80)
        
        updated_count = 0
        error_count = 0
        
        for trade in old_trades:
            try:
                age_hours = (timezone.now() - trade.timestamp).total_seconds() / 3600
                
                self.stdout.write(f'\n📋 Trade ID: {trade.id}')
                self.stdout.write(f'   Símbolo: {trade.symbol}')
                self.stdout.write(f'   Estado actual: {trade.status}')
                self.stdout.write(f'   Timestamp: {trade.timestamp}')
                self.stdout.write(f'   Edad: {age_hours:.2f} horas')
                
                if not dry_run:
                    # Marcar como perdido (expirado)
                    trade.status = 'lost'
                    # P&L = monto negativo (pérdida completa del stake)
                    trade.pnl = -Decimal(str(trade.size or 0))
                    
                    # Actualizar response_payload con información de expiración
                    if not trade.response_payload:
                        trade.response_payload = {}
                    elif isinstance(trade.response_payload, str):
                        import json
                        try:
                            trade.response_payload = json.loads(trade.response_payload)
                        except:
                            trade.response_payload = {}
                    
                    trade.response_payload['auto_expired'] = True
                    trade.response_payload['auto_expired_at'] = timezone.now().isoformat()
                    trade.response_payload['age_hours'] = round(age_hours, 2)
                    trade.response_payload['reason'] = f'Contrato expirado automáticamente (más de {hours} horas en estado {trade.status})'
                    
                    trade.save(update_fields=['status', 'pnl', 'response_payload'])
                    updated_count += 1
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'   ✅ Marcado como LOST (expirado) - P&L: ${trade.pnl:.2f}'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'   ⚠️  Se marcaría como LOST - P&L: ${-Decimal(str(trade.size or 0)):.2f}'
                        )
                    )
                    updated_count += 1
                    
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f'   ❌ Error procesando trade {trade.id}: {e}')
                )
                continue
        
        # Resumen
        self.stdout.write('\n' + '=' * 80)
        if dry_run:
            self.stdout.write(self.style.WARNING(f'📊 Resumen (DRY-RUN): {updated_count} trades se marcarían como expirados'))
            self.stdout.write(self.style.WARNING('   Ejecuta sin --dry-run para aplicar los cambios'))
        else:
            self.stdout.write(self.style.SUCCESS(f'📊 Resumen: {updated_count} trades actualizados, {error_count} errores'))
        
        if updated_count > 0 and not dry_run:
            self.stdout.write(self.style.SUCCESS(f'\n✅ {updated_count} trades antiguos limpiados exitosamente'))

