"""
Auditoría paso a paso del balance que aparece en el dashboard.
Rastrea desde la plantilla hasta la fuente de datos.
"""

import os
import sys
import django
from pathlib import Path

# Configurar Django
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from connectors.deriv_client import DerivClient
from trading_bot.models import DerivAPIConfig
from engine.views import get_balance
from django.test import RequestFactory
from django.contrib.auth.models import AnonymousUser

User = get_user_model()

print("=" * 80)
print("AUDITORÍA DEL BALANCE - PASO A PASO")
print("=" * 80)

# PASO 1: Verificar configuración del usuario
print("\n[PASO 1] Verificando configuración del usuario...")
try:
    # Obtener el primer usuario (o el usuario actual si hay autenticación)
    users = User.objects.all()
    if users.exists():
        user = users.first()
        print(f"✓ Usuario encontrado: {user.username}")
        
        # Verificar configuración de Deriv
        try:
            config = DerivAPIConfig.objects.get(user=user)
            print(f"✓ Configuración Deriv encontrada:")
            print(f"  - Token: {config.api_token[:10]}... (longitud: {len(config.api_token)})")
            print(f"  - App ID: {config.app_id}")
            print(f"  - is_demo: {config.is_demo}")
            print(f"  - is_active: {config.is_active}")
        except DerivAPIConfig.DoesNotExist:
            print("✗ NO hay configuración Deriv para este usuario")
            config = None
    else:
        print("✗ No hay usuarios en la BD")
        user = None
        config = None
except Exception as e:
    print(f"✗ Error: {e}")
    user = None
    config = None

# PASO 2: Verificar DerivClient
print("\n[PASO 2] Verificando DerivClient...")
try:
    client = DerivClient()
    print(f"✓ DerivClient creado")
    print(f"  - Token usado: {client.api_token[:10]}... (longitud: {len(client.api_token)})")
    
    # Verificar de dónde viene el token
    env_token = os.getenv('DERIV_API_TOKEN')
    if env_token:
        print(f"  - Token desde ENV: {env_token[:10]}...")
    else:
        print(f"  - Token desde ENV: NO configurado (usando default)")
    
    if config and config.api_token:
        print(f"  - Token desde BD: {config.api_token[:10]}...")
        if client.api_token != config.api_token:
            print(f"  ⚠️  DISCREPANCIA: El token del client NO coincide con el de la BD")
        else:
            print(f"  ✓ Token coincide con BD")
    else:
        print(f"  ⚠️  No hay token en BD para comparar")
        
except Exception as e:
    print(f"✗ Error creando DerivClient: {e}")
    client = None

# PASO 3: Obtener balance directamente desde DerivClient
print("\n[PASO 3] Obteniendo balance desde DerivClient.get_balance()...")
if client:
    try:
        balance_info = client.get_balance()
        print(f"✓ Balance obtenido:")
        print(f"  - Tipo de respuesta: {type(balance_info)}")
        
        if isinstance(balance_info, dict):
            print(f"  - Balance: ${balance_info.get('balance', 'N/A')}")
            print(f"  - Currency: {balance_info.get('currency', 'N/A')}")
            print(f"  - Account Type: {balance_info.get('account_type', 'N/A')}")
            print(f"  - Login ID: {balance_info.get('loginid', 'N/A')}")
            print(f"  - Cached: {balance_info.get('cached', False)}")
            print(f"  - Source: {balance_info.get('source', 'N/A')}")
            
            # Verificar account_type
            account_type = balance_info.get('account_type', 'demo')
            if account_type == 'demo':
                print(f"  ⚠️  Account Type es 'demo'")
            elif account_type == 'real':
                print(f"  ✓ Account Type es 'real'")
            else:
                print(f"  ⚠️  Account Type desconocido: {account_type}")
                
            # Verificar loginid
            loginid = balance_info.get('loginid', '')
            if loginid:
                if loginid.startswith('VRTC') or loginid.startswith('VRT'):
                    print(f"  ⚠️  LoginID sugiere cuenta DEMO (VRTC/VRT*)")
                else:
                    print(f"  ✓ LoginID sugiere cuenta REAL")
        else:
            print(f"  ⚠️  Respuesta no es dict: {balance_info}")
            
    except Exception as e:
        print(f"✗ Error obteniendo balance: {e}")
        import traceback
        traceback.print_exc()

