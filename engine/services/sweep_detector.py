from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterable, Optional

from django.db import transaction

from market.models import Candle, Zone
from market.indicators import atr


@dataclass
class SweepEvent:
    symbol: str
    zone_id: int
    sweep_time: datetime
    direction: str  # 'long' or 'short'


def detect_liquidity_sweep(symbol: str, zone: Zone, intraday_candles: Iterable[Candle]) -> Optional[SweepEvent]:
    candles = list(intraday_candles)
    if not candles:
        return None
    highs = [float(c.high) for c in candles]
    lows = [float(c.low) for c in candles]
    closes = [float(c.close) for c in candles]
    eps = atr(highs, lows, closes, period=14)[-1] * 0.2

    for c in candles:
        # long sweep: low < zone_low - eps y retorno dentro de la zona (close >= zone_low)
        if float(c.low) < float(zone.zone_low) - eps and float(c.close) >= float(zone.zone_low):
            return SweepEvent(symbol=symbol, zone_id=zone.id, sweep_time=c.timestamp, direction='long')
        # short sweep: high > zone_high + eps y retorno dentro de la zona (close <= zone_high)
        if float(c.high) > float(zone.zone_high) + eps and float(c.close) <= float(zone.zone_high):
            return SweepEvent(symbol=symbol, zone_id=zone.id, sweep_time=c.timestamp, direction='short')
    return None

