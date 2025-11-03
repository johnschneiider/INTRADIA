"""Script para hacer una prueba de trade manual"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from engine.services.tick_trading_loop import TickTradingLoop
from connectors.deriv_client import DerivClient

print("=" * 80)
print("🧪 PRUEBA DE TRADE MANUAL")
print("=" * 80)

# Inicializar
loop = TickTradingLoop(use_statistical=True)
client = DerivClient()

# Probar con R_10 (símbolo común)
symbol = 'R_10'
print(f"\n📊 Probando trade en {symbol}...")

try:
    result = loop.process_symbol(symbol)
    
    print(f"\n✅ Resultado:")
    print(f"   Status: {result.get('status')}")
    print(f"   Reason: {result.get('reason', 'N/A')}")
    
    if result.get('status') == 'executed':
        print(f"   ✅ TRADE EXITOSO!")
        if 'result' in result:
            trade_result = result['result']
            if trade_result.get('accepted'):
                print(f"   Contract ID: {trade_result.get('contract_id')}")
                print(f"   Amount: ${trade_result.get('amount', 'N/A')}")
            else:
                print(f"   ❌ Trade rechazado: {trade_result.get('reason')}")
    else:
        print(f"   ❌ Trade no ejecutado: {result.get('reason')}")
        
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)

