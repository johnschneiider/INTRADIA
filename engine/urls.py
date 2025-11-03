from django.urls import path
from .views import status, get_balance, get_trades, metrics, test_deriv_connection, orders, backtest_run, trader_kill, policy_promote, dashboard, candles, ticks_realtime, capital_config, trading_config_api, quick_controls_api, services_admin, services_status_api, services_restart_api, services_logs_api

app_name = 'engine'

urlpatterns = [
    path('', dashboard, name='dashboard'),
    path('status/', status, name='status'),
    path('balance/', get_balance, name='balance'),
    path('trades/', get_trades, name='trades'),
    path('metrics/', metrics, name='metrics'),
    path('candles/', candles, name='candles'),
    path('ticks/realtime/', ticks_realtime, name='ticks-realtime'),
    path('test-deriv/', test_deriv_connection, name='test-deriv'),
    path('orders/', orders, name='orders'),
    path('backtest/run/', backtest_run, name='backtest-run'),
    path('trader/kill/', trader_kill, name='trader-kill'),
    path('trader/policy/promote/', policy_promote, name='policy-promote'),
    path('capital-config/', capital_config, name='capital-config'),
    path('trading-config-api/', trading_config_api, name='trading-config-api'),
    path('quick-controls-api/', quick_controls_api, name='quick-controls-api'),
    path('services-admin/', services_admin, name='services-admin'),
    path('api/services/status/', services_status_api, name='services-status'),
    path('api/services/restart/', services_restart_api, name='services-restart'),
    path('api/services/logs/', services_logs_api, name='services-logs'),
]

