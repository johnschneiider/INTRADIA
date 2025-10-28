"""
Comando para limpiar operaciones antiguas de la base de datos
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from monitoring.models import OrderAudit


class Command(BaseCommand):
    help = 'Limpia operaciones antiguas de la base de datos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=int,
            default=2,
            help='Mantener operaciones de las últimas N horas (default: 2)'
        )

    def handle(self, *args, **options):
        hours = options['hours']
        since = timezone.now() - timedelta(hours=hours)
        
        # Contar operaciones a eliminar
        old_trades = OrderAudit.objects.filter(timestamp__lt=since)
        count = old_trades.count()
        
        self.stdout.write(f'🗑️  Eliminando operaciones anteriores a {hours} horas...')
        self.stdout.write(f'   Total a eliminar: {count} operaciones')
        
        if count > 0:
            # Eliminar
            old_trades.delete()
            self.stdout.write(
                self.style.SUCCESS(f'✅ Se eliminaron {count} operaciones antiguas')
            )
        else:
            self.stdout.write('✅ No hay operaciones antiguas para eliminar')
        
        # Mostrar estadísticas actuales
        self.stdout.write('')
        self.stdout.write('📊 Operaciones actuales:')
        total = OrderAudit.objects.count()
        pending = OrderAudit.objects.filter(status='pending').count()
        won = OrderAudit.objects.filter(status='won').count()
        lost = OrderAudit.objects.filter(status='lost').count()
        
        self.stdout.write(f'   Total: {total}')
        self.stdout.write(f'   Pendientes: {pending}')
        self.stdout.write(f'   Ganadas: {won} ✅')
        self.stdout.write(f'   Perdidas: {lost} ❌')

