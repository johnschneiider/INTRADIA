"""Verificar tipo de cuenta"""
import os, sys, django
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from connectors.deriv_client import DerivClient

client = DerivClient()
print("Token:", client.api_token[:15])
if client.authenticate():
    b = client.get_balance()
    print("Balance:", b.get('balance'))
    print("Account Type:", b.get('account_type'))
    print("LoginID:", b.get('loginid'))
    if 'real' in b.get('account_type', '').lower():
        print(">> CUENTA REAL - Dinero real habilitado")
    else:
        print(">> CUENTA DEMO - Solo dinero virtual")
else:
    print("ERROR: Autenticacion fallida")

