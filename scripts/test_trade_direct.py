"""Script para hacer una prueba directa de trade con amount pequeño"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from engine.services.tick_trading_loop import TickTradingLoop

print("=" * 80)
print("🧪 PRUEBA DIRECTA DE TRADE CON AMOUNT PEQUEÑO")
print("=" * 80)

# Inicializar
loop = TickTradingLoop(use_statistical=True)

# Probar con RDBULL que ha estado dando errores, usando amount muy pequeño
symbol = 'RDBULL'
print(f"\n📊 Probando trade en {symbol} con amount controlado...")

try:
    # Obtener señal primero
    signal = loop.strategy.analyze_symbol(symbol)
    
    if signal:
        print(f"   ✅ Señal encontrada: {signal.direction} (confianza: {signal.confidence:.2f})")
        
        # Procesar símbolo (esto aplicará los límites)
        result = loop.process_symbol(symbol)
        
        print(f"\n✅ Resultado:")
        print(f"   Status: {result.get('status')}")
        print(f"   Reason: {result.get('reason', 'N/A')}")
        
        if result.get('status') == 'executed':
            print(f"   ✅ TRADE EXITOSO!")
            if 'result' in result and result['result'].get('accepted'):
                print(f"   Contract ID: {result['result'].get('contract_id')}")
                print(f"   Amount: ${result['result'].get('amount', 'N/A')}")
        else:
            print(f"   ❌ Trade no ejecutado: {result.get('reason')}")
            if 'result' in result:
                trade_result = result['result']
                if not trade_result.get('accepted'):
                    print(f"   Error específico: {trade_result.get('reason')}")
    else:
        print(f"   ❌ No hay señal para {symbol} en este momento")
        print(f"   Intentando con R_10...")
        
        # Intentar con R_10
        symbol = 'R_10'
        signal = loop.strategy.analyze_symbol(symbol)
        if signal:
            print(f"   ✅ Señal encontrada en R_10: {signal.direction}")
            result = loop.process_symbol(symbol)
            print(f"   Status: {result.get('status')}")
            if result.get('status') == 'executed' and result.get('result', {}).get('accepted'):
                print(f"   ✅ TRADE EXITOSO EN R_10!")
            else:
                print(f"   Razón: {result.get('reason')}")
        else:
            print(f"   ❌ No hay señales disponibles para testing")
        
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)

