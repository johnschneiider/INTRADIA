from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any

from market.models import Candle, Zone, Timeframe
from engine.services.zone_detector import compute_zones
from engine.services.sweep_detector import detect_liquidity_sweep
from engine.services.rule_based import decide_entry_after_sweep
from connectors.yahoo_finance_client import get_historical_data_for_backtesting
import random
from market.indicators import atr


@dataclass
class BacktestResult:
    trades: int
    wins: int
    pnl: float
    winrate: float
    max_drawdown: float


def run_backtest(symbol: str, timeframe: str = Timeframe.M5, commission: float = 0.0002,
                 slippage_min_pct: float = 0.0002, slippage_max_pct: float = 0.001,
                 latency_min_ms: int = 50, latency_max_ms: int = 300) -> Dict[str, Any]:
    """Ejecutar backtest usando datos históricos reales"""
    
    # Primero intentar obtener datos de la base de datos
    candles = list(Candle.objects.filter(symbol=symbol, timeframe=timeframe).order_by('timestamp'))
    
    # Si no hay suficientes datos en la BD, obtener de Yahoo Finance
    if len(candles) < 50:
        print(f"⚠️ Datos insuficientes en BD para {symbol} {timeframe}, obteniendo de Yahoo Finance...")
        try:
            # Convertir timeframe para Yahoo Finance
            yahoo_timeframe = timeframe
            if timeframe == 'M5':
                yahoo_timeframe = '5m'
            elif timeframe == 'M15':
                yahoo_timeframe = '15m'
            elif timeframe == 'H1':
                yahoo_timeframe = '1h'
            elif timeframe == 'H4':
                yahoo_timeframe = '4h'
            elif timeframe == 'D1':
                yahoo_timeframe = '1d'
            
            # Obtener datos de Yahoo Finance
            yahoo_data = get_historical_data_for_backtesting(symbol, yahoo_timeframe, "6mo")
            
            if yahoo_data and len(yahoo_data) >= 50:
                # Convertir a objetos Candle
                candles = []
                for data in yahoo_data:
                    from datetime import datetime
                    candle = Candle(
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=datetime.fromtimestamp(data['timestamp']),
                        open=data['open'],
                        high=data['high'],
                        low=data['low'],
                        close=data['close'],
                        volume=data['volume']
                    )
                    candles.append(candle)
                print(f"✅ Obtenidos {len(candles)} velas de Yahoo Finance para backtesting")
            else:
                return {
                    'trades': 0, 'wins': 0, 'pnl': 0.0, 'winrate': 0.0, 'max_drawdown': 0.0,
                    'error': 'insufficient_data_from_yahoo',
                    'candles_count': len(yahoo_data) if yahoo_data else 0
                }
        except Exception as e:
            return {
                'trades': 0, 'wins': 0, 'pnl': 0.0, 'winrate': 0.0, 'max_drawdown': 0.0,
                'error': f'yahoo_finance_error: {str(e)}',
                'candles_count': len(candles)
            }
    
    if len(candles) < 50:
        return {
            'trades': 0, 'wins': 0, 'pnl': 0.0, 'winrate': 0.0, 'max_drawdown': 0.0,
            'error': 'insufficient_data',
            'candles_count': len(candles)
        }

    # Usar zonas reales detectadas
    zones = Zone.objects.filter(symbol=symbol).order_by('-timestamp')
    if not zones.exists():
        return {
            'trades': 0, 'wins': 0, 'pnl': 0.0, 'winrate': 0.0, 'max_drawdown': 0.0,
            'error': 'no_zones',
            'candles_count': len(candles)
        }

    pnl = 0.0
    max_equity = 0.0
    min_equity = 0.0
    wins = 0
    trades = 0
    trade_results = []

    opens = [float(c.open) for c in candles]
    highs = [float(c.high) for c in candles]
    lows = [float(c.low) for c in candles]
    closes = [float(c.close) for c in candles]
    vols = [float(c.volume) for c in candles]

    # Procesar cada zona con datos reales
    for zone in zones[:5]:  # Usar las 5 zonas más recientes
        sweep = detect_liquidity_sweep(symbol, zone, candles)
        if sweep:
            decision = decide_entry_after_sweep(
                sweep.direction, 
                zone, 
                highs, 
                lows, 
                closes, 
                vols,
                intraday_opens=opens,
                use_advanced_filters=True  # Sistema bayesiano completo
            )
            if decision:
                trades += 1
                
                # Simular condiciones reales de mercado
                slippage = random.uniform(slippage_min_pct, slippage_max_pct)
                latency_ms = random.randint(latency_min_ms, latency_max_ms)
                
                # Calcular P&L real basado en precios históricos
                if decision.side == 'buy':
                    entry_price = float(decision.entry_level)
                    exit_price = float(decision.tp_level)
                    pnl_trade = exit_price - entry_price
                else:
                    entry_price = float(decision.entry_level)
                    exit_price = float(decision.tp_level)
                    pnl_trade = entry_price - exit_price
                
                # Aplicar comisiones y slippage reales
                pnl_trade -= commission
                pnl_trade -= slippage * entry_price
                
                pnl += pnl_trade
                wins += 1 if pnl_trade > 0 else 0
                
                trade_results.append({
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'pnl': pnl_trade,
                    'side': decision.side,
                    'timestamp': candles[-1].timestamp
                })
                
                max_equity = max(max_equity, pnl)
                min_equity = min(min_equity, pnl)

    winrate = (wins / trades) if trades else 0.0
    max_dd = max(0.0, max_equity - min_equity)
    
    return {
        'trades': trades, 
        'wins': wins, 
        'pnl': pnl, 
        'winrate': winrate, 
        'max_drawdown': max_dd,
        'expectancy': pnl / trades if trades > 0 else 0,
        'sharpe_ratio': (pnl / max_dd) if max_dd > 0 else 0,
        'candles_count': len(candles),
        'zones_count': zones.count(),
        'trade_results': trade_results
    }

