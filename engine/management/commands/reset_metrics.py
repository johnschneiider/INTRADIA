"""
Comando para reiniciar métricas de trading (winrate, trades totales, P&L)
"""
from django.core.management.base import BaseCommand
from monitoring.models import OrderAudit
try:
    from trading_bot.models import TradingStrategy, TradingBot
    HAS_TRADING_BOT = True
except ImportError:
    HAS_TRADING_BOT = False


class Command(BaseCommand):
    help = 'Reinicia las métricas de trading (winrate, trades totales, P&L)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Elimina TODOS los registros de órdenes (incluyendo pendientes)',
        )
        parser.add_argument(
            '--confirmed-only',
            action='store_true',
            default=True,
            help='Solo elimina órdenes confirmadas (won/lost)',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('\n🔄 Reiniciando métricas de trading...\n'))
        
        # Contar registros antes
        total_before = OrderAudit.objects.count()
        won_before = OrderAudit.objects.filter(status='won').count()
        lost_before = OrderAudit.objects.filter(status='lost').count()
        
        self.stdout.write(f'📊 Registros actuales:')
        self.stdout.write(f'   - Total: {total_before}')
        self.stdout.write(f'   - Ganadas: {won_before}')
        self.stdout.write(f'   - Perdidas: {lost_before}')
        self.stdout.write('')
        
        # Confirmar antes de eliminar
        if options['all']:
            self.stdout.write(self.style.ERROR('⚠️  Se eliminarán TODOS los registros de órdenes'))
            confirm = input('¿Estás seguro? (escribe "SI" para confirmar): ')
            if confirm != 'SI':
                self.stdout.write(self.style.WARNING('❌ Operación cancelada'))
                return
            
            deleted_count, _ = OrderAudit.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f'✅ Eliminados {deleted_count} registros de OrderAudit'))
        
        elif options['confirmed_only']:
            self.stdout.write(self.style.WARNING('⚠️  Se eliminarán las órdenes confirmadas (won/lost)'))
            confirm = input('¿Continuar? (s/n): ')
            if confirm.lower() != 's':
                self.stdout.write(self.style.WARNING('❌ Operación cancelada'))
                return
            
            deleted_count, _ = OrderAudit.objects.filter(status__in=['won', 'lost']).delete()
            self.stdout.write(self.style.SUCCESS(f'✅ Eliminados {deleted_count} registros de órdenes confirmadas'))
        
        # Reiniciar contadores en TradingStrategy (si existe la app)
        if HAS_TRADING_BOT:
            strategies_reset = TradingStrategy.objects.all().update(
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                total_profit=0.0
            )
            self.stdout.write(self.style.SUCCESS(f'✅ Reseteadas {strategies_reset} estrategias'))
            
            # Reiniciar contadores en TradingBot
            bots_reset = TradingBot.objects.all().update(
                today_trades=0,
                today_profit=0.0,
                today_wins=0,
                today_losses=0
            )
            self.stdout.write(self.style.SUCCESS(f'✅ Reseteados {bots_reset} bots'))
        
        # Contar registros después
        total_after = OrderAudit.objects.count()
        won_after = OrderAudit.objects.filter(status='won').count()
        lost_after = OrderAudit.objects.filter(status='lost').count()
        
        self.stdout.write('\n📊 Registros finales:')
        self.stdout.write(f'   - Total: {total_after}')
        self.stdout.write(f'   - Ganadas: {won_after}')
        self.stdout.write(f'   - Perdidas: {lost_after}')
        
        self.stdout.write('\n' + self.style.SUCCESS('✅ ¡Métricas reiniciadas exitosamente!'))
        self.stdout.write(self.style.SUCCESS('📈 El winrate, trades totales y P&L ahora están en cero\n'))

