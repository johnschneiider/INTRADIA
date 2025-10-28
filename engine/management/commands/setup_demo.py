from django.core.management.base import BaseCommand
from datetime import datetime, timedelta
from decimal import Decimal
import random
from market.models import Candle, Zone, Timeframe, ZonePeriod
from engine.services.zone_detector import compute_zones
from engine.services.rule_loop import process_symbol_rule_loop


class Command(BaseCommand):
    help = 'Configura datos de demostración y ejecuta la estrategia'

    def handle(self, *args, **options):
        self.stdout.write("🎯 Configurando datos de demostración...")
        
        symbols = ['EURUSD', 'GBPUSD', 'USDJPY']
        
        for symbol in symbols:
            self.stdout.write(f"📊 Generando datos para {symbol}...")
            
            # Generar datos históricos
            daily_candles = self.generate_realistic_candles(symbol, '1d', 30)
            weekly_candles = self.generate_realistic_candles(symbol, '1w', 10)
            intraday_candles = self.generate_realistic_candles(symbol, '5m', 200)
            
            self.stdout.write(f"✅ {symbol}: {len(daily_candles)} días, {len(weekly_candles)} semanas, {len(intraday_candles)} velas 5m")
            
            # Calcular zonas
            daily_zone = compute_zones(symbol, ZonePeriod.DAY, daily_candles)
            weekly_zone = compute_zones(symbol, ZonePeriod.WEEK, weekly_candles)
            
            if daily_zone:
                self.stdout.write(f"🎯 Zona diaria {symbol}: [{daily_zone.zone_low}, {daily_zone.zone_high}]")
            
            if weekly_zone:
                self.stdout.write(f"🎯 Zona semanal {symbol}: [{weekly_zone.zone_low}, {weekly_zone.zone_high}]")
        
        self.stdout.write("🎉 ¡Datos de demostración listos!")
        
        # Probar estrategia
        self.stdout.write("\n🔍 Probando estrategia completa...")
        for symbol in symbols:
            result = process_symbol_rule_loop(symbol)
            self.stdout.write(f"🎯 Resultado {symbol}: {result}")
        
        self.stdout.write("✅ ¡Sistema listo para trading!")

    def generate_realistic_candles(self, symbol: str, timeframe: str, count: int):
        base_price = 1.0500 if 'EUR' in symbol else 1.2500 if 'GBP' in symbol else 110.0
        
        candles = []
        current_price = base_price
        timestamp = datetime.now() - timedelta(hours=count)
        
        for i in range(count):
            change = random.uniform(-0.002, 0.002)
            current_price *= (1 + change)
            
            open_price = current_price
            high_price = current_price * random.uniform(1.0001, 1.0015)
            low_price = current_price * random.uniform(0.9985, 0.9999)
            close_price = current_price * random.uniform(0.999, 1.001)
            
            candles.append(Candle.objects.create(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=timestamp,
                open=Decimal(str(round(open_price, 4))),
                high=Decimal(str(round(high_price, 4))),
                low=Decimal(str(round(low_price, 4))),
                close=Decimal(str(round(close_price, 4))),
                volume=Decimal(str(random.randint(800, 1200)))
            ))
            
            if timeframe == '5m':
                timestamp += timedelta(minutes=5)
            elif timeframe == '1d':
                timestamp += timedelta(days=1)
            elif timeframe == '1w':
                timestamp += timedelta(weeks=1)
        
        return candles
