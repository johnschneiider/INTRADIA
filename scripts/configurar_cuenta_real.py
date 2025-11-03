"""
Configurar cuenta real directamente en la BD
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
print("CONFIGURAR CUENTA REAL")
print("=" * 80)

# Obtener usuario
users = User.objects.all()
if not users.exists():
    print("\n✗ No hay usuarios en la BD")
    sys.exit(1)

user = users.first()
print(f"\n✓ Usuario: {user.username}")

# Verificar configuración actual
config = DerivAPIConfig.objects.filter(user=user).first()

if config:
    print(f"\n✓ Configuración existente:")
    print(f"  - Token: {config.api_token}")
    print(f"  - is_demo: {config.is_demo}")
    print(f"  - is_active: {config.is_active}")
    
    if config.is_demo:
        print(f"\n⚠️  PROBLEMA: is_demo=True (debe ser False para cuenta real)")
        print(f"\n¿Actualizar a cuenta real? (S/n): ", end='')
        respuesta = input().strip().lower()
        
        if respuesta in ['', 's', 'si', 'y', 'yes']:
            config.is_demo = False
            config.save()
            print(f"✓ Configuración actualizada: is_demo=False")
        else:
            print(f"  No se actualizó")
    else:
        print(f"✓ Ya está configurado para cuenta real (is_demo=False)")
else:
    print(f"\n✗ No hay configuración")
    print(f"\nPara crear configuración de cuenta real:")
    print(f"1. Ve a: http://localhost:8000/trading/config/api/")
    print(f"2. Ingresa tu token REAL de Deriv")
    print(f"3. Desmarca '¿Usar cuenta demo?' (is_demo=False)")
    print(f"4. Guarda la configuración")
    print(f"\nO ingresa el token aquí para crearlo automáticamente:")
    print(f"Token: ", end='')
    token = input().strip()
    
    if token:
        try:
            config, created = DerivAPIConfig.objects.get_or_create(
                user=user,
                defaults={
                    'api_token': token,
                    'app_id': '1089',
                    'is_demo': False,
                    'is_active': True
                }
            )
            if created:
                print(f"✓ Configuración creada con cuenta REAL")
            else:
                config.api_token = token
                config.is_demo = False
                config.is_active = True
                config.save()
                print(f"✓ Configuración actualizada a cuenta REAL")
        except Exception as e:
            print(f"✗ Error: {e}")
            sys.exit(1)
    else:
        print(f"✗ No se ingresó token")
        sys.exit(1)

# Verificar configuración final
config = DerivAPIConfig.objects.filter(user=user).first()
if config and not config.is_demo:
    print(f"\n" + "=" * 80)
    print("PROBANDO CUENTA REAL")
    print("=" * 80)
    
    try:
        client = DerivClient(
            api_token=config.api_token,
            is_demo=False,
            app_id=config.app_id
        )
        print(f"\n✓ DerivClient creado con configuración REAL")
        print(f"  - Token usado: {client.api_token[:10]}...")
        print(f"  - is_demo: {client.is_demo}")
        
        print(f"\n📊 Obteniendo balance de cuenta REAL...")
        balance_info = client.get_balance()
        
        if isinstance(balance_info, dict):
            print(f"  ✓ Balance obtenido:")
            print(f"    - Balance: ${balance_info.get('balance', 0):.2f}")
            print(f"    - Currency: {balance_info.get('currency', 'N/A')}")
            print(f"    - Account Type: {balance_info.get('account_type', 'N/A')}")
            print(f"    - Login ID: {balance_info.get('loginid', 'N/A')}")
            
            account_type = balance_info.get('account_type', 'demo')
            loginid = balance_info.get('loginid', '')
            
            if account_type == 'real':
                print(f"\n  ✓✓✓ CUENTA REAL FUNCIONANDO CORRECTAMENTE ✓✓✓")
                print(f"    - El balance mostrado es de cuenta REAL")
                print(f"    - Login ID: {loginid}")
            elif account_type == 'demo':
                print(f"\n  ⚠️  PROBLEMA: Aún usando cuenta DEMO")
                print(f"    - Account Type: {account_type}")
                print(f"    - Login ID: {loginid}")
                print(f"\n  POSIBLES CAUSAS:")
                print(f"    1. El token es de cuenta demo (no real)")
                print(f"    2. La cuenta real está deshabilitada en Deriv")
                print(f"    3. El token no tiene permisos para cuenta real")
                print(f"\n  SOLUCION:")
                print(f"    1. Genera un token REAL en app.deriv.com")
                print(f"    2. Verifica que el token tenga permisos 'read' y 'trade'")
                print(f"    3. Verifica que la cuenta real esté habilitada en Deriv")
            else:
                print(f"\n  ⚠️  Account Type desconocido: {account_type}")
        else:
            print(f"  ⚠️  Respuesta inesperada: {type(balance_info)}")
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 80)
print("RESUMEN")
print("=" * 80)
print("\nLa configuración está lista para usar cuenta REAL")
print("El dashboard mostrará el balance de la cuenta real")

