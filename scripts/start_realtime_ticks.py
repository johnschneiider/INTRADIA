#!/usr/bin/env python3
"""
Script para iniciar el servicio de ticks en tiempo real
"""

import os
import sys
import django
import time
import threading

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from engine.services.realtime_tick_service import tick_service

def main():
    print("🚀 Iniciando servicio de ticks en tiempo real...")
    
    # Iniciar el servicio
    if tick_service.start():
        print("✅ Servicio de ticks iniciado correctamente")
        
        # Suscribirse a símbolos de Deriv - TODOS los instrumentos activos
        symbols = [
            # Forex - Principales
            'frxEURUSD', 'frxGBPUSD', 'frxUSDJPY', 'frxUSDCHF', 'frxAUDUSD', 'frxUSDCAD',
            'frxNZDUSD', 'frxEURGBP', 'frxEURJPY', 'frxGBPJPY', 'frxAUDJPY', 'frxEURAUD',
            # Commodities
            'frxXAUUSD', 'frxXAGUSD', 'frxXPDUSD', 'frxXPTUSD',
            # Índices sintéticos
            'R_10', 'R_25', 'R_50', 'R_75', 'R_100',
            'BOOM1000', 'CRASH1000', 'BOOM500', 'CRASH500', 'BOOM600', 'CRASH600',
            'RDBULL', 'RDBEAR',
            # Cryptocurrencies
            'cryBTCUSD', 'cryETHUSD',
            # Jump indices
            'JD10', 'JD25', 'JD50', 'JD75',
            # Índices OTC
            'OTC_N225', 'OTC_AS51',
        ]
        
        for symbol in symbols:
            if tick_service.subscribe_to_symbol(symbol):
                print(f"✅ Suscrito a {symbol}")
            else:
                print(f"❌ Error suscribiéndose a {symbol}")
        
        print("📊 Servicio funcionando. Presiona Ctrl+C para detener.")
        
        try:
            # Mantener el servicio corriendo
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Deteniendo servicio...")
            tick_service.stop()
            print("✅ Servicio detenido")
    else:
        print("❌ Error iniciando servicio de ticks")
        sys.exit(1)

if __name__ == "__main__":
    main()





