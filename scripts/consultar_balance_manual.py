"""
Script para hacer una solicitud MANUAL de balance a Deriv API
y ver exactamente qué devuelve
"""
import os
import sys
import django
import time
import json
import websocket
import threading

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from trading_bot.models import DerivAPIConfig

def consultar_balance_manual():
    print("=" * 80)
    print("CONSULTA MANUAL DE BALANCE A DERIV API".center(80))
    print("=" * 80)
    
    # 1. Obtener configuración
    print("\n1️⃣ OBTENIENDO CONFIGURACIÓN...")
    try:
        config = DerivAPIConfig.objects.filter(is_active=True).only('api_token', 'is_demo', 'app_id').first()
        if not config:
            print("❌ No hay configuración de API activa")
            return
        print(f"   ✅ Token: {config.api_token[:10]}...{config.api_token[-5:]}")
        print(f"   ✅ Tipo cuenta: {'DEMO' if config.is_demo else 'REAL'}")
        print(f"   ✅ App ID: {config.app_id}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return
    
    # 2. Crear WebSocket y autenticar
    print("\n2️⃣ CONECTANDO Y AUTENTICANDO...")
    
    ws_url = f"wss://ws.binaryws.com/websockets/v3?app_id={config.app_id}"
    response_data = {}
    response_event = threading.Event()
    
    def on_message(ws, message):
        data = json.loads(message)
        nonlocal response_data
        response_data = data
        response_event.set()
        
        msg_type = data.get('msg_type', '')
        if msg_type == 'authorize':
            print(f"\n   📥 RESPUESTA DE AUTHORIZE:")
            authorize_data = data.get('authorize', {})
            print(f"      LoginID: {authorize_data.get('loginid', 'unknown')}")
            print(f"      Is Virtual: {authorize_data.get('is_virtual', 'unknown')}")
            print(f"      Balance: ${authorize_data.get('balance', 0):.2f}")
            print(f"      Currency: {authorize_data.get('currency', 'unknown')}")
            
            account_list = authorize_data.get('account_list', [])
            print(f"\n      Account List ({len(account_list)} cuentas):")
            for i, account in enumerate(account_list):
                loginid = account.get('loginid', '')
                is_virtual = account.get('is_virtual', 1)
                account_type = 'DEMO' if (is_virtual == 1 or loginid.startswith('VRTC') or loginid.startswith('VRT')) else 'REAL'
                print(f"         {i+1}. {loginid} | Virtual: {is_virtual} | Tipo: {account_type}")
        
        elif msg_type == 'balance':
            print(f"\n   📥 RESPUESTA DE BALANCE:")
            balance_data = data.get('balance', {})
            print(f"      Balance: ${balance_data.get('balance', 0):.2f}")
            print(f"      Currency: {balance_data.get('currency', 'unknown')}")
            print(f"      LoginID: {balance_data.get('loginid', 'unknown')}")
            print(f"      Account Type: {balance_data.get('account_type', 'unknown')}")
            print(f"\n   📋 RESPUESTA COMPLETA:")
            print(json.dumps(data, indent=2))
            
        elif msg_type == 'error':
            print(f"\n   ❌ ERROR:")
            error_data = data.get('error', {})
            print(f"      Code: {error_data.get('code', 'unknown')}")
            print(f"      Message: {error_data.get('message', 'unknown')}")
            print(f"\n   📋 RESPUESTA COMPLETA:")
            print(json.dumps(data, indent=2))
    
    def on_error(ws, error):
        print(f"\n   ❌ ERROR DE WEBSOCKET: {error}")
    
    def on_close(ws, close_status_code, close_msg):
        print(f"\n   🔌 WEBSOCKET CERRADO")
    
    def on_open(ws):
        print(f"   ✅ WebSocket conectado")
        
        # Enviar authorize
        print(f"\n   📤 ENVIANDO AUTHORIZE...")
        auth_msg = {
            "authorize": config.api_token
        }
        print(f"      Mensaje: {json.dumps(auth_msg)}")
        ws.send(json.dumps(auth_msg))
        
        # Esperar respuesta de authorize
        if response_event.wait(timeout=10):
            authorize_data = response_data.get('authorize', {})
            if authorize_data:
                default_loginid = authorize_data.get('loginid', '')
                account_list = authorize_data.get('account_list', [])
                
                # Buscar cuenta REAL
                target_loginid = None
                for account in account_list:
                    loginid = account.get('loginid', '')
                    is_virtual = account.get('is_virtual', 1)
                    if not (loginid.startswith('VRTC') or loginid.startswith('VRT')) and is_virtual == 0:
                        target_loginid = loginid
                        break
                
                print(f"\n   🔍 Cuenta REAL encontrada: {target_loginid}")
                print(f"   🔍 Cuenta por defecto (authorize): {default_loginid}")
                
                if target_loginid and target_loginid != default_loginid:
                    # Intentar cambiar de cuenta
                    print(f"\n   📤 INTENTANDO CAMBIAR DE CUENTA...")
                    print(f"      Enviando: authorize = '{config.api_token}:{target_loginid}'")
                    
                    response_event.clear()
                    switch_msg = {
                        "authorize": f"{config.api_token}:{target_loginid}"
                    }
                    ws.send(json.dumps(switch_msg))
                    
                    if response_event.wait(timeout=10):
                        if response_data.get('error'):
                            error_info = response_data.get('error', {})
                            print(f"      ❌ ERROR al cambiar cuenta: {error_info.get('code')} - {error_info.get('message')}")
                            print(f"      ⚠️  Deriv NO acepta el formato 'token:loginid'")
                
                # Solicitar balance
                print(f"\n   📤 SOLICITANDO BALANCE...")
                response_event.clear()
                balance_msg = {
                    "balance": 1
                }
                print(f"      Mensaje: {json.dumps(balance_msg)}")
                ws.send(json.dumps(balance_msg))
                
                # Esperar respuesta de balance
                if response_event.wait(timeout=10):
                    balance_data = response_data.get('balance', {})
                    if balance_data:
                        print(f"\n   ✅ RESPUESTA DE BALANCE RECIBIDA")
                    else:
                        print(f"\n   ⚠️  No se recibió respuesta de balance")
                
                time.sleep(1)  # Esperar un poco más antes de cerrar
                print(f"\n   🔌 Cerrando conexión...")
                ws.close()
                time.sleep(1)
            else:
                print(f"\n   ❌ No se recibió respuesta de authorize")
        else:
            print(f"\n   ⏰ Timeout esperando respuesta de authorize")
    
    ws = websocket.WebSocketApp(
        ws_url,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open
    )
    
    print(f"   🔗 Conectando a: {ws_url}")
    
    # Ejecutar con timeout
    def run_with_timeout():
        ws_thread = threading.Thread(target=ws.run_forever)
        ws_thread.daemon = True
        ws_thread.start()
        ws_thread.join(timeout=30)  # Timeout de 30 segundos
        if ws_thread.is_alive():
            print("\n   ⏰ Timeout alcanzado, cerrando conexión...")
            ws.close()
    
    run_with_timeout()
    
    print("\n" + "=" * 80)
    print("CONSULTA COMPLETADA".center(80))
    print("=" * 80)

if __name__ == "__main__":
    consultar_balance_manual()

