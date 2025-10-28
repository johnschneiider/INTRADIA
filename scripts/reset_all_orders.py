"""
Script para eliminar TODAS las órdenes y reiniciar completamente las métricas
"""
import os
import sys
import django

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
    print('\n🔄 Eliminando TODAS las órdenes (reset completo)...\n')
    
    # Contar registros antes
    total_before = OrderAudit.objects.count()
    
    # Contar por estado
    won_before = OrderAudit.objects.filter(status='won').count()
    lost_before = OrderAudit.objects.filter(status='lost').count()
    pending_before = OrderAudit.objects.filter(status='pending').count()
    active_before = OrderAudit.objects.filter(status='active').count()
    
    print(f'📊 Registros antes:')
    print(f'   - Total: {total_before}')
    print(f'   - Ganadas: {won_before}')
    print(f'   - Perdidas: {lost_before}')
    print(f'   - Pendientes: {pending_before}')
    print(f'   - Activas: {active_before}')
    print('')
    
    # ELIMINAR TODAS LAS ÓRDENES
    deleted_count, _ = OrderAudit.objects.all().delete()
    print(f'✅ Eliminadas {deleted_count} órdenes (TODAS)')
    
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
    
    print(f'\n📊 Registros después:')
    print(f'   - Total: {total_after}')
    
    print('\n✅ ¡Reset completo exitoso!')
    print('📈 Todas las órdenes eliminadas, winrate, trades y P&L están en cero')
    print('🚀 Ahora puedes empezar de nuevo desde cero\n')

if __name__ == '__main__':
    main()

