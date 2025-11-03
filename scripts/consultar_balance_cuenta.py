"""
Script para consultar el balance y ID de la cuenta de Deriv
"""
import os
import sys
import django

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from trading_bot.models import DerivAPIConfig
from connectors.deriv_client import DerivClient


def consultar_balance_cuenta():
    """Consultar balance y ID de cuenta desde Deriv"""
    print("=" * 60)
    print("CONSULTA DE BALANCE Y CUENTA".center(60))
    print("=" * 60)
    
    # Obtener configuración activa
    try:
        config = DerivAPIConfig.objects.filter(is_active=True).only('api_token', 'is_demo', 'app_id').first()
        if not config:
            print("❌ No hay configuración de API activa")
            print("   Configura el token en: http://localhost:8000/trading/config/api/")
            return False
        
        print(f"\n✅ Configuración encontrada:")
        print(f"   Token: {config.api_token[:15]}...{config.api_token[-5:]}")
        print(f"   Tipo: {'REAL' if not config.is_demo else 'DEMO'}")
        print(f"   App ID: {config.app_id}")
        
        # Crear cliente Deriv
        print(f"\n🔌 Conectando a Deriv...")
        client = DerivClient(
            api_token=config.api_token,
            is_demo=config.is_demo,
            app_id=config.app_id
        )
        
        # Autenticar
        print(f"🔐 Autenticando...")
        if not client.authenticate():
            print("❌ Error al autenticar con Deriv")
            return False
        
        # Obtener balance
        print(f"\n💰 Obteniendo balance...")
        balance_info = client.get_balance()
        
        if isinstance(balance_info, dict):
            balance = balance_info.get('balance', 0)
            currency = balance_info.get('currency', 'USD')
            loginid = balance_info.get('loginid', 'N/A')
            account_type = balance_info.get('account_type', 'unknown')
            error = balance_info.get('error')
            
            if error:
                print(f"❌ Error obteniendo balance: {error}")
                return False
            
            # Mostrar información
            print("\n" + "=" * 60)
            print("INFORMACIÓN DE LA CUENTA".center(60))
            print("=" * 60)
            print(f"📊 LoginID (ID de cuenta): {loginid}")
            print(f"💰 Balance: {currency} {balance:.2f}")
            print(f"🏷️  Tipo de cuenta: {account_type.upper()}")
            print(f"🔗 Cuenta objetivo: CRW719150")
            
            # Verificar si coincide con la cuenta objetivo
            if loginid == 'CRW719150':
                print(f"✅ La cuenta autenticada coincide con la cuenta objetivo")
            else:
                print(f"⚠️  La cuenta autenticada ({loginid}) NO coincide con la cuenta objetivo (CRW719150)")
                print(f"   Deriv autenticó con {loginid} pero queremos usar CRW719150")
            
            # Mostrar account_list si está disponible
            if client.account_list:
                print(f"\n📋 Cuentas disponibles en account_list:")
                for account in client.account_list:
                    acc_loginid = account.get('loginid', 'N/A')
                    acc_type = account.get('account_type', 'N/A')
                    acc_category = account.get('account_category', 'N/A')
                    is_virtual = account.get('is_virtual', 1)
                    acc_type_str = 'DEMO' if (is_virtual == 1 or acc_loginid.startswith('VRTC') or acc_loginid.startswith('VRT')) else 'REAL'
                    print(f"   • {acc_loginid} | {acc_type_str} | {acc_category}")
                    if acc_loginid == 'CRW719150':
                        print(f"     ✓ Esta es la cuenta objetivo")
            
            print("\n" + "=" * 60)
            return True
        else:
            print(f"❌ Respuesta inesperada: {type(balance_info)}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    consultar_balance_cuenta()

