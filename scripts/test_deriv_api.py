#!/usr/bin/env python3
"""
Script de prueba para verificar que la API de Deriv funciona
con operaciones CALL y PUT
"""

import os
import sys
import django
import json
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from connectors.deriv_client import DerivClient
import websocket


def test_deriv_connection():
    """Probar conexión con Deriv"""
    print("=" * 60)
    print("🔍 PROBANDO CONEXIÓN CON DERIV")
    print("=" * 60)
    print()
    
    client = DerivClient()
    
    print(f"🔑 Token: {client.api_token[:10]}...")
    print(f"📍 URL: wss://ws.derivws.com/websockets/v3?app_id=1089")
    print()
    
    # Probar autenticación
    print("1️⃣ Intentando autenticar...")
    auth_success = client.authenticate()
    
    if auth_success:
        print("   ✅ Autenticación exitosa")
    else:
        print("   ❌ Fallo en autenticación")
        return False
    
    print()
    print("2️⃣ Verificando conexión WebSocket...")
    if client.connected and client.ws:
        print("   ✅ WebSocket conectado")
    else:
        print("   ❌ WebSocket no conectado")
        return False
    
    print()
    return True


def test_get_balance():
    """Probar obtención de balance"""
    print("3️⃣ Obteniendo balance...")
    client = DerivClient()
    
    if not client.connected:
        if not client.authenticate():
            print("   ❌ No se pudo autenticar")
            return
    
    balance = client.get_balance()
    print(f"   💰 Balance: {balance}")
    print()


def test_place_simple_order():
    """Probar colocar orden simple usando WebSocket directamente"""
    print("=" * 60)
    print("🧪 PROBANDO ORDEN SIMPLE")
    print("=" * 60)
    print()
    
    token = "G7Eq2rRQnE81Vot"
    symbol = "R_10"
    
    print(f"Símbolo: {symbol}")
    print(f"Token: {token[:10]}...")
    print()
    
    # Crear conexión WebSocket directa
    print("1️⃣ Conectando a WebSocket...")
    
    ws = None
    response_received = False
    response_data = {}
    
    def on_message(ws, message):
        nonlocal response_received, response_data
        try:
            data = json.loads(message)
            print(f"📨 Mensaje recibido: {json.dumps(data, indent=2)}")
            response_data = data
            response_received = True
            
            # Verificar si hay error
            if data.get('error'):
                print(f"❌ Error recibido: {data['error']}")
            elif data.get('buy'):
                print(f"✅ Orden aceptada: {data['buy']}")
        except Exception as e:
            print(f"❌ Error parseando mensaje: {e}")
    
    def on_error(ws, error):
        print(f"❌ Error WebSocket: {error}")
    
    def on_close(ws, close_status_code, close_msg):
        print(f"❌ WebSocket cerrado: {close_status_code} - {close_msg}")
    
    def on_open(ws):
        print("✅ WebSocket conectado")
        
        # Autenticar
        print("2️⃣ Enviando autenticación...")
        auth_msg = {"authorize": token}
        ws.send(json.dumps(auth_msg))
        time.sleep(2)
        
        # Intentar comprar opción binaria - CORREGIDO con campos requeridos
        print("3️⃣ Enviando orden BUY (CALL)...")
        buy_msg = {
            "buy": 1,
            "price": 10,
            "parameters": {
                "contract_type": "CALL",
                "symbol": symbol,
                "amount": 1,
                "duration": 60,
                "duration_unit": "s",
                "basis": "stake",
                "currency": "USD"
            }
        }
        print(f"📤 Mensaje: {json.dumps(buy_msg, indent=2)}")
        ws.send(json.dumps(buy_msg))
    
    try:
        ws = websocket.WebSocketApp(
            "wss://ws.derivws.com/websockets/v3?app_id=1089",
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open
        )
        
        # Ejecutar en hilo separado
        import threading
        wst = threading.Thread(target=ws.run_forever)
        wst.daemon = True
        wst.start()
        
        # Esperar respuesta
        print("⏳ Esperando respuesta (timeout: 15 segundos)...")
        timeout = 15
        start_time = time.time()
        
        while not response_received and (time.time() - start_time) < timeout:
            time.sleep(0.5)
        
        if response_received:
            print()
            print("✅ Respuesta recibida")
        else:
            print()
            print("⏰ Timeout - No se recibió respuesta")
        
        time.sleep(1)
        ws.close()
        
    except Exception as e:
        print(f"❌ Error en WebSocket: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Función principal"""
    print()
    
    # Test 1: Conexión básica
    if not test_deriv_connection():
        print("❌ No se pudo conectar")
        return
    
    print()
    test_get_balance()
    
    print()
    test_place_simple_order()
    
    print()
    print("=" * 60)
    print("📊 RESUMEN DE PRUEBAS")
    print("=" * 60)
    print()
    print("✅ Conexión: OK")
    print("✅ Autenticación: OK")
    print("⏳ Orden: Pendiente de respuesta")
    print()
    print("💡 Si ves 'buy' en la respuesta, la API está funcionando")
    print("=" * 60)


if __name__ == "__main__":
    main()
