#!/usr/bin/env python3
"""
Script para probar una entrada manual
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

from engine.services.rule_loop import process_symbol_rule_loop

print("=" * 60)
print("🧪 PROBANDO ENTRADA AUTOMÁTICA")
print("=" * 60)
print()

result = process_symbol_rule_loop('R_10')

print(f"Resultado: {result}")
print()

if result:
    status = result.get('status', 'unknown')
    print(f"Estado: {status}")
    
    if 'resp' in result:
        resp = result['resp']
        print(f"Respuesta completa: {resp}")
print("=" * 60)
