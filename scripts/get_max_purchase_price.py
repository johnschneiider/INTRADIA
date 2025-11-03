"""Script para obtener el máximo purchase price real de Deriv"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from connectors.deriv_client import DerivClient
import json
import time

print("=" * 80)
print("🔍 INVESTIGANDO MÁXIMO PURCHASE PRICE DE DERIV")
print("=" * 80)

client = DerivClient()

if not client.authenticate():
    print("❌ Error autenticando")
    sys.exit(1)

# Probar diferentes amounts para encontrar el máximo
symbols_to_test = [
    ('RDBULL', 'CALL', 30),
    ('RDBEAR', 'PUT', 30),
    ('R_10', 'CALL', 30),
]

for symbol, contract_type, duration in symbols_to_test:
    print(f"\n📊 Probando {symbol} {contract_type} ({duration}s)...")
    
    amounts_to_test = [1.0, 5.0, 10.0, 20.0, 25.0, 30.0, 50.0, 100.0]
    
    for test_amount in amounts_to_test:
        try:
            client.response_event.clear()
            req = {
                "proposal": 1,
                "amount": float(test_amount),
                "basis": "stake",
                "contract_type": contract_type,
                "currency": "USD",
                "duration": duration,
                "duration_unit": "s",
                "symbol": symbol,
            }
            client.ws.send(json.dumps(req))
            
            if client.response_event.wait(timeout=5):
                data = client.response_data
                
                if data.get("error"):
                    error_code = data['error'].get('code', '')
                    if 'maximum purchase price' in str(data['error']).lower():
                        print(f"   ❌ ${test_amount}: {error_code}")
                        # Este es el límite, probar uno anterior
                        if test_amount > 1.0:
                            prev_amount = amounts_to_test[amounts_to_test.index(test_amount) - 1]
                            print(f"   ✅ Máximo permitido aproximadamente: ${prev_amount}")
                        break
                    else:
                        print(f"   ⚠️  ${test_amount}: {data['error']}")
                elif data.get("proposal"):
                    proposal = data['proposal']
                    ask_price = proposal.get('ask_price', 0)
                    max_payout = proposal.get('max_payout', 0)
                    print(f"   ✅ ${test_amount}: OK - ask_price: ${ask_price:.2f}, max_payout: ${max_payout:.2f}")
                    time.sleep(0.5)  # Rate limit
                else:
                    print(f"   ⚠️  ${test_amount}: Sin proposal")
            else:
                print(f"   ⚠️  ${test_amount}: Timeout")
                
        except Exception as e:
            print(f"   ❌ ${test_amount}: Error - {e}")
            break

print("\n" + "=" * 80)

