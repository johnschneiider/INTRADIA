#!/usr/bin/env python3
"""
Script para probar WebSocket de Deriv en tiempo real y verificar ticks
"""

import os
import sys
import django
import time
import json
import threading
import websocket
from datetime import datetime

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

class DerivRealtimeTester:
    def __init__(self):
        self.api_token = 'rOB3RNqw1EevPzu'
        self.ws = None
        self.connected = False
        self.ticks_received = []
        self.response_data = {}
        self.response_event = threading.Event()
        
    def connect_websocket(self):
        """Conectar a WebSocket de Deriv"""
        try:
            def on_message(ws, message):
                data = json.loads(message)
                self.response_data = data
                
                # Procesar diferentes tipos de mensajes
                msg_type = data.get('msg_type', '')
                
                if msg_type == 'authorize':
                    print(f"✅ Autenticación exitosa")
                    self.connected = True
                    
                elif msg_type == 'tick':
                    # Procesar tick en tiempo real
                    tick_data = data.get('tick', {})
                    if tick_data:
                        symbol = tick_data.get('symbol', 'Unknown')
                        price = tick_data.get('quote', 0)
                        epoch = tick_data.get('epoch', 0)
                        
                        tick_info = {
                            'symbol': symbol,
                            'price': price,
                            'timestamp': epoch,
                            'datetime': datetime.fromtimestamp(epoch).strftime('%H:%M:%S')
                        }
                        
                        self.ticks_received.append(tick_info)
                        print(f"📊 TICK {symbol}: {price} @ {tick_info['datetime']}")
                        
                elif msg_type == 'history':
                    # Datos históricos
                    history = data.get('history', {})
                    print(f"📈 Histórico recibido: {len(history.get('prices', []))} puntos")
                    
                elif msg_type == 'error':
                    error = data.get('error', {})
                    print(f"❌ Error: {error.get('message', 'Unknown error')}")
                    
                else:
                    print(f"📨 Mensaje: {msg_type} - {data}")
                
                self.response_event.set()
            
            def on_error(ws, error):
                print(f"❌ WebSocket error: {error}")
                self.connected = False
            
            def on_close(ws, close_status_code, close_msg):
                print(f"🔌 WebSocket cerrado: {close_status_code} - {close_msg}")
                self.connected = False
            
            def on_open(ws):
                print(f"🔌 WebSocket conectado")
                # Autenticar
                auth_msg = {"authorize": self.api_token}
                ws.send(json.dumps(auth_msg))
            
            self.ws = websocket.WebSocketApp(
                "wss://ws.derivws.com/websockets/v3?app_id=1089",
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open
            )
            
            # Ejecutar en hilo separado
            wst = threading.Thread(target=self.ws.run_forever)
            wst.daemon = True
            wst.start()
            
            # Esperar conexión
            time.sleep(3)
            return self.connected
            
        except Exception as e:
            print(f"❌ Error conectando WebSocket: {e}")
            return False
    
    def test_realtime_ticks(self, symbol='R_10'):
        """Probar ticks en tiempo real"""
        if not self.connected:
            print("❌ WebSocket no conectado")
            return
        
        print(f"\n🎯 Suscribiéndose a ticks en tiempo real para {symbol}...")
        
        # Suscribirse a ticks
        tick_subscription = {
            "ticks": symbol
        }
        
        self.ws.send(json.dumps(tick_subscription))
        print(f"✅ Suscripción enviada para {symbol}")
        
        # Escuchar ticks por 30 segundos
        print("⏰ Escuchando ticks por 30 segundos...")
        start_time = time.time()
        
        while time.time() - start_time < 30:
            time.sleep(1)
            if len(self.ticks_received) > 0:
                latest_tick = self.ticks_received[-1]
                print(f"📊 Último tick: {latest_tick['price']} @ {latest_tick['datetime']}")
        
        # Cancelar suscripción
        cancel_subscription = {
            "forget": symbol
        }
        self.ws.send(json.dumps(cancel_subscription))
        
        print(f"\n📊 RESUMEN DE TICKS RECIBIDOS:")
        print(f"Total ticks: {len(self.ticks_received)}")
        
        if self.ticks_received:
            print("Últimos 5 ticks:")
            for tick in self.ticks_received[-5:]:
                print(f"  • {tick['datetime']}: {tick['price']}")
        
        return len(self.ticks_received)
    
    def test_multiple_symbols(self):
        """Probar múltiples símbolos"""
        symbols_to_test = ['R_10', 'R_25', 'R_50', 'CRASH1000', 'BOOM1000']
        
        print("\n🔍 PROBANDO MÚLTIPLES SÍMBOLOS:")
        print("=" * 50)
        
        results = {}
        
        for symbol in symbols_to_test:
            print(f"\n📊 Probando {symbol}...")
            ticks_count = self.test_realtime_ticks(symbol)
            results[symbol] = ticks_count
            
            if ticks_count > 0:
                print(f"✅ {symbol}: {ticks_count} ticks recibidos")
            else:
                print(f"❌ {symbol}: Sin ticks")
            
            time.sleep(2)  # Pausa entre símbolos
        
        print(f"\n📈 RESUMEN FINAL:")
        print("=" * 50)
        for symbol, count in results.items():
            status = "✅" if count > 0 else "❌"
            print(f"{status} {symbol}: {count} ticks")
        
        return results
    
    def test_historical_data(self, symbol='R_10'):
        """Probar datos históricos"""
        if not self.connected:
            print("❌ WebSocket no conectado")
            return
        
        print(f"\n📈 Probando datos históricos para {symbol}...")
        
        # Solicitar datos históricos
        history_request = {
            "ticks_history": symbol,
            "granularity": 60,  # 1 minuto
            "count": 10,
            "end": int(time.time())
        }
        
        self.response_event.clear()
        self.ws.send(json.dumps(history_request))
        
        # Esperar respuesta
        if self.response_event.wait(timeout=10):
            history_data = self.response_data.get('history', {})
            prices = history_data.get('prices', [])
            
            if prices:
                print(f"✅ Datos históricos recibidos: {len(prices)} puntos")
                print("Últimos 3 precios:")
                for price in prices[-3:]:
                    print(f"  • {price}")
                return True
            else:
                print("❌ Sin datos históricos")
                return False
        else:
            print("❌ Timeout esperando datos históricos")
            return False

