import sys
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from engine.services.backtester import run_backtest


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else 'SYMBOL'
    tf = sys.argv[2] if len(sys.argv) > 2 else '5m'
    metrics = run_backtest(symbol, tf)
    print(metrics)


if __name__ == '__main__':
    main()

