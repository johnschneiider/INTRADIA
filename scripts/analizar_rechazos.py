#!/usr/bin/env python3
"""
Script para analizar órdenes rechazadas y sus motivos
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
from django.utils import timezone
from datetime import timedelta

# Analizar últimos 24 horas
since = timezone.now() - timedelta(hours=24)

print("\n" + "="*80)
print("📊 ANÁLISIS DE ÓRDENES RECHAZADAS")
print("="*80 + "\n")

# Totales
total_accepted = OrderAudit.objects.filter(accepted=True, timestamp__gte=since).count()
total_rejected = OrderAudit.objects.filter(accepted=False, timestamp__gte=since).count()
total = total_accepted + total_rejected

print(f"📈 Total órdenes: {total}")
print(f"✅ Aceptadas: {total_accepted} ({total_accepted/total*100 if total > 0 else 0:.1f}%)")
print(f"❌ Rechazadas: {total_rejected} ({total_rejected/total*100 if total > 0 else 0:.1f}%)")
print()

# Motivos de rechazo
if total_rejected > 0:
    print("="*80)
    print("📋 MOTIVOS DE RECHAZO")
    print("="*80 + "\n")
    
    reasons = {}
    for order in OrderAudit.objects.filter(accepted=False, timestamp__gte=since):
        reason = order.reason or 'unknown'
        reasons[reason] = reasons.get(reason, 0) + 1
    
    for reason, count in sorted(reasons.items(), key=lambda x: x[1], reverse=True):
        pct = count / total_rejected * 100
        print(f"  {reason:30s} : {count:4d} ({pct:5.1f}%)")

# Muestras de rechazadas
if total_rejected > 0:
    print("\n" + "="*80)
    print("🔍 MUESTRAS DE ÓRDENES RECHAZADAS (últimas 10)")
    print("="*80 + "\n")
    
    rejected = OrderAudit.objects.filter(accepted=False, timestamp__gte=since).order_by('-timestamp')[:10]
    for order in rejected:
        confidence = order.request_payload.get('confidence', 'N/A')
        signal_type = order.request_payload.get('signal_type', 'N/A')
        z_score = order.request_payload.get('z_score', 'N/A')
        
        print(f"  • {order.symbol:15s} | {order.action:4s} | "
              f"Conf: {confidence} | Tipo: {signal_type} | Z: {z_score}")

# Muestras de aceptadas
if total_accepted > 0:
    print("\n" + "="*80)
    print("✅ MUESTRAS DE ÓRDENES ACEPTADAS (últimas 10)")
    print("="*80 + "\n")
    
    accepted = OrderAudit.objects.filter(accepted=True, timestamp__gte=since).order_by('-timestamp')[:10]
    for order in accepted:
        confidence = order.request_payload.get('confidence', 'N/A')
        signal_type = order.request_payload.get('signal_type', 'N/A')
        z_score = order.request_payload.get('z_score', 'N/A')
        
        print(f"  • {order.symbol:15s} | {order.action:4s} | "
              f"Conf: {confidence} | Tipo: {signal_type} | Z: {z_score}")

print("\n" + "="*80)
print()

