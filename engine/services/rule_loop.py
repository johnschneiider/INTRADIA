from __future__ import annotations

from datetime import timedelta, date
from decimal import Decimal
from typing import Optional

from django.utils import timezone

from market.models import Candle, Zone, LiquiditySweep, Timeframe
from monitoring.models import OrderAudit
from engine.services.sweep_detector import detect_liquidity_sweep
from engine.services.rule_based import decide_entry_after_sweep
from engine.services.execution_gateway import place_order_through_gateway


def _get_intraday_series(symbol: str, timeframe: str = Timeframe.M5, lookback: int = 200):
    qs = Candle.objects.filter(symbol=symbol, timeframe=timeframe).order_by('-timestamp')[:lookback]
    candles = list(reversed(list(qs)))
    opens = [float(c.open) for c in candles]
    highs = [float(c.high) for c in candles]
    lows = [float(c.low) for c in candles]
    closes = [float(c.close) for c in candles]
    vols = [float(c.volume) for c in candles]
    return candles, opens, highs, lows, closes, vols


def process_symbol_rule_loop(symbol: str, *, max_retest_time_hours: int = 24, max_daily_trades: int = 5) -> Optional[dict]:
    """
    Procesa símbolo con límite de operaciones diarias.
    
    Args:
        max_daily_trades: Máximo de trades por día por símbolo (default: 5)
    """
    # MEJORA: Limitar operaciones diarias
    today = timezone.now().date()
    daily_trades = OrderAudit.objects.filter(
        symbol=symbol,
        timestamp__date=today,
        status__in=['won', 'lost']
    ).count()
    
    if daily_trades >= max_daily_trades:
        return {'status': 'max_daily_trades_reached', 'trades_today': daily_trades}
    
    # Usar última zona disponible (preferir WEEK, luego DAY)
    zone = Zone.objects.filter(symbol=symbol).order_by('-timestamp').first()
    if not zone:
        return {'status': 'no_zone'}

    candles, opens, highs, lows, closes, vols = _get_intraday_series(symbol, timeframe=Timeframe.M5)
    if not candles:
        return {'status': 'no_candles'}

    sweep = detect_liquidity_sweep(symbol, zone, candles)
    if not sweep:
        return {'status': 'no_sweep'}

    # Registrar sweep
    LiquiditySweep.objects.get_or_create(
        symbol=symbol,
        zone=zone,
        sweep_time=sweep.sweep_time,
        direction=sweep.direction,
        defaults={'meta': {}},
    )

    # Retest window: esperar precio re-visite banda de entrada con confirmación volumen;
    # En este MVP decidimos inmediatamente usando última vela como confirmación.
    decision = decide_entry_after_sweep(
        direction=sweep.direction,
        zone=zone,
        intraday_highs=highs,
        intraday_lows=lows,
        intraday_closes=closes,
        vol_series=vols,
        intraday_opens=opens,
        use_advanced_filters=True,  # Sistema bayesiano completo
    )

    if not decision:
        return {'status': 'no_entry'}

    resp = place_order_through_gateway(
        symbol=symbol,
        side=decision.side,
        entry=decision.entry_level,
        stop=decision.stop_level,
        take_profit=decision.tp_level,
        risk_percent=decision.risk_percent,
        order_type='limit',
    )
    return {'status': 'ordered' if resp.get('accepted') else 'rejected', 'resp': resp}


