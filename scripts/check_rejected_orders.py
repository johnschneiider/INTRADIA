"""Script para revisar órdenes rechazadas y sus razones"""
import os
import sys
import django

# Configurar Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from monitoring.models import OrderAudit
from django.utils import timezone
from datetime import timedelta
from collections import Counter

print("=" * 80)
print("🔍 ANÁLISIS DE ÓRDENES RECHAZADAS")
print("=" * 80)

# Obtener órdenes rechazadas de las últimas 2 horas
cutoff = timezone.now() - timedelta(hours=2)
rejected_orders = OrderAudit.objects.filter(
    timestamp__gte=cutoff,
    status='rejected'
).order_by('-timestamp')

print(f"\n📊 Total de órdenes rechazadas (últimas 2h): {rejected_orders.count()}")
print("\n" + "-" * 80)

# Agrupar por razón
reasons = Counter()
symbols_rejected = Counter()

for order in rejected_orders[:20]:  # Mostrar últimas 20
    reason = order.reason or 'unknown'
    reasons[reason] += 1
    symbols_rejected[f"{order.symbol} ({order.action})"] += 1
    
    print(f"\n{order.symbol} {order.action.upper()} @ ${order.price}")
    print(f"  📅 {order.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  ❌ Razón: {reason}")
    if order.error_message:
        error_preview = order.error_message[:150] if len(order.error_message) > 150 else order.error_message
        print(f"  ⚠️  Error: {error_preview}")

print("\n" + "=" * 80)
print("📈 ESTADÍSTICAS")
print("=" * 80)
print("\n🔝 Razones más comunes:")
for reason, count in reasons.most_common(10):
    print(f"  • {reason}: {count} veces")

print("\n🔝 Símbolos más rechazados:")
for symbol, count in symbols_rejected.most_common(10):
    print(f"  • {symbol}: {count} veces")

print("\n" + "=" * 80)

