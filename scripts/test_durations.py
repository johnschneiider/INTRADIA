#!/usr/bin/env python3
"""
Script para probar qué duraciones funcionan para cada tipo de instrumento en Deriv
"""

import os
import sys
import django
import time
import json
import websocket
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from connectors.deriv_client import DerivClient


class DurationTester:
    def __init__(self):
        self.ws = None
        self.connected = False
        self.response_data = {}
        self.response_event = threading.Event()
        self.api_token = os.getenv('DERIV_API_TOKEN', 'G7Eq2rRQnE81Vot')
    
    def _connect(self):
        """Conectar al WebSocket de Deriv"""
        if self.connected and self.ws:
            return True
        
        try:
            def on_message(ws, message):
                data = json.loads(message)
                self.response_data = data
                self.response_event.set()
            
            def on_error(ws, error):
                print(f"❌ Error: {error}")
                self.connected = False
            
            def on_close(ws, close_status_code, close_msg):
                print("❌ Conexión cerrada")
                self.connected = False
            
            def on_open(ws):
                print("✅ WebSocket conectado")
                self.connected = True
                auth_msg = {"authorize": self.api_token}
                ws.send(json.dumps(auth_msg))
            
            self.ws = websocket.WebSocketApp(
                "wss://ws.derivws.com/websockets/v3?app_id=1089",
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open
            )
            
            wst = threading.Thread(target=self.ws.run_forever)
            wst.daemon = True
            wst.start()
            
            time.sleep(3)
            return self.connected
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def test_duration(self, symbol, duration):
        """Probar si una duración funciona para un símbolo"""
        if not self._connect():
            return {'valid': False, 'error': 'connection_failed'}
        
        try:
            self.response_event.clear()
            
            # Intentar comprar (solo para probar la duración, no ejecutar)
            request = {
                "proposal": 1,
                "amount": 1.0,
                "basis": "stake",
                "contract_type": "CALL",
                "currency": "USD",
                "duration": duration,
                "duration_unit": "s",
                "symbol": symbol
            }
            
            self.ws.send(json.dumps(request))
            
            if self.response_event.wait(timeout=10):
                data = self.response_data
                
                if data.get('error'):
                    error_code = data['error'].get('code', '')
                    error_msg = data['error'].get('message', '')
                    
                    if 'duration' in error_msg.lower() or 'InvalidOfferings' in error_code:
                        return {'valid': False, 'error': error_msg}
                elif data.get('proposal'):
                    # La propuesta funcionó, la duración es válida
                    return {'valid': True, 'quote': data['proposal'].get('quote', 0)}
                
            return {'valid': False, 'error': 'timeout'}
            
        except Exception as e:
            return {'valid': False, 'error': str(e)}
    
    def close(self):
        if self.ws:
            self.ws.close()


def test_all_durations():
    """Probar diferentes duraciones para cada tipo de instrumento"""
    
    print("\n" + "="*80)
    print("🧪 PROBANDO DURACIONES PARA DIFERENTES TIPOS DE INSTRUMENTOS")
    print("="*80 + "\n")
    
    tester = DurationTester()
    
    # Símbolos de prueba representativos
    test_symbols = {
        'Forex': 'frxEURUSD',
        'Commodities': 'frxXAUUSD',
        'Crypto': 'cryBTCUSD',
        'Índice sintético': 'R_10',
        'Índice OTC': 'OTC_N225',
    }
    
    # Duraciones a probar
    durations = [30, 60, 120, 180, 300, 600, 900]  # 30s, 1min, 2min, 3min, 5min, 10min, 15min
    
    results = {}
    
    for category, symbol in test_symbols.items():
        print(f"\n{'='*80}")
        print(f"📊 {category}: {symbol}")
        print('='*80)
        
        valid_durations = []
        
        for duration in durations:
            print(f"  Probando {duration}s...", end=" ")
            
            result = tester.test_duration(symbol, duration)
            
            if result['valid']:
                print(f"✅ VÁLIDO (Quote: ${result.get('quote', 0)})")
                valid_durations.append(duration)
            else:
                error = result.get('error', 'unknown')
                print(f"❌ {error[:50]}")
            
            time.sleep(0.5)  # Rate limiting
        
        results[category] = {
            'symbol': symbol,
            'valid_durations': valid_durations,
            'min_valid': min(valid_durations) if valid_durations else None
        }
        
        print(f"\n  💡 Duraciones válidas para {symbol}: {valid_durations}")
        if valid_durations:
            print(f"  ⭐ Mínima: {min(valid_durations)}s")
    
    tester.close()
    
    # Resumen
    print("\n" + "="*80)
    print("📊 RESUMEN DE DURACIONES VÁLIDAS")
    print("="*80 + "\n")
    
    for category, data in results.items():
        symbol = data['symbol']
        valid = data['valid_durations']
        min_duration = data['min_valid']
        
        print(f"  {category:20s} ({symbol:15s})")
        if valid:
            print(f"    ✅ Válidas: {valid}")
            print(f"    ⭐ Mínima recomendada: {min_duration}s")
        else:
            print(f"    ❌ Ninguna duración funcionó")
        print()
    
    return results


if __name__ == "__main__":
    results = test_all_durations()
    
    # Guardar resultados
    with open('valid_durations.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print("💾 Resultados guardados en: valid_durations.json")
    print("="*80 + "\n")

