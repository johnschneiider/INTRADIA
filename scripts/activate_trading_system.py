#!/usr/bin/env python3
"""
Script para activar el sistema de trading en vivo
"""

import os
import sys
import django
import time
import threading
from datetime import datetime

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from connectors.deriv_client import DerivClient
from engine.services.rule_loop import process_symbol_rule_loop
from engine.services.execution_gateway import place_order_through_gateway
from market.models import Candle, Zone
from engine.models import OrderAudit

class TradingSystem:
    def __init__(self):
        self.deriv_client = DerivClient()
        self.running = False
        self.symbols = ['EURUSD', 'GBPUSD']
        self.timeframes = ['5m', '15m']
        
    def start(self):
        """Iniciar el sistema de trading"""
        print("🚀 ACTIVANDO SISTEMA DE TRADING EN VIVO")
        print("=" * 60)
        
        # Verificar conexión con Deriv
        if not self.deriv_client.authenticate():
            print("❌ No se pudo conectar a Deriv")
            return False
        
        print("✅ Conexión con Deriv establecida")
        
        # Verificar datos disponibles
        candles_count = Candle.objects.count()
        zones_count = Zone.objects.count()
        
        print(f"📊 Datos disponibles:")
        print(f"   • Velas históricas: {candles_count}")
        print(f"   • Zonas detectadas: {zones_count}")
        
        if candles_count == 0:
            print("⚠️ No hay datos históricos. Ejecutando población...")
            self.populate_historical_data()
        
        if zones_count == 0:
            print("⚠️ No hay zonas detectadas. Calculando zonas...")
            self.calculate_zones()
        
        self.running = True
        print("\n🎯 SISTEMA DE TRADING ACTIVADO")
        print("=" * 60)
        
        # Iniciar loop de trading
        self.trading_loop()
        
        return True
    
    def populate_historical_data(self):
        """Poblar datos históricos si no existen"""
        try:
            from engine.management.commands.populate_yahoo_data import Command
            command = Command()
            command.handle(symbols=self.symbols, timeframes=['1h'])
            print("✅ Datos históricos poblados")
        except Exception as e:
            print(f"❌ Error poblando datos: {e}")
    
    def calculate_zones(self):
        """Calcular zonas de liquidez"""
        try:
            from engine.services.zone_detector import compute_zones
            for symbol in self.symbols:
                candles = Candle.objects.filter(symbol=symbol, timeframe='1h').order_by('timestamp')
                if candles.exists():
                    zones_created = compute_zones(symbol, 'day', candles)
                    print(f"✅ {zones_created} zonas creadas para {symbol}")
        except Exception as e:
            print(f"❌ Error calculando zonas: {e}")
    
    def trading_loop(self):
        """Loop principal de trading"""
        print("🔄 Iniciando loop de trading...")
        print("📊 Monitoreando símbolos:", ", ".join(self.symbols))
        print("⏰ Timeframes:", ", ".join(self.timeframes))
        print("\n🎯 Sistema activo - Presiona Ctrl+C para detener")
        
        cycle = 0
        try:
            while self.running:
                cycle += 1
                print(f"\n🔄 Ciclo #{cycle} - {datetime.now().strftime('%H:%M:%S')}")
                
                for symbol in self.symbols:
                    try:
                        print(f"📊 Procesando {symbol}...")
                        
                        # Procesar símbolo con el loop de reglas
                        result = process_symbol_rule_loop(symbol, '5m')
                        
                        if result:
                            print(f"✅ {symbol}: {result}")
                        else:
                            print(f"ℹ️ {symbol}: Sin señales")
                            
                    except Exception as e:
                        print(f"❌ Error procesando {symbol}: {e}")
                
                # Esperar antes del siguiente ciclo
                print("⏳ Esperando 30 segundos...")
                time.sleep(30)
                
        except KeyboardInterrupt:
            print("\n🛑 Sistema detenido por el usuario")
            self.running = False
        except Exception as e:
            print(f"\n❌ Error en el loop de trading: {e}")
            self.running = False
    
    def stop(self):
        """Detener el sistema"""
        self.running = False
        print("🛑 Sistema de trading detenido")

def main():
    system = TradingSystem()
    
    try:
        success = system.start()
        if success:
            print("\n🎉 Sistema de trading activado exitosamente!")
            print("📊 Dashboard disponible en: http://127.0.0.1:8000/engine/")
            print("🔍 Monitoreando en tiempo real...")
        else:
            print("\n❌ Error activando el sistema")
    except Exception as e:
        print(f"\n❌ Error crítico: {e}")
    finally:
        system.stop()

if __name__ == "__main__":
    main()








