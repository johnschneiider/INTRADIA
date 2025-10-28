from django.urls import path
from .views import status, get_balance, get_trades, metrics, test_deriv_connection, orders, backtest_run, trader_kill, policy_promote, dashboard, candles, ticks_realtime


urlpatterns = [
    path('', dashboard, name='dashboard'),
    path('status/', status, name='engine-status'),
    path('balance/', get_balance, name='get-balance'),
    path('trades/', get_trades, name='get-trades'),
    path('metrics/', metrics, name='engine-metrics'),
    path('candles/', candles, name='engine-candles'),
    path('ticks/realtime/', ticks_realtime, name='ticks-realtime'),
    path('test-deriv/', test_deriv_connection, name='test-deriv'),
    path('orders/', orders, name='engine-orders'),
    path('backtest/run/', backtest_run, name='backtest-run'),
    path('trader/kill/', trader_kill, name='trader-kill'),
    path('trader/policy/promote/', policy_promote, name='policy-promote'),
]

