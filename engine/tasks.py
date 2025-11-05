from celery import shared_task
from django.utils import timezone

from market.models import Candle, Zone, ZonePeriod, Timeframe
from engine.services.zone_detector import compute_zones
from engine.services.sweep_detector import detect_liquidity_sweep
from engine.services.rule_loop import process_symbol_rule_loop
from connectors.deriv_data_service import DerivDataService
from django.conf import settings


@shared_task
def heartbeat():
    return {'ok': True, 'ts': timezone.now().isoformat()}


@shared_task
def fetch_historical_data(symbol: str, timeframe: str = '5m', count: int = 1000):
    """Obtener datos históricos reales de Deriv y almacenarlos"""
    from connectors.deriv_client import DerivClient
    from market.models import Candle, Timeframe
    from django.utils import timezone
    import time
    
    client = DerivClient()
    if not client.authenticate():
        print("❌ No se pudo autenticar con Deriv")
        return {'ok': False, 'error': 'auth_failed'}
    
    try:
        print(f"🔄 Obteniendo datos históricos reales para {symbol} {timeframe}")
        candles_data = client.get_candles(symbol, timeframe, count)
        
        if not candles_data:
            print(f"⚠️ No se obtuvieron datos reales para {symbol} {timeframe}")
            return {'ok': False, 'error': 'no_data'}
        
        created_count = 0
        for candle_data in candles_data:
            candle, created = Candle.objects.get_or_create(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=candle_data['timestamp'],
                defaults={
                    'open': candle_data['open'],
                    'high': candle_data['high'],
                    'low': candle_data['low'],
                    'close': candle_data['close'],
                    'volume': candle_data['volume']
                }
            )
            if created:
                created_count += 1
        
        print(f"✅ {created_count} velas reales nuevas creadas para {symbol} {timeframe}")
        return {'ok': True, 'stored': created_count, 'symbol': symbol, 'timeframe': timeframe}
        
    except Exception as e:
        print(f"❌ Error obteniendo datos reales para {symbol} {timeframe}: {e}")
        return {'ok': False, 'error': str(e)}


@shared_task
def refresh_daily_weekly_zones(symbol: str):
    # Primero obtener datos frescos
    fetch_historical_data.delay(symbol, '1d', 30)
    fetch_historical_data.delay(symbol, '1w', 10)
    
    # Daily
    daily = Candle.objects.filter(symbol=symbol, timeframe=Timeframe.D1).order_by('timestamp')
    if daily.exists():
        compute_zones(symbol, ZonePeriod.DAY, daily)
    # Weekly
    weekly = Candle.objects.filter(symbol=symbol, timeframe=Timeframe.W1).order_by('timestamp')
    if weekly.exists():
        compute_zones(symbol, ZonePeriod.WEEK, weekly)
    return {'ok': True}


@shared_task
def scan_intraday_sweeps(symbol: str, zone_id: int, timeframe: str = Timeframe.M5):
    try:
        zone = Zone.objects.get(id=zone_id)
    except Zone.DoesNotExist:
        return {'ok': False, 'error': 'zone_not_found'}
    candles = Candle.objects.filter(symbol=symbol, timeframe=timeframe).order_by('timestamp')
    evt = detect_liquidity_sweep(symbol, zone, candles)
    return {'ok': True, 'event': evt.__dict__ if evt else None}


@shared_task
def rule_loop_tick(symbol: str):
    """Task antigua basada en zonas - ahora usa ticks"""
    # Usar nueva estrategia basada en ticks
    from engine.services.tick_trading_loop import process_tick_based_trading
    return process_tick_based_trading(symbol)


@shared_task
def process_all_active_symbols():
    """Procesar TODOS los símbolos activos que tengan datos"""
    from market.models import Tick
    from django.utils import timezone
    from datetime import timedelta
    from engine.services.tick_trading_loop import process_tick_based_trading
    
    print("\n" + "="*60)
    print("🔄 PROCESANDO TODOS LOS SÍMBOLOS ACTIVOS")
    print("="*60)
    
    # Obtener todos los símbolos con ticks en las últimas 24 horas
    since = timezone.now() - timedelta(hours=24)
    symbols = Tick.objects.filter(timestamp__gte=since).values_list('symbol', flat=True).distinct()
    
    print(f"📊 Símbolos encontrados: {list(symbols)}")
    
    results = {}
    for symbol in symbols:
        try:
            print(f"\n🔍 Analizando {symbol}...")
            result = process_tick_based_trading(symbol)
            
            if result and result.get('status') == 'executed':
                print(f"  ✅ ENTRADA EJECUTADA en {symbol}!")
                print(f"  📊 Señal: {result.get('signal', {})}")
            elif result:
                print(f"  ⏸️  {symbol}: {result.get('status')} - {result.get('reason', '')}")
            
            results[symbol] = result
        except Exception as e:
            print(f"  ❌ Error en {symbol}: {e}")
            results[symbol] = {'status': 'error', 'error': str(e)}
    
    print("\n" + "="*60)
    print(f"✅ Procesados {len(symbols)} símbolos")
    print("="*60 + "\n")
    
    return {
        'processed': len(symbols),
        'symbols': list(symbols),
        'results': results
    }


