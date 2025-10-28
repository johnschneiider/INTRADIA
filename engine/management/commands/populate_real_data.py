from django.core.management.base import BaseCommand
from connectors.deriv_client import DerivClient
from connectors.yahoo_finance_client import YahooFinanceClient
from market.models import Candle, Zone, Timeframe
from engine.services.zone_detector import compute_zones
from django.utils import timezone
import time


class Command(BaseCommand):
    help = 'Poblar la base de datos con datos históricos reales de Deriv'

    def add_arguments(self, parser):
        parser.add_argument('--symbols', nargs='+', default=['EURUSD', 'GBPUSD', 'USDJPY'], 
                          help='Símbolos a poblar')
        parser.add_argument('--timeframes', nargs='+', default=['5m', '15m', '1h'], 
                          help='Timeframes a poblar')
        parser.add_argument('--count', type=int, default=2000, 
                          help='Número de velas a obtener por símbolo/timeframe')

    def handle(self, *args, **options):
        symbols = options['symbols']
        timeframes = options['timeframes']
        count = options['count']
        
        self.stdout.write("🔄 Iniciando población con datos REALES...")
        self.stdout.write("📊 Usando Yahoo Finance para datos históricos + Deriv para trading en vivo")
        
        # Probar conexión con Deriv para trading en vivo
        deriv_client = DerivClient()
        if deriv_client.authenticate():
            self.stdout.write("✅ Conexión Deriv (trading en vivo): EXITOSA")
        else:
            self.stdout.write("⚠️ Deriv no disponible - solo datos históricos")
        
        # Usar Yahoo Finance para datos históricos
        yahoo_client = YahooFinanceClient()
        if not yahoo_client.test_connection():
            self.stdout.write(self.style.ERROR("❌ No se pudo conectar a Yahoo Finance"))
            return
        
        self.stdout.write("✅ Conexión Yahoo Finance (datos históricos): EXITOSA")
        
        total_created = 0
        
        for symbol in symbols:
            self.stdout.write(f"\n📊 Procesando {symbol}...")
            
            for timeframe in timeframes:
                try:
                    self.stdout.write(f"  🔄 Obteniendo datos históricos REALES de Yahoo Finance para {timeframe}...")
                    
                    # Usar Yahoo Finance para datos históricos
                    candles_data = yahoo_client.get_historical_data(symbol, timeframe, "3mo")
                    
                    if not candles_data:
                        self.stdout.write(f"  ⚠️ No hay datos históricos disponibles para {symbol} {timeframe}")
                        continue
                    
                    created_count = 0
                    for candle_data in candles_data:
                        candle, created = Candle.objects.get_or_create(
                            symbol=symbol,
                            timeframe=timeframe,
                            timestamp=candle_data['timestamp'],
                            defaults={
                                'open': candle_data['open'],
                                'high': candle_data['high'],
                                'low': candle_data['low'],
                                'close': candle_data['close'],
                                'volume': candle_data['volume']
                            }
                        )
                        if created:
                            created_count += 1
                    
                    total_created += created_count
                    self.stdout.write(f"  ✅ {created_count} velas REALES creadas para {symbol} {timeframe}")
                    
                    # Rate limiting
                    time.sleep(1)
                    
                except Exception as e:
                    self.stdout.write(f"  ❌ Error obteniendo datos históricos para {symbol} {timeframe}: {e}")
                    continue
            
            # Calcular zonas desde datos históricos reales
            try:
                self.stdout.write(f"  🔍 Calculando zonas desde datos históricos REALES para {symbol}...")
                candles = Candle.objects.filter(symbol=symbol, timeframe='1d').order_by('timestamp')
                if candles.exists() and candles.count() > 10:
                    zones_created = compute_zones(symbol, 'day', candles)
                    self.stdout.write(f"  ✅ {zones_created} zonas REALES creadas para {symbol}")
                else:
                    # Intentar con timeframe 1h si no hay datos diarios
                    candles = Candle.objects.filter(symbol=symbol, timeframe='1h').order_by('timestamp')
                    if candles.exists() and candles.count() > 24:
                        zones_created = compute_zones(symbol, 'day', candles)
                        self.stdout.write(f"  ✅ {zones_created} zonas REALES creadas para {symbol} (desde datos 1h)")
                    else:
                        self.stdout.write(f"  ⚠️ No hay suficientes datos históricos para calcular zonas de {symbol}")
            except Exception as e:
                self.stdout.write(f"  ❌ Error calculando zonas reales para {symbol}: {e}")
        
        if total_created == 0:
            self.stdout.write(f"\n⚠️ No se obtuvieron datos históricos")
            self.stdout.write(f"💡 El dashboard se mostrará en blanco hasta que haya datos reales")
        else:
            self.stdout.write(f"\n🎉 ¡Población con datos REALES completada!")
            self.stdout.write(f"📈 Total de velas REALES creadas: {total_created}")
        
        self.stdout.write(f"🏦 Datos históricos: Yahoo Finance")
        self.stdout.write(f"📊 Trading en vivo: Deriv WebSocket API")
        self.stdout.write(f"📊 Símbolos procesados: {', '.join(symbols)}")
        self.stdout.write(f"⏰ Timeframes procesados: {', '.join(timeframes)}")
