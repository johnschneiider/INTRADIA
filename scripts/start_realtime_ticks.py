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
        
        # Suscribirse a símbolos de Deriv
        symbols = ['R_10', 'R_25', 'R_50', 'CRASH1000', 'BOOM1000']
        
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


