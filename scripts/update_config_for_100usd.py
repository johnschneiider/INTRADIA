"""Script para actualizar configuración para cuenta de $100 USD"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from engine.models import CapitalConfig
from decimal import Decimal

print("=" * 80)
print("💰 ACTUALIZANDO CONFIGURACIÓN PARA CUENTA DE $100 USD")
print("=" * 80)

config = CapitalConfig.get_active()

print(f"\n📋 CONFIGURACIÓN ACTUAL:")
print(f"   • Risk per Trade: {config.risk_per_trade_pct}%")
print(f"   • Max Amount (% Balance): {config.max_amount_pct_balance}%")
print(f"   • Max Amount Absoluto: ${config.max_amount_absolute:,.2f}")
print(f"   • Min Amount: ${config.min_amount_per_trade:,.2f}")

# Actualizar valores para cuenta de $100
config.risk_per_trade_pct = 0.5  # 0.5% = $0.50 por trade
config.max_amount_pct_balance = 2.0  # Máximo 2% = $2.00
config.max_amount_absolute = 5.0  # Máximo $5.00 absoluto
config.min_amount_per_trade = 0.50  # Mínimo $0.50

config.save()

print(f"\n✅ CONFIGURACIÓN ACTUALIZADA:")
print(f"   • Risk per Trade: {config.risk_per_trade_pct}% (${100 * config.risk_per_trade_pct / 100:.2f} por trade con $100)")
print(f"   • Max Amount (% Balance): {config.max_amount_pct_balance}% (${100 * config.max_amount_pct_balance / 100:.2f} máximo con $100)")
print(f"   • Max Amount Absoluto: ${config.max_amount_absolute:,.2f}")
print(f"   • Min Amount: ${config.min_amount_per_trade:,.2f}")

print(f"\n📊 RESUMEN PARA CUENTA DE $100:")
print(f"   • Amount por trade: ~${100 * config.risk_per_trade_pct / 100:.2f} ({config.risk_per_trade_pct}% del balance)")
print(f"   • Máximo permitido: ${100 * config.max_amount_pct_balance / 100:.2f} ({config.max_amount_pct_balance}% del balance)")
print(f"   • Trades posibles antes de perder todo: {int(100 / (100 * config.risk_per_trade_pct / 100))} trades")

print("\n" + "=" * 80)
print("✅ Configuración actualizada exitosamente")
print("=" * 80)

