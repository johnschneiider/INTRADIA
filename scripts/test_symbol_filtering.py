"""
Script para verificar el filtro de símbolos con bajo win rate
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from engine.services.statistical_strategy import StatisticalStrategy
from monitoring.models import OrderAudit

print("=" * 80)
print("🚫 VERIFICACIÓN DEL FILTRO DE SÍMBOLOS")
print("=" * 80)

strategy = StatisticalStrategy(
    enable_symbol_filtering=True,
    min_trades_for_filtering=5,
    min_win_rate_threshold=0.30  # 30%
)

# Verificar win rate por símbolo
symbols_to_check = ['RDBULL', 'RDBEAR', 'R_100', 'R_10', 'R_25', 'R_50', 'R_75']

print(f"\n📊 WIN RATE POR SÍMBOLO:")
print(f"   (Mínimo {strategy.min_trades_for_filtering} trades para filtrar)")
print(f"   (Win rate mínimo: {strategy.min_win_rate_threshold*100:.1f}%)\n")

for symbol in symbols_to_check:
    win_rate = strategy.get_symbol_win_rate(symbol)
    should_skip = strategy.should_skip_symbol(symbol)
    
    if win_rate is None:
        trades_count = OrderAudit.objects.filter(
            symbol=symbol,
            accepted=True,
            status__in=['won', 'lost']
        ).count()
        print(f"   • {symbol}: {trades_count} trades (insuficientes datos) ✅ Permitido")
    else:
        trades_count = OrderAudit.objects.filter(
            symbol=symbol,
            accepted=True,
            status__in=['won', 'lost']
        ).count()
        won_count = OrderAudit.objects.filter(
            symbol=symbol,
            accepted=True,
            status='won'
        ).count()
        
        status = "🚫 EXCLUIDO" if should_skip else "✅ Permitido"
        print(f"   • {symbol}: {win_rate*100:.1f}% ({won_count}/{trades_count}) {status}")

print(f"\n💡 CONFIGURACIÓN ACTUAL:")
print(f"   • Filtrado habilitado: {strategy.enable_symbol_filtering}")
print(f"   • Mínimo trades: {strategy.min_trades_for_filtering}")
print(f"   • Win rate mínimo: {strategy.min_win_rate_threshold*100:.1f}%")

print(f"\n📈 IMPACTO:")
print(f"   • Símbolos con win rate < {strategy.min_win_rate_threshold*100:.1f}% serán excluidos")
print(f"   • Esto mejora la calidad general de trades")
print(f"   • Los símbolos excluidos pueden volver a operarse si mejoran su win rate")

print("\n" + "=" * 80)
print("✅ Filtro de símbolos verificado")
print("=" * 80)

