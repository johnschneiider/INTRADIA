"""
Script automático para reiniciar métricas de trading (sin confirmación)
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
try:
    from trading_bot.models import TradingStrategy, TradingBot
    HAS_TRADING_BOT = True
except:
    HAS_TRADING_BOT = False

def main():
    print('\n🔄 Reiniciando métricas de trading automáticamente...\n')
    
    # Contar registros antes
    total_before = OrderAudit.objects.count()
    won_before = OrderAudit.objects.filter(status='won').count()
    lost_before = OrderAudit.objects.filter(status='lost').count()
    
    print(f'📊 Registros antes:')
    print(f'   - Total: {total_before}')
    print(f'   - Ganadas: {won_before}')
    print(f'   - Perdidas: {lost_before}')
    print('')
    
    # Eliminar solo órdenes confirmadas (won/lost)
    deleted_count, _ = OrderAudit.objects.filter(status__in=['won', 'lost']).delete()
    print(f'✅ Eliminados {deleted_count} registros de órdenes confirmadas')
    
    # Reiniciar contadores en TradingStrategy (si existe)
    if HAS_TRADING_BOT:
        try:
            strategies_reset = TradingStrategy.objects.all().update(
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                total_profit=0.0
            )
            print(f'✅ Reseteadas {strategies_reset} estrategias')
        except:
            print('⚠️  No se pudo resetear estrategias (tabla no existe)')
        
        try:
            bots_reset = TradingBot.objects.all().update(
                today_trades=0,
                today_profit=0.0,
                today_wins=0,
                today_losses=0
            )
            print(f'✅ Reseteados {bots_reset} bots')
        except:
            print('⚠️  No se pudo resetear bots (tabla no existe)')
    
    # Contar registros después
    total_after = OrderAudit.objects.count()
    won_after = OrderAudit.objects.filter(status='won').count()
    lost_after = OrderAudit.objects.filter(status='lost').count()
    
    print('\n📊 Registros después:')
    print(f'   - Total: {total_after}')
    print(f'   - Ganadas: {won_after}')
    print(f'   - Perdidas: {lost_after}')
    
    print('\n✅ ¡Métricas reiniciadas exitosamente!')
    print('📈 El winrate, trades totales y P&L ahora están en cero\n')

if __name__ == '__main__':
    main()

