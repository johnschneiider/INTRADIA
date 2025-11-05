from django.urls import path
from .views import (
    status, 
    get_balance, 
    get_trades,
    metrics,
    dashboard,
    capital_config, 
    trading_config_api,
    quick_controls_api, 
    services_admin, 
    services_status_api, 
    services_restart_api, 
    services_logs_api, 
    trading_loop_control_api, 
    active_trades_api, 
    close_trade_api
)

app_name = 'engine'

urlpatterns = [
    path('', dashboard, name='dashboard'),
    path('status/', status, name='status'),
    path('balance/', get_balance, name='balance'),
    path('trades/', get_trades, name='trades'),
    path('metrics/', metrics, name='metrics'),
    path('capital-config/', capital_config, name='capital-config'),
    path('trading-config-api/', trading_config_api, name='trading-config-api'),
    path('quick-controls-api/', quick_controls_api, name='quick-controls-api'),
    path('services-admin/', services_admin, name='services-admin'),
    path('api/services/status/', services_status_api, name='services-status'),
    path('api/services/restart/', services_restart_api, name='services-restart'),
    path('api/services/logs/', services_logs_api, name='services-logs'),
    path('api/trading-loop/control/', trading_loop_control_api, name='trading-loop-control'),
    path('api/trades/active/', active_trades_api, name='active-trades'),
    path('api/trades/close/', close_trade_api, name='close-trade'),
]

