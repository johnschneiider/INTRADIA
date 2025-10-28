from django.urls import path
from . import views

app_name = 'trading_bot'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('bots/', views.bot_list, name='bot_list'),
    path('bots/create/', views.bot_create, name='bot_create'),
    path('bots/<int:bot_id>/', views.bot_detail, name='bot_detail'),
    path('bots/<int:bot_id>/start/', views.bot_start, name='bot_start'),
    path('bots/<int:bot_id>/stop/', views.bot_stop, name='bot_stop'),
    path('bots/<int:bot_id>/delete/', views.bot_delete, name='bot_delete'),
    
    path('strategies/', views.strategy_list, name='strategy_list'),
    path('strategies/create/', views.strategy_create, name='strategy_create'),
    
    path('config/api/', views.api_config, name='api_config'),
    path('trades/', views.trades_history, name='trades_history'),
    path('analytics/', views.analytics, name='analytics'),
]


