#!/usr/bin/env python3
"""
Comando para poblar datos de Yahoo Finance
"""

from django.core.management.base import BaseCommand
from market.models import Candle
from connectors.yahoo_finance_client import YahooFinanceClient
from datetime import datetime
import time


class Command(BaseCommand):
    help = 'Poblar datos históricos de Yahoo Finance'

    def add_arguments(self, parser):
        parser.add_argument('--symbols', nargs='+', 
                          default=['EURUSD', 'GBPUSD', 'USDJPY', 'R_10', 'R_25', 'GOLD'], 
                          help='Símbolos a poblar')
        parser.add_argument('--timeframes', nargs='+', 
                          default=['1h', '1d'], 
                          help='Timeframes a poblar')

    def handle(self, *args, **options):
        symbols = options['symbols']
        timeframes = options['timeframes']
        
        self.stdout.write("🔄 Poblando datos de Yahoo Finance...")
        
        yahoo_client = YahooFinanceClient()
        total_created = 0
        
        for symbol in symbols:
            self.stdout.write(f"\n📊 Procesando {symbol}...")
            
            for timeframe in timeframes:
                try:
                    self.stdout.write(f"  🔄 Obteniendo {timeframe}...")
                    
                    # Obtener datos usando el cliente
                    data = yahoo_client.get_candles(symbol, timeframe, count=500)
                    
                    if not data:
                        self.stdout.write(f"  ⚠️ Sin datos para {symbol} {timeframe}")
                        continue
                    
                    created_count = 0
                    for item in data:
                        candle, created = Candle.objects.get_or_create(
                            symbol=symbol,
                            timeframe=timeframe,
                            timestamp=datetime.fromtimestamp(item['timestamp']),
                            defaults={
                                'open': item['open'],
                                'high': item['high'],
                                'low': item['low'],
                                'close': item['close'],
                                'volume': item.get('volume', 0)
                            }
                        )
                        if created:
                            created_count += 1
                    
                    total_created += created_count
                    self.stdout.write(f"  ✅ {created_count} velas creadas para {symbol} {timeframe}")
                    
                    time.sleep(1)
                    
                except Exception as e:
                    self.stdout.write(f"  ❌ Error con {symbol} {timeframe}: {e}")
                    continue
        
        self.stdout.write(f"\n🎉 ¡Población completada!")
        self.stdout.write(f"📈 Total de velas creadas: {total_created}")
        self.stdout.write(f"📊 Símbolos: {', '.join(symbols)}")
        self.stdout.write(f"⏰ Timeframes: {', '.join(timeframes)}")

