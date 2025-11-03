#!/usr/bin/env python3
"""
Script para suscribirse a múltiples símbolos de Deriv y detectar cuáles están activos
"""

import os
import sys
import django
import time
import json
import websocket
import threading
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from market.models import Tick
from django.utils import timezone


class MultiSymbolSubscriber:
    """Suscribirse a múltiples símbolos y detectar cuáles están activos"""
    
    def __init__(self, symbols):
        self.ws = None
        self.connected = False
        self.api_token = os.getenv('DERIV_API_TOKEN', 'rOB3RNqw1EevPzu')
        self.symbols = symbols
        self.active_symbols = set()
        self.tick_counts = {symbol: 0 for symbol in symbols}
        self.start_time = time.time()
        self.test_duration = 30  # Segundos de prueba
        self.ticks_received = {}
        
    def on_message(self, ws, message):
        data = json.loads(message)
        msg_type = data.get('msg_type', '')
        
        if msg_type == 'tick':
            tick_data = data.get('tick', {})
            if tick_data:
                symbol = tick_data.get('symbol', '')
                if symbol in self.symbols:
                    self.ticks_received[symbol] = self.ticks_received.get(symbol, 0) + 1
                    self.tick_counts[symbol] += 1
                    self.active_symbols.add(symbol)
                    
                    # Mostrar update cada 5 ticks
                    if self.ticks_received[symbol] % 5 == 0:
                        price = tick_data.get('quote', 0)
                        epoch = tick_data.get('epoch', int(time.time()))
                        timestamp = datetime.fromtimestamp(epoch).strftime('%H:%M:%S')
                        print(f"  ✅ {symbol:20s} @ {price:.4f} - {timestamp} ({self.tick_counts[symbol]} ticks)")
        
        elif msg_type == 'authorize':
            auth_data = data.get('authorize', {})
            if auth_data.get('error'):
                print(f"❌ Error de autenticación: {auth_data['error']}")
            else:
                print(f"✅ Autenticado como: {auth_data.get('email', 'Usuario')}")
    
    def on_error(self, ws, error):
        print(f"❌ WebSocket error: {error}")
        self.connected = False
    
    def on_close(self, ws, close_status_code, close_msg):
        print("❌ WebSocket cerrado")
        self.connected = False
    
    def on_open(self, ws):
        print("✅ WebSocket conectado")
        self.connected = True
        
        # Autenticar
        auth_msg = {"authorize": self.api_token}
        ws.send(json.dumps(auth_msg))
        time.sleep(1)
        
        print(f"\n📊 Suscribiéndose a {len(self.symbols)} símbolos...")
        # Suscribirse a todos los símbolos
        for symbol in self.symbols:
            subscribe_msg = {"ticks": symbol}
            ws.send(json.dumps(subscribe_msg))
            time.sleep(0.1)  # Pequeño delay entre suscripciones
        
        print("⏳ Escuchando ticks por 30 segundos...\n")
    
    def start(self):
        print("=" * 80)
        print("🔍 DETECTANDO SÍMBOLOS ACTIVOS EN DERIV")
        print("=" * 80)
        print(f"🔑 Token: {self.api_token[:15]}...")
        print(f"📊 Probando {len(self.symbols)} símbolos")
        print(f"⏱️  Duración: {self.test_duration} segundos")
        print("=" * 80)
        
        self.ws = websocket.WebSocketApp(
            "wss://ws.derivws.com/websockets/v3?app_id=1089",
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )
        
        # Ejecutar en hilo separado
        wst = threading.Thread(target=self.ws.run_forever)
        wst.daemon = True
        wst.start()
        
        # Esperar el tiempo de prueba
        time.sleep(self.test_duration)
        
        # Cerrar conexión
        if self.ws:
            self.ws.close()
        
        # Mostrar resultados
        self.print_results()
    
    def print_results(self):
        print("\n" + "=" * 80)
        print("📊 RESULTADOS DE LA PRUEBA")
        print("=" * 80)
        
        # Ordenar por número de ticks
        sorted_results = sorted(
            self.tick_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        print("\n✅ SÍMBOLOS ACTIVOS:")
        print("-" * 80)
        active_count = 0
        for symbol, count in sorted_results:
            if count > 0:
                print(f"  ✅ {symbol:20s} - {count:4d} ticks recibidos")
                active_count += 1
            else:
                print(f"  ❌ {symbol:20s} - Sin datos")
        
        print("\n" + "=" * 80)
        print(f"📈 RESUMEN:")
        print(f"   • Total probados: {len(self.symbols)}")
        print(f"   • Activos: {active_count}")
        print(f"   • Inactivos: {len(self.symbols) - active_count}")
        print("=" * 80)
        
        # Guardar resultados
        results = {
            'active_symbols': list(self.active_symbols),
            'tick_counts': self.tick_counts,
            'total_ticks': sum(self.tick_counts.values())
        }
        
        with open('active_symbols.json', 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n💾 Resultados guardados en: active_symbols.json")
        print("\n")


def main():
    # Lista de símbolos a probar - Forex, Commodities, Índices, etc.
    test_symbols = [
        # Forex (principales)
        'frxEURUSD', 'frxGBPUSD', 'frxUSDJPY', 'frxUSDCHF', 'frxAUDUSD', 'frxUSDCAD',
        'frxNZDUSD', 'frxEURGBP', 'frxEURJPY', 'frxGBPJPY', 'frxAUDJPY', 'frxEURAUD',
        
        # Commodities
        'frxXAUUSD', 'frxXAGUSD', 'frxXPDUSD', 'frxXPTUSD',
        
        # Índices sintéticos
        'R_10', 'R_25', 'R_50', 'R_75', 'R_100',
        'BOOM1000', 'CRASH1000', 'BOOM300', 'CRASH300',
        'BOOM500', 'CRASH500', 'BOOM600', 'CRASH600',
        
        # Indices bursátiles (OTC)
        'OTC_SPC', 'OTC_NDX', 'OTC_DJI', 'OTC_FTSE', 'OTC_GDAXI',
        'OTC_FCHI', 'OTC_HSI', 'OTC_N225', 'OTC_AS51',
        
        # Cryptocurrencies
        'cryBTCUSD', 'cryETHUSD',
        
        # Otros
        'JD10', 'JD25', 'JD50', 'JD75',
        'RDBULL', 'RDBEAR',
    ]
    
    subscriber = MultiSymbolSubscriber(test_symbols)
    subscriber.start()


if __name__ == "__main__":
    main()

