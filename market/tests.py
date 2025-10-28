from django.test import TestCase
from django.utils import timezone
from decimal import Decimal

from market.models import Candle, Zone, ZonePeriod, Timeframe
from engine.services.zone_detector import compute_zones
from engine.services.sweep_detector import detect_liquidity_sweep
from engine.services.backtester import run_backtest


class ZoneAndSweepTests(TestCase):
    def setUp(self):
        self.symbol = 'SYMBOL'
        ts0 = timezone.now()
        # Crear velas diarias simples
        for i in range(7):
            Candle.objects.create(
                symbol=self.symbol,
                timeframe=Timeframe.D1,
                timestamp=ts0.replace(hour=0, minute=0, second=0, microsecond=0) - timezone.timedelta(days=6 - i),
                open=Decimal('100'), high=Decimal('110'), low=Decimal('90'), close=Decimal('105'), volume=Decimal('1000'),
            )
        # Crear zona diaria por adelantado para las pruebas
        daily = Candle.objects.filter(symbol=self.symbol, timeframe=Timeframe.D1).order_by('timestamp')
        compute_zones(self.symbol, ZonePeriod.DAY, daily)
        # Intradía 5m
        for i in range(60):
            Candle.objects.create(
                symbol=self.symbol,
                timeframe=Timeframe.M5,
                timestamp=ts0 - timezone.timedelta(minutes=5 * (60 - i)),
                open=Decimal('100'), high=Decimal('111'), low=Decimal('89'), close=Decimal('106'), volume=Decimal('100'),
            )

    def test_zone_detection(self):
        daily = Candle.objects.filter(symbol=self.symbol, timeframe=Timeframe.D1).order_by('timestamp')
        z = compute_zones(self.symbol, ZonePeriod.DAY, daily)
        self.assertIsNotNone(z)
        self.assertLess(z.zone_low, z.zone_high)

    def test_sweep_detection(self):
        zone = Zone.objects.filter(symbol=self.symbol).first()
        intraday = Candle.objects.filter(symbol=self.symbol, timeframe=Timeframe.M5).order_by('timestamp')
        evt = detect_liquidity_sweep(self.symbol, zone, intraday)
        # Dadas las velas, debería detectar algún sweep
        self.assertIsNotNone(evt)

    def test_backtest_smoke(self):
        metrics = run_backtest(self.symbol, Timeframe.M5)
        self.assertIn('trades', metrics)
        self.assertIn('winrate', metrics)
