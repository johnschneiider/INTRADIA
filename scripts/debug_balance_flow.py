"""
Script para depurar el flujo de obtención de balance
"""
import os
import sys
import django
import time
import json

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from connectors.deriv_client import DerivClient
from trading_bot.models import DerivAPIConfig

def debug_balance_flow():
    print("=" * 80)
    print("DEBUG DEL FLUJO DE BALANCE".center(80))
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
    
    # 2. Crear cliente
    print("\n2️⃣ CREANDO DERIVCLIENT...")
    client = DerivClient(
        api_token=config.api_token,
        is_demo=config.is_demo,
        app_id=config.app_id
    )
    print(f"   ✅ DerivClient creado")
    print(f"   ✅ is_demo: {client.is_demo}")
    print(f"   ✅ current_loginid: {client.current_loginid}")
    print(f"   ✅ _balance_cache_value: {client._balance_cache_value}")
    
    # 3. Autenticar
    print("\n3️⃣ AUTENTICANDO...")
    if not client.authenticate():
        print("   ❌ Error en autenticación")
        return
    
    print(f"   ✅ Autenticación exitosa")
    print(f"   ✅ current_loginid después de authenticate: {client.current_loginid}")
    print(f"   ✅ _balance_cache_value después de authenticate: {client._balance_cache_value}")
    print(f"   ✅ account_list tiene {len(client.account_list)} cuentas")
    
    # Mostrar account_list
    print("\n   📋 Account List:")
    for i, account in enumerate(client.account_list):
        loginid = account.get('loginid', '')
        is_virtual = account.get('is_virtual', 1)
        is_real = not (loginid.startswith('VRTC') or loginid.startswith('VRT')) and is_virtual == 0
        print(f"      {i+1}. LoginID: {loginid} | Virtual: {is_virtual} | Real: {is_real}")
    
    # 4. Obtener balance
    print("\n4️⃣ OBTENIENDO BALANCE (get_balance)...")
    print("   📤 Enviando mensaje: {'balance': 1}")
    
    balance_info = client.get_balance()
    
    print(f"\n   📥 Respuesta de get_balance():")
    print(f"      Balance: ${balance_info.get('balance', 0):.2f}")
    print(f"      Currency: {balance_info.get('currency', 'USD')}")
    print(f"      Account Type: {balance_info.get('account_type', 'unknown').upper()}")
    print(f"      LoginID: {balance_info.get('loginid', 'unknown')}")
    print(f"      Source: {balance_info.get('source', 'unknown')}")
    print(f"      Warning: {balance_info.get('warning', 'none')}")
    
    # 5. Verificar estado final
    print("\n5️⃣ ESTADO FINAL...")
    print(f"   ✅ current_loginid: {client.current_loginid}")
    print(f"   ✅ _balance_cache_value: {client._balance_cache_value}")
    print(f"   ✅ account_type del resultado: {balance_info.get('account_type', 'unknown')}")
    
    # 6. Verificación
    print("\n6️⃣ VERIFICACIÓN...")
    is_real = balance_info.get('account_type') == 'real'
    loginid = balance_info.get('loginid', '')
    is_real_loginid = loginid and not (loginid.startswith('VRTC') or loginid.startswith('VRT'))
    matches_current = loginid == client.current_loginid
    
    if is_real and is_real_loginid and matches_current:
        print("   ✅ Balance REAL confirmado")
        print(f"   ✅ LoginID coincide con current_loginid ({client.current_loginid})")
        print(f"   ✅ Account type es 'real'")
        if balance_info.get('balance', 0) > 0:
            print(f"   ✅ Balance mayor a $0.00: ${balance_info.get('balance', 0):.2f}")
    else:
        print("   ❌ Balance NO REAL confirmado")
        if not is_real:
            print(f"   ❌ Account type no es 'real' (es: {balance_info.get('account_type', 'unknown')})")
        if not is_real_loginid:
            print(f"   ❌ LoginID es DEMO ({loginid})")
        if not matches_current:
            print(f"   ❌ LoginID no coincide con current_loginid (balance: {loginid}, current: {client.current_loginid})")
    
    print("\n" + "=" * 80)
    print("RESUMEN DEL PROBLEMA".center(80))
    print("=" * 80)
    print("\n📌 PUNTOS CRÍTICOS:")
    print("   1. Cuando Deriv rechaza 'token:loginid', NO se guarda balance en caché")
    print("   2. Cuando se solicita balance con {'balance': 1}, Deriv devuelve balance de DEMO")
    print("   3. El balance de authorize inicial siempre es de DEMO")
    print("   4. No hay forma de obtener balance REAL sin cambiar de cuenta")
    print("   5. Deriv NO acepta el formato 'token:loginid' para cambiar de cuenta")
    print("\n💡 SOLUCIÓN PROPUESTA:")
    print("   - Cuando Deriv rechaza 'token:loginid', NO guardar balance de DEMO en caché")
    print("   - Cuando get_balance() detecta que balance viene de DEMO pero current_loginid es REAL,")
    print("     usar balance de authorize inicial si está disponible, o usar $0.00 si no hay balance REAL")
    print("   - O usar el balance de los trades anteriores si están en cuenta REAL")
    
    return balance_info

if __name__ == "__main__":
    debug_balance_flow()

