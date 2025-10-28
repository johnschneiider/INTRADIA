from django.core.management.base import BaseCommand
from connectors.yahoo_finance_client import YahooFinanceClient
from connectors.deriv_client import DerivClient
from market.models import Candle, Tick
from django.utils import timezone
from datetime import datetime, timedelta


class Command(BaseCommand):
    help = 'Obtener datos históricos de Yahoo y ticks en tiempo real de Deriv'

    def add_arguments(self, parser):
        parser.add_argument(
            '--symbols',
            type=str,
            default='EURUSD,GBPUSD',
            help='Símbolos separados por comas'
        )
        parser.add_argument(
            '--timeframes',
            type=str,
            default='1h,1d',
            help='Timeframes separados por comas'
        )

    def handle(self, *args, **options):
        symbols = options['symbols'].split(',')
        timeframes = options['timeframes'].split(',')
        
        # 1. Obtener datos históricos de Yahoo Finance
        self.stdout.write(self.style.SUCCESS('📊 Obteniendo datos históricos de Yahoo Finance...'))
        yahoo = YahooFinanceClient()
        
        for symbol in symbols:
            for tf in timeframes:
                try:
                    self.stdout.write(f'Obteniendo {symbol} {tf}...')
                    data = yahoo.get_candles(symbol, tf, 200)
                    
                    created = 0
                    for item in data:
                        candle, created_obj = Candle.objects.get_or_create(
                            symbol=symbol,
                            timeframe=tf,
                            timestamp=item['timestamp'],
                            defaults={
                                'open': item['open'],
                                'high': item['high'],
                                'low': item['low'],
                                'close': item['close'],
                                'volume': item.get('volume', 0)
                            }
                        )
                        if created_obj:
                            created += 1
                    
                    self.stdout.write(self.style.SUCCESS(
                        f'✅ {symbol} {tf}: {created} nuevas velas'
                    ))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(
                        f'❌ Error con {symbol} {tf}: {e}'
                    ))
        
        # 2. Conectar a Deriv para ticks en tiempo real
        self.stdout.write(self.style.SUCCESS('📡 Conectando a Deriv para ticks en tiempo real...'))
        deriv = DerivClient()
        
        if deriv.authenticate():
            self.stdout.write(self.style.SUCCESS('✅ Conectado a Deriv'))
            self.stdout.write(self.style.SUCCESS('💡 Los ticks se actualizan automáticamente en el dashboard'))
        else:
            self.stdout.write(self.style.ERROR('❌ Error conectando a Deriv'))

