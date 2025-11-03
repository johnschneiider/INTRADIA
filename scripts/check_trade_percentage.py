"""Script para verificar qué porcentaje del capital se invierte en cada operación"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from engine.models import CapitalConfig
from connectors.deriv_client import DerivClient
from engine.services.advanced_capital_manager import AdvancedCapitalManager
from decimal import Decimal

print("=" * 80)
print("📊 ANÁLISIS: PORCENTAJE DEL CAPITAL POR OPERACIÓN")
print("=" * 80)

# Obtener configuración
config = CapitalConfig.get_active()
client = DerivClient()

if not client.authenticate():
    print("❌ Error autenticando con Deriv")
    sys.exit(1)

balance_data = client.get_balance()
current_balance = float(balance_data.get('balance', 0))

print(f"\n💰 Balance actual: ${current_balance:,.2f}")
print(f"\n📋 CONFIGURACIÓN ACTUAL:")
print(f"   • Método de Position Sizing: {config.position_sizing_method}")
print(f"   • Risk per Trade (%): {config.risk_per_trade_pct}%")
print(f"   • Max Risk per Trade (%): {config.max_risk_per_trade_pct}%")
print(f"   • Max Amount (% Balance): {config.max_amount_pct_balance}%")
print(f"   • Max Amount Absoluto: ${config.max_amount_absolute:,.2f}")
print(f"   • Min Amount: ${config.min_amount_per_trade:,.2f}")

# Crear Advanced Capital Manager
advanced_manager = AdvancedCapitalManager(
    profit_target=config.profit_target,
    max_loss=config.max_loss,
    max_trades=config.max_trades,
    profit_target_pct=config.profit_target_pct,
    max_loss_pct=config.max_loss_pct,
    position_sizing_method=config.position_sizing_method,
    kelly_fraction=config.kelly_fraction,
    risk_per_trade_pct=config.risk_per_trade_pct,
    max_risk_per_trade_pct=config.max_risk_per_trade_pct,
)

# Calcular position size para diferentes escenarios
print(f"\n📈 CÁLCULO DE POSITION SIZE:")

# Escenario 1: Trade normal (sin estadísticas previas)
position_result = advanced_manager.calculate_position_size(
    current_balance=Decimal(str(current_balance)),
    symbol="R_10",
    entry_price=Decimal("5657.0"),
    stop_loss_price=None,
    atr_value=None
)

print(f"\n   Escenario: Trade normal (R_10)")
print(f"   • Amount calculado: ${float(position_result.contract_amount):,.2f}")
print(f"   • Porcentaje del balance: {(float(position_result.contract_amount) / current_balance * 100):.2f}%")
print(f"   • Método usado: {position_result.method_used}")

# Verificar límites aplicados
max_from_balance = current_balance * (config.max_amount_pct_balance / 100)
final_amount = min(
    float(position_result.contract_amount),
    max_from_balance,
    config.max_amount_absolute,
    config.get_symbol_limit("R_10") or float('inf')
)

print(f"\n   Límites aplicados:")
print(f"   • Max {config.max_amount_pct_balance}% del balance: ${max_from_balance:,.2f}")
if config.get_symbol_limit("R_10"):
    print(f"   • Límite por símbolo R_10: ${config.get_symbol_limit('R_10'):,.2f}")
print(f"   • Max absoluto: ${config.max_amount_absolute:,.2f}")
print(f"   • Amount final (después de límites): ${final_amount:,.2f}")
print(f"   • Porcentaje final del balance: {(final_amount / current_balance * 100):.2f}%")

print(f"\n📊 RESUMEN:")
print(f"   El sistema está configurado para invertir aproximadamente:")
print(f"   • Base: {config.risk_per_trade_pct}% del balance (método: {config.position_sizing_method})")
print(f"   • Máximo permitido: {config.max_amount_pct_balance}% del balance")
print(f"   • Con límites aplicados, se invierte: {(final_amount / current_balance * 100):.2f}% del balance")

print("\n" + "=" * 80)

