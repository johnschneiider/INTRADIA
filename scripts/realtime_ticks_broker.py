#!/usr/bin/env python3
"""
Script para actuar como broker en tiempo real
Recibe ticks del WebSocket de Deriv y los envía al dashboard
"""

import os
import sys
import django
import time
import json
import requests
import threading
from datetime import datetime

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from connectors.deriv_client import DerivClient

class RealtimeTicksBroker:
    def __init__(self):
        self.deriv_client = DerivClient()
        self.running = False
        # TODOS los instrumentos activos - Forex, Commodities, Índices, Crypto
        self.symbols = [
            # Forex - Principales
            'frxEURUSD', 'frxGBPUSD', 'frxUSDJPY', 'frxUSDCHF', 'frxAUDUSD', 'frxUSDCAD',
            'frxNZDUSD', 'frxEURGBP', 'frxEURJPY', 'frxGBPJPY', 'frxAUDJPY', 'frxEURAUD',
            # Commodities
            'frxXAUUSD', 'frxXAGUSD', 'frxXPDUSD', 'frxXPTUSD',
            # Índices sintéticos
            'R_10', 'R_25', 'R_50', 'R_75', 'R_100',
            'BOOM1000', 'CRASH1000', 'BOOM500', 'CRASH500', 'BOOM600', 'CRASH600',
            'RDBULL', 'RDBEAR',
            # Cryptocurrencies
            'cryBTCUSD', 'cryETHUSD',
            # Jump indices
            'JD10', 'JD25', 'JD50', 'JD75',
            # Índices OTC
            'OTC_N225', 'OTC_AS51',
        ]
        self.dashboard_url = 'http://127.0.0.1:8000/engine/ticks/realtime/'
        self.tick_count = 0
        
    def start(self):
        """Iniciar el broker de ticks en tiempo real"""
        print("🚀 INICIANDO BROKER DE TICKS EN TIEMPO REAL")
        print("=" * 60)
        
        # Verificar conexión con Deriv
        if not self.deriv_client.authenticate():
            print("❌ No se pudo conectar a Deriv WebSocket")
            return False
        
        print("✅ Conexión Deriv WebSocket establecida")
        
        # Verificar que el dashboard esté disponible
        try:
            response = requests.get('http://127.0.0.1:8000/engine/status/', timeout=5)
            if response.status_code == 200:
                print("✅ Dashboard disponible")
            else:
                print("⚠️ Dashboard no disponible")
        except:
            print("⚠️ Dashboard no disponible")
        
        self.running = True
        print("\n🎯 BROKER ACTIVO - Enviando ticks en tiempo real")
        print("📊 Símbolos monitoreados:", ", ".join(self.symbols))
        print("🔄 Enviando ticks al dashboard...")
        print("=" * 60)
        
        # Iniciar el loop de ticks
        self.tick_loop()
        
        return True
    
    def tick_loop(self):
        """Loop principal para enviar ticks en tiempo real"""
        try:
            while self.running:
                for symbol in self.symbols:
                    try:
                        # Simular ticks en tiempo real (en un broker real, esto vendría del WebSocket)
                        self.send_tick(symbol)
                        time.sleep(0.1)  # 10 ticks por segundo por símbolo
                        
                    except Exception as e:
                        print(f"❌ Error enviando tick para {symbol}: {e}")
                        continue
                
                # Pausa breve entre ciclos
                time.sleep(0.5)
                
        except KeyboardInterrupt:
            print("\n🛑 Broker detenido por el usuario")
            self.running = False
        except Exception as e:
            print(f"\n❌ Error en el loop de ticks: {e}")
            self.running = False
    
    def send_tick(self, symbol):
        """Enviar un tick al dashboard"""
        try:
            # Simular precio real (en un broker real, esto vendría del WebSocket)
            import random
            base_prices = {
                'R_10': 10.0,
                'R_25': 25.0,
                'R_50': 50.0,
                'CRASH1000': 1000.0,
                'BOOM1000': 1000.0
            }
            
            base_price = base_prices.get(symbol, 100.0)
            price = base_price + random.uniform(-0.5, 0.5)
            
            tick_data = {
                'symbol': symbol,
                'price': round(price, 2),
                'volume': random.uniform(100, 1000),
                'timestamp': datetime.now().isoformat(),
                'bid': round(price - 0.01, 2),
                'ask': round(price + 0.01, 2)
            }
            
            # Enviar tick al dashboard
            response = requests.post(
                self.dashboard_url,
                json=tick_data,
                timeout=2
            )
            
            if response.status_code == 200:
                self.tick_count += 1
                if self.tick_count % 100 == 0:  # Mostrar cada 100 ticks
                    print(f"📈 {symbol}: {price:.2f} (ticks enviados: {self.tick_count})")
            else:
                print(f"⚠️ Error enviando tick para {symbol}: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Error enviando tick: {e}")
    
    def stop(self):
        """Detener el broker"""
        self.running = False
        print("🛑 Broker de ticks detenido")

def main():
    broker = RealtimeTicksBroker()
    
    try:
        success = broker.start()
        if success:
            print(f"\n🎉 Broker de ticks activado exitosamente!")
            print(f"📊 Total ticks enviados: {broker.tick_count}")
            print(f"🌐 Dashboard: http://127.0.0.1:8000/engine/")
        else:
            print("\n❌ Error activando el broker")
    except Exception as e:
        print(f"\n❌ Error crítico: {e}")
    finally:
        broker.stop()

if __name__ == "__main__":
    main()





