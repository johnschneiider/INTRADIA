#!/usr/bin/env python3
"""
Script para guardar ticks en tiempo real de Deriv en la base de datos
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

# Obtener directorio raíz del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from market.models import Tick
from django.utils import timezone

class RealtimeTickSaver:
    def __init__(self):
        self.ws = None
        self.connected = False
        self.api_token = os.getenv('DERIV_API_TOKEN', 'rOB3RNqw1EevPzu')
        self.tick_count = 0
        
    def on_message(self, ws, message):
        data = json.loads(message)
        msg_type = data.get('msg_type', '')
        
        if msg_type == 'tick':
            tick_data = data.get('tick', {})
            if tick_data:
                self.save_tick(tick_data)
                
    def save_tick(self, tick_data):
        try:
            symbol = tick_data.get('symbol', '')
            price = tick_data.get('quote', 0)
            epoch = tick_data.get('epoch', int(time.time()))
            
            if not symbol or price == 0:
                return
            
            # Convertir timestamp
            timestamp = timezone.make_aware(datetime.fromtimestamp(epoch))
            
            # Guardar en base de datos
            tick, created = Tick.objects.get_or_create(
                symbol=symbol,
                timestamp=timestamp,
                defaults={
                    'price': price,
                    'volume': tick_data.get('volume', 0)
                }
            )
            
            if created:
                self.tick_count += 1
                if self.tick_count % 10 == 0:
                    print(f"✅ Guardados {self.tick_count} ticks nuevos")
                print(f"  {symbol} @ {price:.4f} - {timestamp.strftime('%H:%M:%S')}")
            
        except Exception as e:
            print(f"Error guardando tick: {e}")
    
    def on_error(self, ws, error):
        print(f"❌ WebSocket error: {error}")
        self.connected = False
    
    def on_close(self, ws, close_status_code, close_msg):
        print("❌ WebSocket desconectado")
        self.connected = False
    
    def on_open(self, ws):
        print("✅ WebSocket conectado a Deriv")
        self.connected = True
        
        # Autenticar
        auth_msg = {"authorize": self.api_token}
        ws.send(json.dumps(auth_msg))
        
        # Suscribirse a símbolos
        symbols = ['R_10', 'R_25', 'R_50', 'CRASH1000', 'BOOM1000']
        for symbol in symbols:
            subscribe_msg = {"ticks": symbol}
            ws.send(json.dumps(subscribe_msg))
            print(f"📊 Suscrito a {symbol}")
    
    def start(self):
        print("🚀 Iniciando guardado de ticks en tiempo real...")
        print(f"🔑 Token: {self.api_token[:10]}...")
        print("📊 Suscribiéndose a R_10, R_25, R_50, CRASH1000, BOOM1000...")
        print("💾 Guardando ticks en base de datos...")
        print("=" * 60)
        
        self.ws = websocket.WebSocketApp(
            "wss://ws.derivws.com/websockets/v3?app_id=1089",
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )
        
        # Mantener conexión
        self.ws.run_forever()

if __name__ == "__main__":
    saver = RealtimeTickSaver()
    try:
        saver.start()
    except KeyboardInterrupt:
        print("\n🛑 Deteniendo...")
        sys.exit(0)

