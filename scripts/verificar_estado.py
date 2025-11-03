import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from engine.models import CapitalConfig
from monitoring.models import OrderAudit
from django.utils import timezone
from datetime import timedelta

config = CapitalConfig.get_active()
today = timezone.now().date()
today_trades = OrderAudit.objects.filter(timestamp__date=today)

print('📊 ESTADO DEL SISTEMA')
print('=' * 50)
print(f'✅ disable_max_trades: {config.disable_max_trades}')
print(f'✅ max_trades config: {config.max_trades}')
print(f'✅ Trades hoy: {today_trades.count()}')
print(f'✅ Ganados: {today_trades.filter(status="won").count()}')
print(f'✅ Perdidos: {today_trades.filter(status="lost").count()}')
print(f'✅ Pendientes: {today_trades.filter(status__in=["pending", "active"]).count()}')
print('=' * 50)

# Verificar últimos 10 trades
print('\n📋 ÚLTIMOS 10 TRADES:')
recent_trades = OrderAudit.objects.order_by('-timestamp')[:10]
for trade in recent_trades:
    print(f'  {trade.symbol} {trade.action} | {trade.status} | ${trade.amount if hasattr(trade, "amount") else "N/A"} | {trade.timestamp.strftime("%H:%M:%S")}')

