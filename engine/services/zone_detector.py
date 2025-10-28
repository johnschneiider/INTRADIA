from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Iterable, Optional

from django.db import transaction

from market.models import Candle, Zone, ZonePeriod, Timeframe
from market.indicators import atr


def _dec(x: float | Decimal) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def compute_zones(symbol: str, zone_period: ZonePeriod, candles: Iterable[Candle]) -> Optional[Zone]:
    candles = list(candles)
    if not candles:
        return None
    # Period OHLC
    open_p = _dec(candles[0].open)
    close_p = _dec(candles[-1].close)
    high_p = max(_dec(c.high) for c in candles)
    low_p = min(_dec(c.low) for c in candles)

    zone_low = min(open_p, close_p)
    zone_high = max(open_p, close_p)
    zone_height = zone_high - zone_low

    highs = [float(c.high) for c in candles]
    lows = [float(c.low) for c in candles]
    closes = [float(c.close) for c in candles]
    period_atr = atr(highs, lows, closes, period=14)[-1]
    atr_dec = _dec(period_atr)

    if abs(open_p - close_p) < atr_dec * Decimal('0.2'):
        padding = atr_dec * Decimal('0.5')
        zone_low = _dec(low_p) - padding
        zone_high = _dec(high_p) + padding
        zone_height = zone_high - zone_low

    with transaction.atomic():
        z = Zone.objects.create(
            symbol=symbol,
            zone_period=zone_period,
            zone_low=zone_low,
            zone_high=zone_high,
            zone_height=zone_height,
            timestamp=candles[-1].timestamp,
            meta={
                'open_p': str(open_p),
                'close_p': str(close_p),
                'high_p': str(high_p),
                'low_p': str(low_p),
                'atr': float(atr_dec),
            },
        )
    return z

