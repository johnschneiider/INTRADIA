#!/usr/bin/env python
"""
Script para obtener datos históricos de Deriv y poblar la base de datos
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from connectors.deriv_data_service import DerivDataService
from django.conf import settings


def main():
    # Inicializar servicio con tu token
    service = DerivDataService(settings.DERIV_API_TOKEN)
    
    # Símbolos a obtener (ajusta según Deriv)
    symbols = ['EURUSD', 'GBPUSD', 'USDJPY']  # Ejemplo
    timeframes = ['1d', '1w']  # Para zonas
    
    print("🔄 Obteniendo datos históricos de Deriv...")
    
    for symbol in symbols:
        for tf in timeframes:
            print(f"📊 Obteniendo {symbol} {tf}...")
            
            # Obtener datos históricos
            candles = service.get_historical_candles(symbol, tf, count=100)
            
            if candles:
                # Almacenar en DB
                stored = service.store_candles(symbol, tf, candles)
                print(f"✅ {symbol} {tf}: {stored} velas almacenadas")
            else:
                print(f"❌ No se pudieron obtener datos para {symbol} {tf}")
    
    print("🎯 Datos históricos listos para la estrategia!")


if __name__ == '__main__':
    main()
