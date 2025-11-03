"""Script para actualizar configuración: 1% stake, 5% max loss, 10% profit target"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from engine.models import CapitalConfig
from decimal import Decimal

print("=" * 80)
print("💰 ACTUALIZANDO CONFIGURACIÓN: 1% Stake, 5% Stop Loss, 10% Take Profit")
print("=" * 80)

config = CapitalConfig.get_active()

print(f"\n📋 CONFIGURACIÓN ACTUAL:")
print(f"   • Risk per Trade: {config.risk_per_trade_pct}%")
print(f"   • Max Loss Diario: {config.max_loss_pct}%")
print(f"   • Profit Target Diario: {config.profit_target_pct}%")

# Actualizar a los valores solicitados
config.risk_per_trade_pct = 1.0  # 1% del balance por trade
config.max_loss_pct = 5.0  # 5% máximo de pérdida diaria
config.profit_target_pct = 10.0  # 10% objetivo de ganancia diaria

# También actualizar valores absolutos para balance de $100
config.max_loss = Decimal('-5.00')  # -$5 máximo
config.profit_target = Decimal('10.00')  # $10 objetivo

config.save()

print(f"\n✅ CONFIGURACIÓN ACTUALIZADA:")
print(f"   • Risk per Trade: {config.risk_per_trade_pct}%")
print(f"   • Max Loss Diario: {config.max_loss_pct}% (${abs(config.max_loss):.2f})")
print(f"   • Profit Target Diario: {config.profit_target_pct}% (${config.profit_target:.2f})")

print(f"\n📊 CON BALANCE DE $100 USD:")
print(f"   • Monto por trade: ${100 * config.risk_per_trade_pct / 100:.2f} ({config.risk_per_trade_pct}%)")
print(f"   • Stop Loss efectivo: {config.max_loss_pct}% = ${abs(config.max_loss):.2f} (equivale a {int(config.max_loss_pct / config.risk_per_trade_pct)} trades perdidos)")
print(f"   • Take Profit objetivo: {config.profit_target_pct}% = ${config.profit_target:.2f}")

print(f"\n💡 EXPLICACIÓN:")
print(f"   En opciones binarias:")
print(f"   • Stop Loss: No existe tradicional. Si pierdes = pierdes el 100% del stake.")
print(f"   • El 'stop loss del 5%' significa: máximo {int(config.max_loss_pct / config.risk_per_trade_pct)} trades perdidos = -{config.max_loss_pct}%")
print(f"   • Take Profit: No existe tradicional. El payout promedio es ~195%.")
print(f"   • El 'take profit del 10%' es tu objetivo diario: ganar ${config.profit_target:.2f} en total.")

print("\n" + "=" * 80)
print("✅ Configuración actualizada exitosamente")
print("=" * 80)

