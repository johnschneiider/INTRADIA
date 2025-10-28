#!/usr/bin/env python
"""
Script para poblar la base de datos con datos simulados realistas
y luego ejecutar el sistema completo
"""
import os
import django
from datetime import datetime, timedelta
from decimal import Decimal
import random

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from market.models import Candle, Zone, Timeframe, ZonePeriod
from engine.services.zone_detector import compute_zones
from engine.services.sweep_detector import detect_liquidity_sweep
from engine.services.rule_loop import process_symbol_rule_loop


def generate_realistic_candles(symbol: str, timeframe: str, count: int):
    """Genera velas realistas para simular datos de mercado"""
    base_price = 1.0500 if 'EUR' in symbol else 1.2500 if 'GBP' in symbol else 110.0
    
    candles = []
    current_price = base_price
    timestamp = datetime.now() - timedelta(hours=count)
    
    for i in range(count):
        # Movimiento de precio realista
        change = random.uniform(-0.002, 0.002)  # ±0.2%
        current_price *= (1 + change)
        
        # Generar OHLC
        open_price = current_price
        high_price = current_price * random.uniform(1.0001, 1.0015)
        low_price = current_price * random.uniform(0.9985, 0.9999)
        close_price = current_price * random.uniform(0.999, 1.001)
        
        candles.append(Candle.objects.create(
            symbol=symbol,
            timeframe=getattr(Timeframe, timeframe.upper().replace('M', 'M').replace('H', 'H').replace('D', 'D').replace('W', 'W')),
            timestamp=timestamp,
            open=Decimal(str(round(open_price, 4))),
            high=Decimal(str(round(high_price, 4))),
            low=Decimal(str(round(low_price, 4))),
            close=Decimal(str(round(close_price, 4))),
            volume=Decimal(str(random.randint(800, 1200)))
        ))
        
        # Incrementar timestamp según timeframe
        if timeframe == '5m':
            timestamp += timedelta(minutes=5)
        elif timeframe == '1d':
            timestamp += timedelta(days=1)
        elif timeframe == '1w':
            timestamp += timedelta(weeks=1)
    
    return candles


def setup_demo_data():
    """Configura datos de demostración realistas"""
    print("🎯 Configurando datos de demostración...")
    
    symbols = ['EURUSD', 'GBPUSD', 'USDJPY']
    
    for symbol in symbols:
        print(f"📊 Generando datos para {symbol}...")
        
        # Generar datos históricos
        daily_candles = generate_realistic_candles(symbol, '1d', 30)
        weekly_candles = generate_realistic_candles(symbol, '1w', 10)
        intraday_candles = generate_realistic_candles(symbol, '5m', 200)
        
        print(f"✅ {symbol}: {len(daily_candles)} días, {len(weekly_candles)} semanas, {len(intraday_candles)} velas 5m")
        
        # Calcular zonas
        daily_zone = compute_zones(symbol, ZonePeriod.DAY, daily_candles)
        weekly_zone = compute_zones(symbol, ZonePeriod.WEEK, weekly_candles)
        
        if daily_zone:
            print(f"🎯 Zona diaria {symbol}: [{daily_zone.zone_low}, {daily_zone.zone_high}]")
        
        if weekly_zone:
            print(f"🎯 Zona semanal {symbol}: [{weekly_zone.zone_low}, {weekly_zone.zone_high}]")
    
    print("🎉 ¡Datos de demostración listos!")
    print("🚀 Sistema listo para ejecutar estrategia completa")


def test_strategy():
    """Prueba la estrategia completa"""
    print("\n🔍 Probando estrategia completa...")
    
    symbols = ['EURUSD', 'GBPUSD', 'USDJPY']
    
    for symbol in symbols:
        print(f"\n📈 Analizando {symbol}...")
        
        # Ejecutar bucle de estrategia
        result = process_symbol_rule_loop(symbol)
        print(f"🎯 Resultado {symbol}: {result}")
    
    print("\n✅ ¡Estrategia probada exitosamente!")


if __name__ == '__main__':
    setup_demo_data()
    test_strategy()

