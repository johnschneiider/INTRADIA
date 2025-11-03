"""Script para mostrar información sobre Take Profit / Payout"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from engine.models import CapitalConfig
from monitoring.models import OrderAudit
from datetime import timedelta
from django.utils import timezone
from decimal import Decimal

print("=" * 80)
print("💰 INFORMACIÓN SOBRE TAKE PROFIT / PAYOUT")
print("=" * 80)

config = CapitalConfig.get_active()

print("\n📊 METAS DIARIAS DE GANANCIA:")
print(f"   • Profit Target (fijo): ${config.profit_target:.2f}")
print(f"   • Profit Target (%): {config.profit_target_pct}% del balance inicial")
print(f"   • Max Loss (fijo): ${config.max_loss:.2f}")
print(f"   • Max Loss (%): {config.max_loss_pct}% del balance inicial")

print("\n🛡️ PROTECCIÓN DE GANANCIAS (Trailing Stop):")
print(f"   • Trailing Stop: {'✅ ACTIVADO' if config.enable_trailing_stop else '❌ DESACTIVADO'}")
if config.enable_trailing_stop:
    print(f"   • Distancia del Trailing Stop: {config.trailing_stop_distance_pct}%")
    print(f"   • Ganancia mínima para activar: {config.min_profit_for_trailing_pct}%")

print("\n📈 PAYOUT EN OPCIONES BINARIAS:")
print("   En opciones binarias NO hay 'take profit' tradicional.")
print("   El 'payout' es el retorno fijo que obtienes si la opción es ganadora.")
print()
print("   Ejemplo:")
print("   • Si apuestas $100 y el payout es 85%")
print("   • Si GANAS: Recibes $185 total ($100 stake + $85 ganancia)")
print("   • Si PIERDES: Pierdes los $100 completos")
print()

# Analizar payouts recientes
since = timezone.now() - timedelta(hours=24)
orders = OrderAudit.objects.filter(
    timestamp__gte=since,
    accepted=True,
    response_payload__isnull=False
).order_by('-timestamp')[:50]

payouts = []
for order in orders:
    if order.response_payload:
        payout = order.response_payload.get('payout', 0)
        buy_price = order.response_payload.get('buy_price', 0)
        if payout and buy_price:
            # Calcular porcentaje de payout
            payout_pct = (float(payout) / float(buy_price)) * 100 if buy_price > 0 else 0
            payouts.append({
                'payout': float(payout),
                'buy_price': float(buy_price),
                'payout_pct': payout_pct,
                'symbol': order.symbol
            })

if payouts:
    avg_payout_pct = sum(p['payout_pct'] for p in payouts) / len(payouts)
    min_payout_pct = min(p['payout_pct'] for p in payouts)
    max_payout_pct = max(p['payout_pct'] for p in payouts)
    
    print("   📊 PAYOUTS RECIENTES (últimas 24h):")
    print(f"      • Payout promedio: {avg_payout_pct:.1f}%")
    print(f"      • Payout mínimo: {min_payout_pct:.1f}%")
    print(f"      • Payout máximo: {max_payout_pct:.1f}%")
    print(f"      • Cantidad de operaciones analizadas: {len(payouts)}")
    print()
    print("   💡 Esto significa:")
    print(f"      • Por cada $100 apostados, ganas ~${avg_payout_pct:.1f} si la opción es ganadora")
    print(f"      • El retorno efectivo es aproximadamente {avg_payout_pct:.1f}% por trade ganador")
else:
    print("   ⚠️ No hay operaciones recientes con información de payout")

print("\n" + "=" * 80)
print("✅ RESUMEN:")
print("=" * 80)
print("   • Take Profit (diario): ${:.2f} o {:.1f}% del balance".format(
    config.profit_target, config.profit_target_pct))
print("   • Trailing Stop: {} ({:.1f}% de distancia)".format(
    "ACTIVADO" if config.enable_trailing_stop else "DESACTIVADO",
    config.trailing_stop_distance_pct))
if payouts:
    print("   • Payout promedio: {:.1f}% por trade ganador".format(avg_payout_pct))
print("=" * 80)