def main():
    print("🚀 INICIANDO PRUEBA DE WEBSOCKET DERIV EN TIEMPO REAL")
    print("=" * 60)
    
    tester = DerivRealtimeTester()
    
    # Conectar WebSocket
    if not tester.connect_websocket():
        print("❌ No se pudo conectar al WebSocket")
        return
    
    # Probar datos históricos primero
    print("\n1️⃣ PROBANDO DATOS HISTÓRICOS:")
    historical_success = tester.test_historical_data('R_10')
    
    # Probar ticks en tiempo real
    print("\n2️⃣ PROBANDO TICKS EN TIEMPO REAL:")
    realtime_results = tester.test_multiple_symbols()
    
    # Resumen final
    print(f"\n🎯 CONCLUSIÓN:")
    print("=" * 60)
    
    if historical_success:
        print("✅ Datos históricos: FUNCIONANDO")
    else:
        print("❌ Datos históricos: NO DISPONIBLE")
    
    working_symbols = [s for s, c in realtime_results.items() if c > 0]
    if working_symbols:
        print(f"✅ Ticks en tiempo real: FUNCIONANDO para {working_symbols}")
    else:
        print("❌ Ticks en tiempo real: NO DISPONIBLE")
    
    if working_symbols:
        print(f"\n💡 RECOMENDACIÓN: Usar {working_symbols[0]} para trading en tiempo real")
        print("📊 El sistema puede funcionar con datos en tiempo real de Deriv")
    else:
        print("\n⚠️ RECOMENDACIÓN: Deriv no proporciona datos en tiempo real suficientes")
        print("📊 Necesario implementar fuente de datos alternativa")

if __name__ == "__main__":
    main()










