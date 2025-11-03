"""
Script para verificar si un token de Deriv es de cuenta demo o real
"""
import os
import sys
import django

# Setup Django
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from connectors.deriv_client import DerivClient


def verificar_tipo_cuenta():
    """Verificar si el token actual es demo o real"""
    print("=" * 60)
    print("VERIFICANDO TIPO DE CUENTA DEL TOKEN")
    print("=" * 60)
    print()
    
    client = DerivClient()
    print(f"Token: {client.api_token[:10]}...")
    print()
    
    print("Conectando a Deriv...")
    if not client.authenticate():
        print("ERROR: No se pudo autenticar con Deriv")
        print("Verifica que el token sea válido")
        return False
    
    print("Autenticacion exitosa")
    print()
    
    print("Obteniendo informacion de balance...")
    balance_info = client.get_balance()
    
    print()
    print("=" * 60)
    print("RESULTADO:")
    print("=" * 60)
    print(f"Balance: ${balance_info.get('balance', 'N/A')}")
    print(f"Currency: {balance_info.get('currency', 'N/A')}")
    print(f"Login ID: {balance_info.get('loginid', 'N/A')}")
    print(f"Account Type: {balance_info.get('account_type', 'N/A')}")
    print()
    
    account_type = balance_info.get('account_type', '').lower()
    loginid = balance_info.get('loginid', '')
    
    if 'real' in account_type or (loginid and not loginid.startswith('VRTC')):
        print("=" * 60)
        print("CUENTA: REAL - Dinero real habilitado")
        print("=" * 60)
        print()
        print("Puedes usar este token para operar con dinero real.")
        print("IMPORTANTE: Las perdidas seran permanentes.")
        return True
    elif 'demo' in account_type or (loginid and loginid.startswith('VRTC')):
        print("=" * 60)
        print("CUENTA: DEMO - Dinero virtual")
        print("=" * 60)
        print()
        print("Este token es de cuenta demo.")
        print("Para usar dinero real necesitas:")
        print("1. Ir a app.deriv.com")
        print("2. Settings -> API Token")
        print("3. Crear un nuevo token seleccionando 'Real Account'")
        return False
    else:
        print("=" * 60)
        print("CUENTA: DESCONOCIDA")
        print("=" * 60)
        print()
        print("No se pudo determinar el tipo de cuenta.")
        print("Verifica el token y vuelve a intentar.")
        return False


if __name__ == '__main__':
    verificar_tipo_cuenta()

