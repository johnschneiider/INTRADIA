"""
Script simple para reiniciar métricas de trading
"""
import os
import sys
import django

# Agregar el directorio raíz del proyecto al path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from monitoring.models import OrderAudit
from trading_bot.models import TradingStrategy, TradingBot

def main():
    print('\n🔄 Reiniciando métricas de trading...\n')
    
    # Contar registros antes
    total_before = OrderAudit.objects.count()
    won_before = OrderAudit.objects.filter(status='won').count()
    lost_before = OrderAudit.objects.filter(status='lost').count()
    
    print(f'📊 Registros actuales:')
    print(f'   - Total: {total_before}')
    print(f'   - Ganadas: {won_before}')
    print(f'   - Perdidas: {lost_before}')
    print('')
    
    # Eliminar solo órdenes confirmadas (won/lost)
    print('⚠️  Se eliminarán las órdenes confirmadas (won/lost)')
    confirm = input('¿Continuar? (s/n): ')
    
    if confirm.lower() != 's':
        print('❌ Operación cancelada')
        return
    
    deleted_count, _ = OrderAudit.objects.filter(status__in=['won', 'lost']).delete()
    print(f'✅ Eliminados {deleted_count} registros de órdenes confirmadas')
    
    # Reiniciar contadores en TradingStrategy
    strategies_reset = TradingStrategy.objects.all().update(
        total_trades=0,
        winning_trades=0,
        losing_trades=0,
        total_profit=0.0
    )
    print(f'✅ Reseteadas {strategies_reset} estrategias')
    
    # Reiniciar contadores en TradingBot
    bots_reset = TradingBot.objects.all().update(
        today_trades=0,
        today_profit=0.0,
        today_wins=0,
        today_losses=0
    )
    print(f'✅ Reseteados {bots_reset} bots')
    
    # Contar registros después
    total_after = OrderAudit.objects.count()
    won_after = OrderAudit.objects.filter(status='won').count()
    lost_after = OrderAudit.objects.filter(status='lost').count()
    
    print('\n📊 Registros finales:')
    print(f'   - Total: {total_after}')
    print(f'   - Ganadas: {won_after}')
    print(f'   - Perdidas: {lost_after}')
    
    print('\n✅ ¡Métricas reiniciadas exitosamente!')
    print('📈 El winrate, trades totales y P&L ahora están en cero\n')

if __name__ == '__main__':
    main()