@shared_task
def check_pending_contracts_task(max_age_minutes: int = 5):
    """Tarea periódica: verifica y actualiza contratos pendientes/activos.
    Replica la lógica del comando de management para evitar operaciones colgadas.
    """
    from datetime import timedelta
    from decimal import Decimal
    from monitoring.models import OrderAudit
    from connectors.deriv_client import DerivClient
    from trading_bot.models import DerivAPIConfig

    try:
        config = DerivAPIConfig.objects.filter(is_active=True).only('api_token', 'is_demo', 'app_id').first()
        if not config:
            return {'ok': False, 'error': 'no_api_config'}
        client = DerivClient(api_token=config.api_token, is_demo=config.is_demo, app_id=config.app_id)
        if not client.authenticate():
            return {'ok': False, 'error': 'auth_failed'}

        updated = expired = errors = 0
        cutoff = timezone.now() - timedelta(minutes=max_age_minutes)
        pending_trades = OrderAudit.objects.filter(status__in=['pending', 'active'], timestamp__lt=cutoff).order_by('timestamp')

        # Auto-expirar muy antiguos (> 2h)
        very_old_cutoff = timezone.now() - timedelta(hours=2)
        very_old = OrderAudit.objects.filter(status__in=['pending', 'active'], timestamp__lt=very_old_cutoff)
        for t in very_old:
            try:
                t.status = 'lost'
                t.pnl = -Decimal(str(t.size or 0))
                if not t.response_payload:
                    t.response_payload = {}
                t.response_payload['auto_expired'] = True
                t.response_payload['auto_expired_at'] = timezone.now().isoformat()
                t.response_payload['reason'] = 'Auto-expired (>2h)'
                t.save()
                expired += 1
            except Exception:
                errors += 1

        for trade in pending_trades:
            try:
                contract_id = None
                if trade.response_payload and isinstance(trade.response_payload, dict):
                    contract_id = (
                        trade.response_payload.get('contract_id') or
                        trade.response_payload.get('order_id') or
                        (trade.response_payload.get('buy', {}).get('contract_id') if isinstance(trade.response_payload.get('buy'), dict) else None)
                    )
                if not contract_id:
                    # Si supera 2h ya se auto-expiró arriba; si no, saltar
                    continue

                info = client.get_open_contract_info(str(contract_id))
                if info.get('error'):
                    err = str(info.get('error')).lower()
                    if any(k in err for k in ['not found', 'expired', 'invalid', 'does not exist', 'contract_id']):
                        trade.status = 'lost'
                        trade.pnl = -Decimal(str(trade.size or 0))
                        if not trade.response_payload:
                            trade.response_payload = {}
                        trade.response_payload['auto_expired'] = True
                        trade.response_payload['auto_expired_at'] = timezone.now().isoformat()
                        trade.response_payload['error'] = info.get('error')
                        trade.save()
                        expired += 1
                    else:
                        errors += 1
                    continue

                if info.get('is_sold', False):
                    status = info.get('status')
                    profit = Decimal(str(info.get('profit', 0)))
                    trade.status = status if status else ('won' if profit > 0 else 'lost')
                    trade.pnl = profit
                    if not trade.response_payload:
                        trade.response_payload = {}
                    trade.response_payload['auto_updated'] = True
                    trade.response_payload['auto_updated_at'] = timezone.now().isoformat()
                    trade.response_payload['contract_info'] = info
                    trade.save()
                    updated += 1
            except Exception:
                errors += 1

        return {'ok': True, 'updated': updated, 'expired': expired, 'errors': errors}
    except Exception as e:
        return {'ok': False, 'error': str(e)}

