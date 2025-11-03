"""
Script para verificar que los controles rápidos funcionan correctamente
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from engine.models import CapitalConfig
from decimal import Decimal

print("=" * 80)
print("✅ VERIFICACIÓN DE CONTROLES RÁPIDOS")
print("=" * 80)

config = CapitalConfig.get_active()

print(f"\n📋 CONFIGURACIÓN ACTUAL:")
print(f"   • Desactivar límite de trades: {config.disable_max_trades}")
print(f"   • Desactivar meta de ganancia: {config.disable_profit_target}")
print(f"   • Stop loss por monto: ${config.stop_loss_amount:.2f}")

print(f"\n📊 COMPORTAMIENTO ESPERADO:")
if config.disable_max_trades:
    print(f"   ✅ Límite de trades: DESACTIVADO (trading ilimitado)")
else:
    print(f"   ⚠️  Límite de trades: ACTIVO ({config.max_trades} trades/día)")

if config.disable_profit_target:
    print(f"   ✅ Meta de ganancia: DESACTIVADA (trading continuo)")
else:
    print(f"   ⚠️  Meta de ganancia: ACTIVA (${config.profit_target:.2f})")

if config.stop_loss_amount > 0:
    print(f"   ✅ Stop Loss por monto: ACTIVO (${config.stop_loss_amount:.2f})")
    print(f"      → El trading se detendrá al perder ${config.stop_loss_amount:.2f}")
else:
    print(f"   ⚠️  Stop Loss por monto: DESACTIVADO")

print(f"\n💡 USO:")
print(f"   1. Abre el modal desde el botón ⏱️ en el header")
print(f"   2. Marca las casillas para desactivar límites")
print(f"   3. Ingresa un monto en 'Stop Loss por Monto' si quieres límite de pérdida")
print(f"   4. Los cambios se aplican INMEDIATAMENTE en el trading loop")

print("\n" + "=" * 80)

