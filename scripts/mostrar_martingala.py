import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from engine.models import CapitalConfig
from decimal import Decimal

config = CapitalConfig.get_active()

base_amount = float(config.martingale_base_amount)
multiplier = config.martingale_multiplier
max_levels = config.martingale_max_levels

print("=" * 60)
print("📊 TABLA DE MARTINGALA")
print("=" * 60)
print(f"\nConfiguración:")
print(f"  • Monto base: ${base_amount:.2f}")
print(f"  • Multiplicador: {multiplier}x")
print(f"  • Máximo niveles: {max_levels}")
print(f"  • Reset en ganancia: {'Sí' if config.martingale_reset_on_win else 'No'}")
print("\n" + "=" * 60)
print("EVOLUCIÓN DE MONTOS POR NIVEL:")
print("=" * 60)
print(f"{'Nivel':<8} {'Resultado Anterior':<20} {'Monto Trade':<15} {'Acumulado'}")
print("-" * 60)

amount = base_amount
total_invested = 0

for level in range(1, max_levels + 1):
    if level == 1:
        result = "Inicio"
    else:
        result = "Pérdida"
    
    total_invested += amount
    
    print(f"{level:<8} {result:<20} ${amount:>10.2f}     ${total_invested:>10.2f}")
    
    # Calcular siguiente monto
    amount = base_amount * (multiplier ** (level))

print("-" * 60)
print(f"\n💡 Si gana en cualquier nivel → Vuelve a ${base_amount:.2f}")
print(f"⚠️  Capital necesario para {max_levels} pérdidas: ${total_invested:.2f}")
print("=" * 60)

