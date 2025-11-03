"""Limpiar cache y verificar balance real"""
import os, sys, django
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from connectors.deriv_client import DerivClient

print("=" * 60)
print("LIMPIANDO CACHE Y VERIFICANDO BALANCE")
print("=" * 60)
print()

# Crear nuevo cliente (sin cache)
client = DerivClient()
print("Token:", client.api_token[:15])

# Limpiar cache anterior
client.clear_cache()

# Autenticar
print("\nAutenticando...")
if not client.authenticate():
    print("ERROR: No se pudo autenticar")
    sys.exit(1)

print("Autenticacion exitosa")

# Obtener balance
print("\nObteniendo balance...")
balance_info = client.get_balance()

print("\n" + "=" * 60)
print("RESULTADO:")
print("=" * 60)
print(f"Balance: ${balance_info.get('balance')}")
print(f"Currency: {balance_info.get('currency')}")
print(f"Login ID: {balance_info.get('loginid')}")
print(f"Account Type: {balance_info.get('account_type')}")
print()

account_type = balance_info.get('account_type', '').lower()
balance = balance_info.get('balance', 0)

if 'real' in account_type:
    print("=" * 60)
    print("CUENTA: REAL - Dinero real habilitado")
    print("=" * 60)
    print()
    print("Si el balance aun muestra demo en el dashboard,")
    print("recarga la pagina o reinicia el servidor Django.")
elif balance == 10000.0:
    print("=" * 60)
    print("ATENCION: Balance de DEMO detectado")
    print("=" * 60)
    print()
    print("El balance es $10,000 USD, típico de cuenta demo.")
    print("Verifica que el token sea de cuenta REAL en Deriv.")
else:
    print("=" * 60)
    print("CUENTA: Verifica en Deriv")
    print("=" * 60)
    print()
    print(f"Balance: ${balance}")
    print("Verifica en Deriv si este es el balance real.")

