#!/usr/bin/env python3
"""
Listar todos los instrumentos disponibles en la base de datos
"""

import os
import sys
import django
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from market.models import Tick
from django.utils import timezone
from datetime import timedelta

# Obtener todos los símbolos que tienen ticks recientes (últimas 24 horas)
since = timezone.now() - timedelta(hours=24)
symbols = Tick.objects.filter(timestamp__gte=since).values_list('symbol', flat=True).distinct()

print("=" * 60)
print("INSTRUMENTOS DISPONIBLES")
print("=" * 60)
print()

for symbol in sorted(symbols):
    tick_count = Tick.objects.filter(symbol=symbol).count()
    latest_tick = Tick.objects.filter(symbol=symbol).order_by('-timestamp').first()
    if latest_tick:
        print(f"  • {symbol}: {tick_count} ticks | Último: {latest_tick.price} @ {latest_tick.timestamp.strftime('%H:%M:%S')}")
    else:
        print(f"  • {symbol}: {tick_count} ticks")

print()
print(f"Total: {len(symbols)} instrumentos activos")
print("=" * 60)