# PASO 4: Simular la vista get_balance
print("\n[PASO 4] Simulando engine.views.get_balance()...")
try:
    factory = RequestFactory()
    request = factory.get('/engine/balance/')
    if user:
        request.user = user
    else:
        request.user = AnonymousUser()
    
    response = get_balance(request)
    
    if hasattr(response, 'content'):
        import json
        data = json.loads(response.content.decode('utf-8'))
        print(f"✓ Respuesta de get_balance:")
        print(f"  - Success: {data.get('success', False)}")
        print(f"  - Balance: ${data.get('balance', 'N/A')}")
        print(f"  - Currency: {data.get('currency', 'N/A')}")
        print(f"  - Account Type: {data.get('account_type', 'N/A')}")
        print(f"  - Cached: {data.get('cached', False)}")
        print(f"  - Source: {data.get('source', 'N/A')}")
        
        # Verificar account_type
        account_type = data.get('account_type', 'demo')
        if account_type == 'demo':
            print(f"  ⚠️  Account Type es 'demo'")
        elif account_type == 'real':
            print(f"  ✓ Account Type es 'real'")
    else:
        print(f"  ⚠️  Respuesta no tiene content: {response}")
        
except Exception as e:
    print(f"✗ Error simulando get_balance: {e}")
    import traceback
    traceback.print_exc()

# PASO 5: Verificar caché
print("\n[PASO 5] Verificando caché de balance...")
if client:
    try:
        cache_value = client._balance_cache_value
        cache_time = client._balance_cache_time
        cache_ttl = client._balance_cache_ttl
        
        if cache_value:
            print(f"✓ Hay caché de balance:")
            print(f"  - Balance: ${cache_value.get('balance', 'N/A')}")
            print(f"  - Account Type: {cache_value.get('account_type', 'N/A')}")
            print(f"  - Cache Time: {cache_time}")
            print(f"  - Cache TTL: {cache_ttl}s")
            
            import time
            now = time.time()
            age = now - cache_time
            print(f"  - Cache Age: {age:.2f}s")
            
            if age > cache_ttl:
                print(f"  ⚠️  Cache EXPIRADO (age > TTL)")
            else:
                print(f"  ✓ Cache válido")
        else:
            print(f"  - No hay caché de balance")
            
    except Exception as e:
        print(f"✗ Error verificando caché: {e}")

# RESUMEN
print("\n" + "=" * 80)
print("RESUMEN Y DIAGNÓSTICO")
print("=" * 80)

if config:
    print(f"\n1. Configuración del usuario:")
    print(f"   - Token configurado: {'✓' if config.api_token else '✗'}")
    print(f"   - is_demo: {config.is_demo}")
    print(f"   - ¿Debe usar cuenta REAL? {'SÍ' if not config.is_demo else 'NO'}")
    
    if config.is_demo:
        print(f"   ⚠️  PROBLEMA: La configuración dice is_demo=True")
        print(f"      → Debes DESMARCAR '¿Usar cuenta demo?' en la configuración")
    else:
        print(f"   ✓ Configuración correcta para cuenta REAL")

print(f"\n2. DerivClient:")
if client:
    print(f"   - Token usado: {client.api_token[:10]}...")
    if config and client.api_token != config.api_token:
        print(f"   ⚠️  PROBLEMA: DerivClient NO está usando el token de la BD")
        print(f"      → DerivClient debe recibir el token desde DerivAPIConfig")
    else:
        if config:
            print(f"   ✓ Token coincide con configuración")
        else:
            print(f"   ⚠️  No hay configuración para comparar")

print(f"\n3. Balance obtenido:")
if client:
    try:
        balance_info = client.get_balance()
        if isinstance(balance_info, dict):
            account_type = balance_info.get('account_type', 'demo')
            print(f"   - Account Type: {account_type}")
            if account_type == 'demo':
                print(f"   ⚠️  PROBLEMA: El balance es de cuenta DEMO")
            elif account_type == 'real':
                print(f"   ✓ Balance es de cuenta REAL")
    except Exception as e:
        print(f"   ✗ Error: {e}")

print("\n" + "=" * 80)
print("RECOMENDACIONES")
print("=" * 80)
print("\n1. Modificar DerivClient.__init__() para recibir token y configuración")
print("2. Modificar engine.views.get_balance() para usar DerivAPIConfig del usuario")
print("3. Verificar que is_demo=False en DerivAPIConfig")
print("4. Limpiar caché después de cambiar configuración")

