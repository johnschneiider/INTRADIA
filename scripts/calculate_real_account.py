"""Script para calcular monto por trade con cuenta real de $100"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from engine.models import CapitalConfig
from engine.services.advanced_capital_manager import AdvancedCapitalManager
from decimal import Decimal

print("=" * 80)
print("💰 CÁLCULO CON CUENTA REAL DE $100 USD")
print("=" * 80)

# Simular balance de $100
simulated_balance = Decimal('100.00')

# Obtener configuración
config = CapitalConfig.get_active()

print(f"\n💵 Balance simulado: ${float(simulated_balance):,.2f}")
print(f"\n📋 CONFIGURACIÓN ACTUAL:")
print(f"   • Método: {config.position_sizing_method}")
print(f"   • Risk per Trade: {config.risk_per_trade_pct}%")
print(f"   • Max Amount (% Balance): {config.max_amount_pct_balance}%")
print(f"   • Max Amount Absoluto: ${config.max_amount_absolute:,.2f}")

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

# Calcular position size
position_result = advanced_manager.calculate_position_size(
    current_balance=simulated_balance,
    symbol="R_10",
    entry_price=Decimal("5657.0"),
    stop_loss_price=None,
    atr_value=None
)

amount_calculado = float(position_result.contract_amount)
porcentaje_balance = (amount_calculado / float(simulated_balance)) * 100

print(f"\n📊 CÁLCULO DE POSITION SIZE:")
print(f"   • Amount calculado (base): ${amount_calculado:,.2f}")
print(f"   • Porcentaje del balance: {porcentaje_balance:.2f}%")

# Aplicar límites
max_from_balance = float(simulated_balance) * (config.max_amount_pct_balance / 100)
symbol_limit = config.get_symbol_limit("R_10")
final_amount = min(
    amount_calculado,
    max_from_balance,
    config.max_amount_absolute,
    symbol_limit if symbol_limit else float('inf')
)

porcentaje_final = (final_amount / float(simulated_balance)) * 100

print(f"\n🔒 LÍMITES APLICADOS:")
print(f"   • Max {config.max_amount_pct_balance}% del balance: ${max_from_balance:,.2f}")
if symbol_limit:
    print(f"   • Límite por símbolo: ${symbol_limit:,.2f}")
print(f"   • Max absoluto: ${config.max_amount_absolute:,.2f}")
print(f"\n✅ AMOUNT FINAL: ${final_amount:,.2f}")
print(f"   • Porcentaje final del balance: {porcentaje_final:.2f}%")

# Explicar cómo funciona el riesgo en opciones binarias
print(f"\n" + "=" * 80)
print("⚠️ IMPORTANTE: RIESGO EN OPCIONES BINARIAS")
print("=" * 80)
print(f"""
En opciones binarias NO existe un "stop loss" tradicional como en Forex.
El riesgo está determinado por el STAKE (monto que apuestas):

📊 EJEMPLO CON ${final_amount:,.2f} POR TRADE:
   
   Escenario 1: TRADE GANADOR ✅
   • Inviertes: ${final_amount:,.2f}
   • Ganas: ${final_amount * 0.85:,.2f} aprox. (payout típico ~85%)
   • Ganancia neta: +${final_amount * 0.85:,.2f}
   
   Escenario 2: TRADE PERDEDOR ❌
   • Inviertes: ${final_amount:,.2f}
   • Pierdes: ${final_amount:,.2f} (TODO el stake)
   • Pérdida: -${final_amount:,.2f}
   
   📉 Esto significa que el "STOP LOSS" es inherente:
   • Si el trade pierde = pierdes el ${final_amount:,.2f} completo
   • El riesgo máximo por trade es el 100% del stake invertido
   • No hay "stop loss parcial" - es todo o nada

💡 CON UN BALANCE DE $100:
   • Por trade inviertes: ${final_amount:,.2f} ({porcentaje_final:.2f}% del balance)
   • Si pierdes: Balance baja a ${float(simulated_balance) - final_amount:,.2f}
   • Si ganas: Balance sube a ${float(simulated_balance) + (final_amount * 0.85):,.2f}
   
📊 RIESGO POR TRADE:
   • Riesgo máximo: {porcentaje_final:.2f}% del balance (${final_amount:,.2f})
   • Esto es equivalente a un "stop loss" del {porcentaje_final:.2f}% del balance
   
⚠️ RECOMENDACIÓN:
   Con ${float(simulated_balance):,.2f} en cuenta, considera:
   • Reducir el Risk per Trade a 0.5% = ${float(simulated_balance) * 0.005:,.2f} por trade
   • O mantener {porcentaje_final:.2f}% pero asegurar un buen win rate (>60%)
""")

print("\n" + "=" * 80)

