"""Script para probar directamente place_binary_option con límites"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from engine.services.tick_trading_loop import TickTradingLoop

print("=" * 80)
print("🧪 PRUEBA DIRECTA DE PLACE_BINARY_OPTION")
print("=" * 80)

# Inicializar
loop = TickTradingLoop(use_statistical=True)

# Probar colocando una orden directamente con amounts pequeños
symbols_to_test = [
    ('RDBULL', 'CALL', 50.0),   # Amount muy pequeño
    ('RDBEAR', 'PUT', 50.0),    # Amount muy pequeño
    ('R_10', 'CALL', 100.0),    # Amount pequeño
]

for symbol, side, test_amount in symbols_to_test:
    print(f"\n📊 Probando {symbol} {side} con amount ${test_amount}...")
    
    try:
        # Llamar directamente a place_binary_option
        # Usar duration estándar de 30 segundos
        result = loop.place_binary_option(
            symbol=symbol,
            side='buy' if side == 'CALL' else 'sell',
            amount=test_amount,
            duration=30
        )
        
        if result.get('accepted'):
            print(f"   ✅ TRADE ACEPTADO!")
            print(f"   Contract ID: {result.get('contract_id', 'N/A')}")
            print(f"   Amount usado: ${result.get('amount', test_amount)}")
            print(f"   Balance después: ${result.get('balance_after', 'N/A')}")
            
            # Si funciona, parar aquí para no hacer muchos trades
            print(f"\n✅ ¡PRUEBA EXITOSA! El sistema de límites funciona correctamente.")
            break
        else:
            print(f"   ❌ Trade rechazado: {result.get('reason')}")
            error_msg = result.get('reason', '')
            if 'maximum purchase price' in error_msg.lower():
                print(f"   ⚠️  Aún excede el máximo purchase price con ${test_amount}")
                # Intentar con amount aún más pequeño
                smaller_amount = test_amount * 0.5
                print(f"   🔄 Intentando con ${smaller_amount}...")
                result2 = loop.place_binary_option(
                    symbol=symbol,
                    side='buy' if side == 'CALL' else 'sell',
                    amount=smaller_amount,
                    duration=30
                )
                if result2.get('accepted'):
                    print(f"   ✅ Funciona con ${smaller_amount}!")
                else:
                    print(f"   ❌ Aún falla: {result2.get('reason')}")
                    
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 80)

