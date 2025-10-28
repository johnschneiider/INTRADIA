"""
Script para ver el estado actual de las órdenes
"""
import os
import sys
import django

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from monitoring.models import OrderAudit
from django.utils import timezone
from datetime import timedelta

print('\n📊 Estado actual de órdenes\n')

total = OrderAudit.objects.count()
print(f'Total de órdenes: {total}')

# Contar por estado
statuses = ['pending', 'active', 'won', 'lost', 'cancelled']
for status in statuses:
    count = OrderAudit.objects.filter(status=status).count()
    if count > 0:
        print(f'  - {status}: {count}')

# Ver las más recientes
print('\n🕒 Últimas 10 órdenes:')
recent = OrderAudit.objects.all().order_by('-timestamp')[:10]
for order in recent:
    age = timezone.now() - order.timestamp
    print(f"  {order.timestamp.strftime('%Y-%m-%d %H:%M:%S')} | {order.status:10} | {age} ago")

# Ver órdenes pendientes/activas antiguas (más de 1 hora)
print('\n⚠️  Órdenes pendientes/activas antiguas (>1 hora):')
old_time = timezone.now() - timedelta(hours=1)
old_orders = OrderAudit.objects.filter(
    status__in=['pending', 'active'],
    timestamp__lt=old_time
)
print(f'  Total antiguas: {old_orders.count()}')

for order in old_orders[:5]:
    age = timezone.now() - order.timestamp
    print(f"    {order.timestamp.strftime('%Y-%m-%d %H:%M:%S')} | {order.status} | {age} ago")

