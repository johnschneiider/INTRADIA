"""Diagnóstico de amounts en órdenes rechazadas"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from monitoring.models import OrderAudit
from django.utils import timezone
from datetime import timedelta
import json

print("=" * 80)
print("🔍 DIAGNÓSTICO DE AMOUNTS EN ÓRDENES RECHAZADAS")
print("=" * 80)

cutoff = timezone.now() - timedelta(hours=2)
rejected = OrderAudit.objects.filter(
    timestamp__gte=cutoff,
    status='rejected',
    error_message__icontains='maximum purchase price'
).order_by('-timestamp')[:5]

for order in rejected:
    print(f"\n📋 {order.symbol} {order.action.upper()} @ ${order.price}")
    print(f"   Hora: {order.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Extraer amount del request_payload
    if order.request_payload:
        try:
            payload = json.loads(order.request_payload) if isinstance(order.request_payload, str) else order.request_payload
            if 'parameters' in payload:
                amount = payload['parameters'].get('amount')
                duration = payload['parameters'].get('duration')
                print(f"   💰 Amount enviado: ${amount}")
                print(f"   ⏱️  Duration: {duration}s")
        except Exception as e:
            print(f"   ⚠️  Error leyendo payload: {e}")
    
    if order.error_message:
        print(f"   ❌ Error: {order.error_message[:200]}")

print("\n" + "=" * 80)

