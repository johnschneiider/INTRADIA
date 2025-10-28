#!/usr/bin/env python3
"""
Script para probar qué símbolos de Deriv tienen datos históricos disponibles
"""

import os
import sys
import django
import time
import json

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from connectors.deriv_client import DerivClient

def test_symbols():
    """Probar diferentes símbolos de Deriv para ver cuáles tienen datos históricos"""
    
    # Lista de símbolos comunes de Deriv
    test_symbols = [
        # Índices sintéticos
        'R_10', 'R_25', 'R_50', 'R_75', 'R_100',
        'RDBULL', 'RDBEAR', 'RDSNG', 'RDDOOM',
        
        # Índices de volatilidad
        'V_10', 'V_25', 'V_50', 'V_75', 'V_100',
        'VDBULL', 'VDBEAR', 'VDSNG', 'VDDOOM',
        
        # Índices crash/boom
        'CRASH', 'BOOM', 'CRASH1000', 'BOOM1000',
        'CRASH500', 'BOOM500', 'CRASH300', 'BOOM300',
        
        # Índices híbridos
        'H_10', 'H_25', 'H_50', 'H_75', 'H_100',
        
        # CFD (con prefijo cr)
        'crEURUSD', 'crGBPUSD', 'crUSDJPY', 'crAUDUSD',
        'crUSDCAD', 'crUSDCHF', 'crNZDUSD', 'crEURGBP',
        
        # Commodities
        'crGOLD', 'crSILVER', 'crOIL', 'crCOPPER',
        
        # Índices bursátiles
        'crUS500', 'crUK100', 'crDE30', 'crFR40',
        'crAU200', 'crJP225', 'crES35', 'crIT40',
        
        # Criptomonedas
        'crBTCUSD', 'crETHUSD', 'crLTCUSD', 'crXRPUSD',
    ]
    
    client = DerivClient()
    print("🔑 Conectando a Deriv API...")
    
    if not client.authenticate():
        print("❌ No se pudo autenticar con Deriv")
        return
    
    print("✅ Autenticación exitosa")
    print(f"💰 Balance: ${client.get_balance().get('balance', 'N/A')}")
    print("\n🔍 Probando símbolos para datos históricos...")
    print("=" * 60)
    
    symbols_with_data = []
    symbols_without_data = []
    
    for symbol in test_symbols:
        try:
            print(f"📊 Probando {symbol}...", end=" ")
            
            # Probar obtener datos históricos
            candles = client.get_candles(symbol, '5m', 10)
            
            if candles and len(candles) > 0:
                print(f"✅ {len(candles)} velas disponibles")
                symbols_with_data.append(symbol)
            else:
                print("❌ Sin datos")
                symbols_without_data.append(symbol)
            
            # Rate limiting
            time.sleep(1)
            
        except Exception as e:
            print(f"❌ Error: {str(e)[:50]}")
            symbols_without_data.append(symbol)
            time.sleep(1)
    
    print("\n" + "=" * 60)
    print("📈 RESUMEN DE RESULTADOS:")
    print("=" * 60)
    
    if symbols_with_data:
        print(f"\n✅ SÍMBOLOS CON DATOS HISTÓRICOS ({len(symbols_with_data)}):")
        for symbol in symbols_with_data:
            print(f"   • {symbol}")
    else:
        print("\n⚠️ No se encontraron símbolos con datos históricos")
    
    if symbols_without_data:
        print(f"\n❌ SÍMBOLOS SIN DATOS HISTÓRICOS ({len(symbols_without_data)}):")
        for symbol in symbols_without_data:
            print(f"   • {symbol}")
    
    print(f"\n📊 Total probados: {len(test_symbols)}")
    print(f"✅ Con datos: {len(symbols_with_data)}")
    print(f"❌ Sin datos: {len(symbols_without_data)}")
    
    if symbols_with_data:
        print(f"\n💡 RECOMENDACIÓN: Usar estos símbolos para el sistema:")
        for symbol in symbols_with_data[:5]:  # Mostrar los primeros 5
            print(f"   • {symbol}")
    
    return symbols_with_data, symbols_without_data

if __name__ == "__main__":
    test_symbols()


