from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import asyncio
import threading

from .models import TradingBot, Trade, TradingStrategy, DerivAPIConfig, BotLog
from .deriv_service import DerivAPI, TradingEngine


@login_required
def dashboard(request):
    """Dashboard principal del bot"""
    # Obtener bots del usuario
    bots = TradingBot.objects.filter(user=request.user)
    
    # Estadísticas generales
    total_trades_today = Trade.objects.filter(
        user=request.user,
        opened_at__date=timezone.now().date()
    ).count()
    
    profit_today = Trade.objects.filter(
        user=request.user,
        opened_at__date=timezone.now().date(),
        status__in=['won', 'lost']
    ).aggregate(total=Sum('profit'))['total'] or Decimal('0.0')
    
    # Últimos trades
    recent_trades = Trade.objects.filter(user=request.user).order_by('-opened_at')[:10]
    
    # Verificar configuración de API
    has_api_config = hasattr(request.user, 'deriv_config')
    
    context = {
        'bots': bots,
        'total_trades_today': total_trades_today,
        'profit_today': profit_today,
        'recent_trades': recent_trades,
        'has_api_config': has_api_config,
    }
    
    return render(request, 'trading_bot/dashboard.html', context)


@login_required
def bot_list(request):
    """Lista de todos los bots"""
    bots = TradingBot.objects.filter(user=request.user)
    
    context = {
        'bots': bots,
    }
    
    return render(request, 'trading_bot/bot_list.html', context)


@login_required
def bot_detail(request, bot_id):
    """Detalle de un bot específico"""
    bot = get_object_or_404(TradingBot, id=bot_id, user=request.user)
    
    # Trades del bot
    trades = bot.trades.all()[:50]
    
    # Logs recientes
    logs = bot.logs.all()[:20]
    
    # Estadísticas
    total_trades = bot.trades.count()
    won_trades = bot.trades.filter(status='won').count()
    lost_trades = bot.trades.filter(status='lost').count()
    total_profit = bot.trades.filter(status__in=['won', 'lost']).aggregate(
        total=Sum('profit')
    )['total'] or Decimal('0.0')
    
    win_rate = (won_trades / total_trades * 100) if total_trades > 0 else 0
    
    context = {
        'bot': bot,
        'trades': trades,
        'logs': logs,
        'total_trades': total_trades,
        'won_trades': won_trades,
        'lost_trades': lost_trades,
        'total_profit': total_profit,
        'win_rate': win_rate,
    }
    
    return render(request, 'trading_bot/bot_detail.html', context)


@login_required
def bot_create(request):
    """Crear un nuevo bot"""
    if request.method == 'POST':
        # Verificar que el usuario tenga configuración de API
        if not hasattr(request.user, 'deriv_config'):
            messages.error(request, 'Primero debes configurar tu API de Deriv')
            return redirect('trading_bot:api_config')
        
        # Obtener estrategias del usuario
        strategy_id = request.POST.get('strategy')
        strategy = None
        if strategy_id:
            strategy = TradingStrategy.objects.get(id=strategy_id, user=request.user)
        
        # Crear el bot
        bot = TradingBot.objects.create(
            user=request.user,
            name=request.POST.get('name'),
            strategy=strategy,
            symbol=request.POST.get('symbol', 'R_100'),
            contract_type=request.POST.get('contract_type', 'CALL'),
            duration=int(request.POST.get('duration', 1)),
            duration_unit=request.POST.get('duration_unit', 'm'),
            max_daily_loss=Decimal(request.POST.get('max_daily_loss', 50)),
            max_daily_trades=int(request.POST.get('max_daily_trades', 100)),
        )
        
        messages.success(request, f'Bot "{bot.name}" creado exitosamente')
        return redirect('trading_bot:bot_detail', bot_id=bot.id)
    
    # GET request
    strategies = TradingStrategy.objects.filter(user=request.user, is_active=True)
    
    context = {
        'strategies': strategies,
    }
    
    return render(request, 'trading_bot/bot_create.html', context)


@login_required
@require_POST
def bot_start(request, bot_id):
    """Iniciar un bot"""
    bot = get_object_or_404(TradingBot, id=bot_id, user=request.user)
    
    if bot.status == 'running':
        return JsonResponse({'success': False, 'message': 'El bot ya está ejecutándose'})
    
    # Verificar configuración de API
    if not hasattr(request.user, 'deriv_config'):
        return JsonResponse({'success': False, 'message': 'Configura tu API de Deriv primero'})
    
    # Iniciar el bot en un hilo separado
    bot.start()
    
    # Crear log
    BotLog.objects.create(
        bot=bot,
        level='info',
        message='Bot iniciado'
    )
    
    # En producción, aquí iniciarías el bot en un proceso separado
    # Por ahora solo cambiamos el estado
    
    messages.success(request, f'Bot "{bot.name}" iniciado')
    return JsonResponse({'success': True, 'message': 'Bot iniciado correctamente'})


@login_required
@require_POST
def bot_stop(request, bot_id):
    """Detener un bot"""
    bot = get_object_or_404(TradingBot, id=bot_id, user=request.user)
    
    if bot.status == 'stopped':
        return JsonResponse({'success': False, 'message': 'El bot ya está detenido'})
    
    bot.stop()
    
    # Crear log
    BotLog.objects.create(
        bot=bot,
        level='info',
        message='Bot detenido'
    )
    
    messages.success(request, f'Bot "{bot.name}" detenido')
    return JsonResponse({'success': True, 'message': 'Bot detenido correctamente'})


