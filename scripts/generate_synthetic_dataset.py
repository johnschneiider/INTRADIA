import os
import json
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from market.models import Candle, Zone, Timeframe
from engine.services.rule_loop import _get_intraday_series
from engine.services.sweep_detector import detect_liquidity_sweep
from engine.services.rule_based import decide_entry_after_sweep


def main(symbol: str = 'SYMBOL', timeframe: str = Timeframe.M5, out_path: str = 'dataset.jsonl'):
    candles, opens, highs, lows, closes, vols = _get_intraday_series(symbol, timeframe)
    zone = Zone.objects.filter(symbol=symbol).order_by('-timestamp').first()
    if not zone:
        print('no zone, abort')
        return
    evt = detect_liquidity_sweep(symbol, zone, candles)
    if not evt:
        print('no sweep, abort')
        return
    decision = decide_entry_after_sweep(
        evt.direction, 
        zone, 
        highs, 
        lows, 
        closes, 
        vols,
        intraday_opens=opens,
        use_advanced_filters=True  # Sistema bayesiano completo
    )
    record = {
        'state': {
            'closes': closes[-100:],
            'ema8': [],
            'atr14': [],
            'zone_low': float(zone.zone_low),
            'zone_high': float(zone.zone_high),
        },
        'action_rule': decision.side if decision else 'NO_TRADE',
        'reward': 0.0,
    }
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(json.dumps(record) + '\n')
    print('written', out_path)


if __name__ == '__main__':
    main()

