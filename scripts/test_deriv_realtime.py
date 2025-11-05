#!/usr/bin/env python3
"""
Script para probar datos en tiempo real de Deriv y ver qué información está disponible
"""

import os
import sys
import django
import time
import json
import threading

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from connectors.deriv_client import DerivClient

def test_realtime_data():
    """Probar datos en tiempo real de Deriv"""
    
    client = DerivClient()
    print("🔑 Conectando a Deriv API...")
    
    if not client.authenticate():
        print("❌ No se pudo autenticar con Deriv")
        return
    
    print("✅ Autenticación exitosa")
    
    # Obtener balance
    balance_info = client.get_balance()
    print(f"💰 Balance: ${balance_info.get('balance', 'N/A')}")
    print(f"🏦 Cuenta: {balance_info.get('loginid', 'N/A')}")
    print(f"📊 Tipo: {balance_info.get('account_type', 'N/A')}")
    
    print("\n🔍 Probando diferentes enfoques para obtener datos...")
    print("=" * 60)
    
    # Probar diferentes timeframes con símbolos que sabemos que existen
    test_configs = [
        {'symbol': 'R_10', 'timeframe': '1m', 'count': 5},
        {'symbol': 'R_10', 'timeframe': '5m', 'count': 5},
        {'symbol': 'R_10', 'timeframe': '15m', 'count': 5},
        {'symbol': 'R_10', 'timeframe': '1h', 'count': 5},
        {'symbol': 'R_25', 'timeframe': '1m', 'count': 5},
        {'symbol': 'CRASH1000', 'timeframe': '1m', 'count': 5},
        {'symbol': 'BOOM1000', 'timeframe': '1m', 'count': 5},
    ]
    
    for config in test_configs:
        symbol = config['symbol']
        timeframe = config['timeframe']
        count = config['count']
        
        try:
            print(f"📊 Probando {symbol} {timeframe} (últimos {count})...", end=" ")
            
            candles = client.get_candles(symbol, timeframe, count)
            
            if candles and len(candles) > 0:
                print(f"✅ {len(candles)} velas")
                # Mostrar detalles de la primera vela
                first_candle = candles[0]
                print(f"   📈 Primera vela: O:{first_candle['open']:.5f} H:{first_candle['high']:.5f} L:{first_candle['low']:.5f} C:{first_candle['close']:.5f}")
            else:
                print("❌ Sin datos")
            
            time.sleep(2)  # Rate limiting
            
        except Exception as e:
            print(f"❌ Error: {str(e)[:50]}")
            time.sleep(1)
    
    print("\n" + "=" * 60)
    print("💡 ANÁLISIS:")
    print("=" * 60)
    print("Deriv parece tener limitaciones en datos históricos a través de la API WebSocket.")
    print("Esto es común en brokers de trading porque:")
    print("1. Los datos históricos pueden estar en sistemas separados")
    print("2. Pueden requerir endpoints diferentes")
    print("3. Pueden estar limitados por el tipo de cuenta")
    print("4. Los datos históricos pueden no estar disponibles para todos los símbolos")
    
    print("\n🔧 RECOMENDACIONES:")
    print("1. Usar datos en tiempo real para el trading en vivo")
    print("2. Para backtesting, usar fuentes de datos alternativas")
    print("3. Contactar soporte de Deriv para información específica")
    print("4. Considerar usar MT5/cTrader para datos históricos")
    
    return True

if __name__ == "__main__":
    test_realtime_data()