@login_required
@require_POST
def bot_delete(request, bot_id):
    """Eliminar un bot"""
    bot = get_object_or_404(TradingBot, id=bot_id, user=request.user)
    
    if bot.status == 'running':
        return JsonResponse({'success': False, 'message': 'Detén el bot antes de eliminarlo'})
    
    bot_name = bot.name
    bot.delete()
    
    messages.success(request, f'Bot "{bot_name}" eliminado')
    return JsonResponse({'success': True, 'message': 'Bot eliminado correctamente'})


@login_required
def strategy_list(request):
    """Lista de estrategias"""
    strategies = TradingStrategy.objects.filter(user=request.user)
    
    context = {
        'strategies': strategies,
    }
    
    return render(request, 'trading_bot/strategy_list.html', context)


@login_required
def strategy_create(request):
    """Crear una nueva estrategia"""
    if request.method == 'POST':
        config = {}
        
        # Configuración específica según el tipo de estrategia
        strategy_type = request.POST.get('strategy_type')
        
        if strategy_type == 'martingale':
            config['multiplier'] = float(request.POST.get('multiplier', 2.0))
            config['max_sequence'] = int(request.POST.get('max_sequence', 5))
        
        elif strategy_type == 'percentage':
            config['percentage'] = float(request.POST.get('percentage', 2.0))
        
        # Crear la estrategia
        strategy = TradingStrategy.objects.create(
            user=request.user,
            name=request.POST.get('name'),
            strategy_type=strategy_type,
            description=request.POST.get('description', ''),
            initial_stake=Decimal(request.POST.get('initial_stake', 1.0)),
            max_stake=Decimal(request.POST.get('max_stake', 100.0)),
            config=config
        )
        
        messages.success(request, f'Estrategia "{strategy.name}" creada exitosamente')
        return redirect('trading_bot:strategy_list')
    
    context = {
        'strategy_types': TradingStrategy.STRATEGY_TYPES,
    }
    
    return render(request, 'trading_bot/strategy_create.html', context)


@login_required
def api_config(request):
    """Configurar la API de Deriv"""
    config, created = DerivAPIConfig.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        config.api_token = request.POST.get('api_token')
        config.app_id = request.POST.get('app_id', '1089')
        config.is_demo = request.POST.get('is_demo') == 'on'
        config.save()
        
        messages.success(request, 'Configuración de API guardada correctamente')
        return redirect('trading_bot:dashboard')
    
    context = {
        'config': config,
    }
    
    return render(request, 'trading_bot/api_config.html', context)


@login_required
def trades_history(request):
    """Historial completo de trades"""
    trades = Trade.objects.filter(user=request.user).order_by('-opened_at')
    
    # Filtros
    status_filter = request.GET.get('status')
    if status_filter:
        trades = trades.filter(status=status_filter)
    
    date_from = request.GET.get('date_from')
    if date_from:
        trades = trades.filter(opened_at__date__gte=date_from)
    
    date_to = request.GET.get('date_to')
    if date_to:
        trades = trades.filter(opened_at__date__lte=date_to)
    
    # Estadísticas del período
    stats = trades.aggregate(
        total_trades=Count('id'),
        won_trades=Count('id', filter=Q(status='won')),
        lost_trades=Count('id', filter=Q(status='lost')),
        total_profit=Sum('profit')
    )
    
    context = {
        'trades': trades[:100],  # Limitar a 100
        'stats': stats,
    }
    
    return render(request, 'trading_bot/trades_history.html', context)


@login_required
def analytics(request):
    """Análisis y estadísticas avanzadas"""
    # Estadísticas por día (últimos 30 días)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    
    daily_stats = []
    for i in range(30):
        date = timezone.now().date() - timedelta(days=i)
        trades = Trade.objects.filter(
            user=request.user,
            opened_at__date=date,
            status__in=['won', 'lost']
        )
        
        profit = trades.aggregate(total=Sum('profit'))['total'] or Decimal('0.0')
        won = trades.filter(status='won').count()
        lost = trades.filter(status='lost').count()
        total = won + lost
        win_rate = (won / total * 100) if total > 0 else 0
        
        daily_stats.append({
            'date': date.strftime('%Y-%m-%d'),
            'profit': float(profit),
            'trades': total,
            'win_rate': win_rate
        })
    
    daily_stats.reverse()
    
    # Estadísticas por estrategia
    strategy_stats = []
    for strategy in TradingStrategy.objects.filter(user=request.user):
        bots = TradingBot.objects.filter(strategy=strategy)
        trades = Trade.objects.filter(bot__in=bots, status__in=['won', 'lost'])
        
        total_trades = trades.count()
        won_trades = trades.filter(status='won').count()
        total_profit = trades.aggregate(total=Sum('profit'))['total'] or Decimal('0.0')
        win_rate = (won_trades / total_trades * 100) if total_trades > 0 else 0
        
        strategy_stats.append({
            'name': strategy.name,
            'trades': total_trades,
            'profit': float(total_profit),
            'win_rate': win_rate
        })
    
    context = {
        'daily_stats': daily_stats,
        'strategy_stats': strategy_stats,
    }
    
    return render(request, 'trading_bot/analytics.html', context)
