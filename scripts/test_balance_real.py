"""
Script para probar la obtención del balance REAL
"""
import os
import sys
import django
import time

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from connectors.deriv_client import DerivClient
from trading_bot.models import DerivAPIConfig

def test_balance_real():
    print("=" * 60)
    print("TEST DE BALANCE REAL".center(60))
    print("=" * 60)
    
    # Obtener configuración
    try:
        config = DerivAPIConfig.objects.filter(is_active=True).only('api_token', 'is_demo', 'app_id').first()
        if not config:
            print("❌ No hay configuración de API activa")
            return False
        
        print(f"\n📋 Configuración:")
        print(f"   Token: {config.api_token[:10]}...{config.api_token[-5:]}")
        print(f"   Tipo cuenta: {'DEMO' if config.is_demo else 'REAL'}")
        print(f"   App ID: {config.app_id}")
        
        if config.is_demo:
            print("\n⚠️  ADVERTENCIA: La configuración está marcada como DEMO")
            print("   Para probar balance REAL, marca is_demo=False")
            return False
        
        # Crear cliente
        print(f"\n🔑 Inicializando DerivClient...")
        client = DerivClient(
            api_token=config.api_token,
            is_demo=config.is_demo,
            app_id=config.app_id
        )
        
        # Autenticar
        print(f"\n🔐 Autenticando...")
        if not client.authenticate():
            print("❌ Error en autenticación")
            return False
        
        print(f"✅ Autenticación exitosa")
        print(f"   current_loginid: {client.current_loginid}")
        
        # Obtener balance
        print(f"\n💰 Obteniendo balance...")
        balance_info = client.get_balance()
        
        print(f"\n📊 Resultado:")
        print(f"   Balance: ${balance_info.get('balance', 0):.2f}")
        print(f"   Currency: {balance_info.get('currency', 'USD')}")
        print(f"   Account Type: {balance_info.get('account_type', 'unknown').upper()}")
        print(f"   LoginID: {balance_info.get('loginid', 'unknown')}")
        print(f"   Source: {balance_info.get('source', 'unknown')}")
        
        if balance_info.get('warning'):
            print(f"   ⚠️  Warning: {balance_info.get('warning')}")
        
        # Verificar
        is_real = balance_info.get('account_type') == 'real'
        loginid = balance_info.get('loginid', '')
        is_real_loginid = loginid and not (loginid.startswith('VRTC') or loginid.startswith('VRT'))
        
        print(f"\n✅ Verificación:")
        if is_real and is_real_loginid and loginid == client.current_loginid:
            print(f"   ✅ Balance REAL confirmado")
            print(f"   ✅ LoginID coincide con current_loginid")
            print(f"   ✅ Account type es 'real'")
            if balance_info.get('balance', 0) > 0:
                print(f"   ✅ Balance mayor a $0.00")
                return True
            else:
                print(f"   ⚠️  Balance es $0.00 (puede ser correcto si no has recargado)")
                return True
        else:
            print(f"   ❌ Balance NO REAL confirmado")
            if not is_real:
                print(f"   ❌ Account type no es 'real'")
            if not is_real_loginid:
                print(f"   ❌ LoginID es DEMO ({loginid})")
            if loginid != client.current_loginid:
                print(f"   ❌ LoginID no coincide con current_loginid")
            return False
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_balance_real()

