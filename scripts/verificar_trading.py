#!/usr/bin/env python3
"""
Script para verificar el estado del trading automático
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

from monitoring.models import OrderAudit
from market.models import Zone, LiquiditySweep, Candle
from django.utils import timezone

print("=" * 60)
print("📊 ESTADO DEL TRADING AUTOMÁTICO")
print("=" * 60)
print()

# 1. Zonas
print("1️⃣ ZONAS DE LIQUIDEZ:")
zones = Zone.objects.all()
print(f"   Total zonas: {zones.count()}")
for z in zones[:5]:
    print(f"   - {z.symbol} | {z.zone_low} - {z.zone_high} | {z.timestamp}")
print()

# 2. Sweeps
print("2️⃣ LIQUIDITY SWEEPS DETECTADOS:")
sweeps = LiquiditySweep.objects.all()
print(f"   Total sweeps: {sweeps.count()}")
for s in sweeps[:5]:
    print(f"   - {s.symbol} | {s.direction} | {s.sweep_time}")
print()

# 3. Operaciones
print("3️⃣ OPERACIONES:")
orders = OrderAudit.objects.all()
print(f"   Total operaciones: {orders.count()}")
print(f"   Aceptadas: {orders.filter(accepted=True).count()}")
print(f"   Rechazadas: {orders.filter(accepted=False).count()}")
print()
print("   Últimas 5 operaciones:")
for o in orders.order_by('-timestamp')[:5]:
    status_emoji = "✅" if o.accepted else "❌"
    print(f"   {status_emoji} {o.timestamp.strftime('%H:%M:%S')} | {o.symbol} | {o.status} | {o.reason}")
print()

# 4. Velas disponibles
print("4️⃣ DATOS DISPONIBLES:")
symbols = ['R_10', 'R_25']
for symbol in symbols:
    candles = Candle.objects.filter(symbol=symbol).count()
    print(f"   {symbol}: {candles} velas en base de datos")
print()

# 5. Último tick
print("5️⃣ ÚLTIMOS TICKS:")
from market.models import Tick
for symbol in symbols:
    tick = Tick.objects.filter(symbol=symbol).order_by('-timestamp').first()
    if tick:
        print(f"   {symbol}: ${tick.price:.2f} - {tick.timestamp.strftime('%H:%M:%S')}")
print()

print("=" * 60)
print("💡 CONCLUSIÓN:")
if zones.count() == 0:
    print("   ❌ No hay zonas detectadas. Necesitas ejecutar refresh_daily_weekly_zones")
elif sweeps.count() == 0:
    print("   ⚠️  No hay sweeps detectados. Espera más datos históricos o ajusta criterios")
elif orders.count() == 0:
    print("   ⚠️  No se han hecho operaciones. La estrategia puede ser muy estricta")
    print("   💡 Revisa los criterios en engine/services/rule_based.py")
else:
    print("   ✅ Sistema funcionando correctamente")
print("=" * 60)
