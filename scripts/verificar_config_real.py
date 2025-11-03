"""
Verificar que la configuración de cuenta real esté correcta
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

User = get_user_model()

print("=" * 80)
print("VERIFICACION DE CONFIGURACION CUENTA REAL")
print("=" * 80)

# Obtener usuario
users = User.objects.all()
if not users.exists():
    print("\n✗ No hay usuarios en la BD")
    sys.exit(1)

user = users.first()
print(f"\n✓ Usuario: {user.username}")

# Verificar configuración actual
print("\n" + "=" * 80)
print("CONFIGURACION ACTUAL")
print("=" * 80)

try:
    config = DerivAPIConfig.objects.filter(user=user).first()
    if config:
        print(f"  ✓ Configuración encontrada:")
        print(f"    - Token: {config.api_token[:10]}... (longitud: {len(config.api_token)})")
        print(f"    - App ID: {config.app_id}")
        print(f"    - is_demo: {config.is_demo}")
        print(f"    - is_active: {config.is_active}")
        
        if config.is_demo:
            print(f"    ⚠️  PROBLEMA: is_demo=True (debe ser False para cuenta real)")
        else:
            print(f"    ✓ is_demo=False (correcto para cuenta real)")
    else:
        print(f"  ✗ NO hay configuración Deriv para este usuario")
        print(f"  → Debes crear configuración en: http://localhost:8000/trading/config/api/")
        sys.exit(1)
except Exception as e:
    print(f"  ✗ Error: {e}")
    sys.exit(1)

# Probar con la configuración actual
print("\n" + "=" * 80)
print("PROBANDO CON CONFIGURACION ACTUAL")
print("=" * 80)

try:
    client = DerivClient(
        api_token=config.api_token,
        is_demo=config.is_demo,
        app_id=config.app_id
    )
    print(f"  ✓ DerivClient creado con configuración")
    print(f"    - Token usado: {client.api_token[:10]}...")
    print(f"    - is_demo: {client.is_demo}")
    print(f"    - Target account: {'DEMO' if client.is_demo else 'REAL'}")
    
    # Obtener balance
    print(f"\n  📊 Obteniendo balance...")
    balance_info = client.get_balance()
    
    if isinstance(balance_info, dict):
        print(f"  ✓ Balance obtenido:")
        print(f"    - Balance: ${balance_info.get('balance', 0):.2f}")
        print(f"    - Currency: {balance_info.get('currency', 'N/A')}")
        print(f"    - Account Type: {balance_info.get('account_type', 'N/A')}")
        print(f"    - Login ID: {balance_info.get('loginid', 'N/A')}")
        print(f"    - Cached: {balance_info.get('cached', False)}")
        
        account_type = balance_info.get('account_type', 'demo')
        loginid = balance_info.get('loginid', '')
        
        # Verificar si es cuenta real
        if account_type == 'real':
            print(f"\n  ✓ CUENTA REAL ACTIVA")
            print(f"    - El balance mostrado es de cuenta REAL")
            print(f"    - Login ID: {loginid}")
        elif account_type == 'demo':
            print(f"\n  ⚠️  PROBLEMA: Aún usando cuenta DEMO")
            print(f"    - Account Type: {account_type}")
            print(f"    - Login ID: {loginid}")
            
            if loginid.startswith('VRTC') or loginid.startswith('VRT'):
                print(f"    - El loginid confirma que es cuenta DEMO (VRTC*)")
                print(f"\n  SOLUCION:")
                print(f"    1. Verifica que is_demo=False en la configuración")
                print(f"    2. Verifica que el token es de cuenta REAL (no demo)")
                print(f"    3. Verifica que la cuenta real esté habilitada en Deriv")
            else:
                print(f"    - El loginid sugiere cuenta real, pero account_type es demo")
                print(f"    - Puede ser que Deriv aún esté devolviendo cuenta demo")
        else:
            print(f"\n  ⚠️  Account Type desconocido: {account_type}")
    else:
        print(f"  ⚠️  Respuesta inesperada: {type(balance_info)}")
        
except Exception as e:
    print(f"  ✗ Error: {e}")
    import traceback
    traceback.print_exc()

# Si is_demo=True, corregirlo
if config and config.is_demo:
    print("\n" + "=" * 80)
    print("CORRIGIENDO CONFIGURACION (is_demo=False)")
    print("=" * 80)
    
    try:
        config.is_demo = False
        config.save()
        print(f"  ✓ Configuración actualizada: is_demo=False")
        
        # Probar de nuevo
        print(f"\n  📊 Probando de nuevo con is_demo=False...")
        client_fixed = DerivClient(
            api_token=config.api_token,
            is_demo=False,
            app_id=config.app_id
        )
        balance_info_fixed = client_fixed.get_balance()
        
        if isinstance(balance_info_fixed, dict):
            account_type_fixed = balance_info_fixed.get('account_type', 'demo')
            loginid_fixed = balance_info_fixed.get('loginid', '')
            
            print(f"  ✓ Balance obtenido:")
            print(f"    - Balance: ${balance_info_fixed.get('balance', 0):.2f}")
            print(f"    - Account Type: {account_type_fixed}")
            print(f"    - Login ID: {loginid_fixed}")
            
            if account_type_fixed == 'real':
                print(f"\n  ✓ CUENTA REAL FUNCIONANDO")
            elif account_type_fixed == 'demo':
                print(f"\n  ⚠️  Aún usando cuenta DEMO")
                print(f"    - Verifica que el token sea de cuenta REAL")
                print(f"    - Verifica que la cuenta real esté habilitada en Deriv")
    except Exception as e:
        print(f"  ✗ Error corrigiendo: {e}")

print("\n" + "=" * 80)
print("RESUMEN")
print("=" * 80)
print("\nPara usar cuenta real:")
print("1. Ve a: http://localhost:8000/trading/config/api/")
print("2. Verifica que 'is_demo' esté DESMARCADO (False)")
print("3. Verifica que el token sea de cuenta REAL (generado en app.deriv.com)")
print("4. El sistema automáticamente seleccionará la cuenta real")

