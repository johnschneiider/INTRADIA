#!/usr/bin/env python3
"""
Script para probar el endpoint de velas
"""

import os
import sys
import django

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client
import json

def test_candles_endpoint():
    client = Client()
    
    # Probar diferentes combinaciones
    test_cases = [
        {'symbol': 'EURUSD', 'timeframe': '1h', 'limit': 3},
        {'symbol': 'GBPUSD', 'timeframe': '1h', 'limit': 3},
        {'symbol': 'EURUSD', 'timeframe': '5m', 'limit': 5},
    ]
    
    for test_case in test_cases:
        print(f"\n🧪 Probando: {test_case}")
        
        url = f"/engine/candles/?symbol={test_case['symbol']}&timeframe={test_case['timeframe']}&limit={test_case['limit']}"
        response = client.get(url)
        
        if response.status_code == 200:
            data = response.json()
            candles = data.get('candles', [])
            print(f"✅ Status: {response.status_code}")
            print(f"📊 Velas obtenidas: {len(candles)}")
            print(f"🎯 Símbolo: {data.get('symbol')}")
            print(f"⏰ Timeframe: {data.get('timeframe')}")
            
            if candles:
                first_candle = candles[0]
                print(f"📈 Primera vela:")
                print(f"   Timestamp: {first_candle['timestamp']}")
                print(f"   OHLC: {first_candle['open']:.5f} | {first_candle['high']:.5f} | {first_candle['low']:.5f} | {first_candle['close']:.5f}")
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"Content: {response.content.decode()[:200]}")

if __name__ == "__main__":
    test_candles_endpoint()














