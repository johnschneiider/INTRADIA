from __future__ import annotations

from typing import Iterable, List, Optional, Dict, Tuple
from dataclasses import dataclass
import math
import statistics


def ema(values: Iterable[float], period: int) -> List[float]:
    values = list(values)
    if period <= 1 or not values:
        return values
    k = 2 / (period + 1)
    out: List[float] = []
    ema_val = values[0]
    for v in values:
        ema_val = v * k + ema_val * (1 - k)
        out.append(ema_val)
    return out


def sma(values: Iterable[float], period: int) -> List[float]:
    values = list(values)
    if period <= 1:
        return values
    out: List[float] = []
    window_sum = 0.0
    for i, v in enumerate(values):
        window_sum += v
        if i >= period:
            window_sum -= values[i - period]
        if i >= period - 1:
            out.append(window_sum / period)
        else:
            out.append(window_sum / (i + 1))
    return out


def rsi(closes: Iterable[float], period: int = 14) -> List[float]:
    closes = list(closes)
    if len(closes) < 2:
        return [0.0 for _ in closes]
    gains: List[float] = [0.0]
    losses: List[float] = [0.0]
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = sma(gains, period)
    avg_loss = sma(losses, period)
    rsi_vals: List[float] = []
    for g, l in zip(avg_gain, avg_loss):
        if l == 0:
            rsi_vals.append(100.0)
        else:
            rs = g / l
            rsi_vals.append(100 - (100 / (1 + rs)))
    return rsi_vals


def true_range(highs: Iterable[float], lows: Iterable[float], closes: Iterable[float]) -> List[float]:
    highs = list(highs)
    lows = list(lows)
    closes = list(closes)
    tr: List[float] = []
    prev_close = closes[0] if closes else 0.0
    for h, l, c in zip(highs, lows, closes):
        tr.append(max(h - l, abs(h - prev_close), abs(l - prev_close)))
        prev_close = c
    return tr


def atr(highs: Iterable[float], lows: Iterable[float], closes: Iterable[float], period: int = 14) -> List[float]:
    tr = true_range(highs, lows, closes)
    return ema(tr, period)


def detect_engulfing(opens: Iterable[float], closes: Iterable[float]) -> Optional[str]:
    """
    Detecta patrones Engulfing (Envolvente) en velas japonesas.
    
    Un Engulfing es un patrón de 2 velas donde:
    - Engulfing Alcista: La vela anterior es bajista (open > close) y la actual 
      es alcista (open < close), y la segunda envuelve completamente a la primera
    - Engulfing Bajista: La vela anterior es alcista (open < close) y la actual 
      es bajista (open > close), y la segunda envuelve completamente a la primera
    
    Args:
        opens: Lista de precios de apertura
        closes: Lista de precios de cierre
        
    Returns:
        'bullish' si hay engulfing alcista
        'bearish' si hay engulfing bajista  
        None si no hay patrón engulfing
    """
    opens = list(opens)
    closes = list(closes)
    
    if len(opens) < 2 or len(closes) < 2:
        return None
    
    # Últimas dos velas
    open_prev = opens[-2]
    close_prev = closes[-2]
    open_curr = opens[-1]
    close_curr = closes[-1]
    
    # Calcular tamaño de las velas (absoluto)
    body_prev = abs(close_prev - open_prev)
    body_curr = abs(close_curr - open_curr)
    
    # Engulfing Alcista: 
    # - Vela anterior bajista (open_prev > close_prev)
    # - Vela actual alcista (open_curr < close_curr)
    # - La vela actual envuelve completamente a la anterior
    if (open_prev > close_prev and 
        open_curr < close_curr and 
        close_curr > open_prev and 
        open_curr < close_prev and 
        body_curr > body_prev):
        return 'bullish'
    
    # Engulfing Bajista:
    # - Vela anterior alcista (open_prev < close_prev)
    # - Vela actual bajista (open_curr > close_curr)
    # - La vela actual envuelve completamente a la anterior
    if (open_prev < close_prev and 
        open_curr > close_curr and 
        close_curr < open_prev and 
        open_curr > close_prev and 
        body_curr > body_prev):
        return 'bearish'
    
    return None


def macd(closes: Iterable[float], fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> Dict[str, List[float]]:
    """
    Calcula MACD (Moving Average Convergence Divergence).
    
    Args:
        closes: Lista de precios de cierre
        fast_period: Período de la EMA rápida (default: 12)
        slow_period: Período de la EMA lenta (default: 26)
        signal_period: Período de la línea de señal (default: 9)
        
    Returns:
        Diccionario con:
            - 'macd_line': MACD Line = EMA(fast) - EMA(slow)
            - 'signal_line': Signal Line = EMA(MACD Line)
            - 'histogram': Histogram = MACD Line - Signal Line
    """
    closes = list(closes)
    
    if len(closes) < slow_period + signal_period:
        return {
            'macd_line': [0.0] * len(closes),
            'signal_line': [0.0] * len(closes),
            'histogram': [0.0] * len(closes)
        }
    
    # Calcular EMAs
    ema_fast = ema(closes, fast_period)
    ema_slow = ema(closes, slow_period)
    
    # MACD Line
    macd_line = [fast - slow for fast, slow in zip(ema_fast, ema_slow)]
    
    # Signal Line (EMA del MACD)
    signal_line = ema(macd_line, signal_period)
    
    # Histogram
    histogram = [m - s for m, s in zip(macd_line, signal_line)]
    
    return {
        'macd_line': macd_line,
        'signal_line': signal_line,
        'histogram': histogram
    }


def bollinger_bands(closes: Iterable[float], period: int = 20, num_std: float = 2.0) -> Dict[str, List[float]]:
    """
    Calcula las Bandas de Bollinger.
    
    Args:
        closes: Lista de precios de cierre
        period: Período para el cálculo de la SMA (default: 20)
        num_std: Número de desviaciones estándar (default: 2.0)
        
    Returns:
        Diccionario con:
            - 'upper': Banda superior
            - 'middle': Banda media (SMA)
            - 'lower': Banda inferior
    """
    closes = list(closes)
    
    if len(closes) < period:
        return {
            'upper': [0.0] * len(closes),
            'middle': [0.0] * len(closes),
            'lower': [0.0] * len(closes)
        }
    
    # Calcular SMA (middle band)
    middle = sma(closes, period)
    
    # Calcular desviación estándar
    upper = []
    lower = []
    
    for i in range(len(closes)):
        if i < period - 1:
            upper.append(closes[i])
            lower.append(closes[i])
        else:
            # Calcular desviación estándar de los últimos 'period' valores
            window = closes[i - period + 1:i + 1]
            mean = sum(window) / len(window)
            variance = sum((x - mean) ** 2 for x in window) / len(window)
            std_dev = math.sqrt(variance)
            
            upper.append(middle[i] + (num_std * std_dev))
            lower.append(middle[i] - (num_std * std_dev))
    
    return {
        'upper': upper,
        'middle': middle,
        'lower': lower
    }


def stochastic(highs: Iterable[float], lows: Iterable[float], closes: Iterable[float], 
               k_period: int = 14, d_period: int = 3) -> Dict[str, List[float]]:
    """
    Calcula el Oscilador Estocástico (%K y %D).
    
    Args:
        highs: Lista de precios máximos
        lows: Lista de precios mínimos
        closes: Lista de precios de cierre
        k_period: Período para %K (default: 14)
        d_period: Período para %D (default: 3)
        
    Returns:
        Diccionario con:
            - 'k_percent': %K
            - 'd_percent': %D
    """
    highs = list(highs)
    lows = list(lows)
    closes = list(closes)
    
    if len(highs) < k_period or len(lows) < k_period or len(closes) < k_period:
        return {
            'k_percent': [0.0] * len(closes),
            'd_percent': [0.0] * len(closes)
        }
    
    k_percent = []
    
    for i in range(len(closes)):
        if i < k_period - 1:
            k_percent.append(50.0)  # Valor neutral
        else:
            # Encontrar máximo y mínimo en la ventana
            window_highs = highs[i - k_period + 1:i + 1]
            window_lows = lows[i - k_period + 1:i + 1]
            
            highest_high = max(window_highs)
            lowest_low = min(window_lows)
            
            if highest_high == lowest_low:
                k_percent.append(50.0)  # Evitar división por cero
            else:
                k_pct = ((closes[i] - lowest_low) / (highest_high - lowest_low)) * 100
                k_percent.append(k_pct)
    
    # Calcular %D (SMA de %K)
    d_percent = sma(k_percent, d_period)
    
    return {
        'k_percent': k_percent,
        'd_percent': d_percent
    }


@dataclass
class SignalScore:
    """Puntuación de una señal de entrada"""
    total_score: float
    max_score: float
    score_breakdown: Dict[str, float]
    passed: bool
    reason: str


def t_test_winrate_improvement(
    trades_with_filters: List[float],  # Lista de P&L con filtros (1=win, 0=loss)
    trades_without_filters: List[float]  # Lista de P&L sin filtros (1=win, 0=loss)
) -> Dict[str, float]:
    """
    Realiza T-test para verificar si el win rate mejoró estadísticamente.
    
    Args:
        trades_with_filters: Lista de resultados con filtros (1=ganó, 0=perdió)
        trades_without_filters: Lista de resultados sin filtros (1=ganó, 0=perdió)
        
    Returns:
        Diccionario con resultados del T-test
    """
    if len(trades_with_filters) < 10 or len(trades_without_filters) < 10:
        return {
            't_statistic': 0.0,
            'p_value': 1.0,
            'winrate_with': 0.0,
            'winrate_without': 0.0,
            'improvement': 0.0,
            'is_significant': False,
            'error': 'Insufficient data'
        }
    
    # Calcular win rates
    winrate_with = sum(trades_with_filters) / len(trades_with_filters)
    winrate_without = sum(trades_without_filters) / len(trades_without_filters)
    
    # Calcular estadísticas
    mean_with = statistics.mean(trades_with_filters)
    mean_without = statistics.mean(trades_without_filters)
    
    try:
        stdev_with = statistics.stdev(trades_with_filters)
        stdev_without = statistics.stdev(trades_without_filters)
    except:
        stdev_with = 0.0
        stdev_without = 0.0
    
    # T-test
    n_with = len(trades_with_filters)
    n_without = len(trades_without_filters)
    pooled_variance = ((n_with - 1) * stdev_with**2 + (n_without - 1) * stdev_without**2) / (n_with + n_without - 2)
    
    if pooled_variance == 0:
        t_statistic = 0.0
        p_value = 1.0
    else:
        se = math.sqrt(pooled_variance * (1/n_with + 1/n_without))
        t_statistic = (mean_with - mean_without) / se
        
        # Aproximación del p-value
        if abs(t_statistic) > 2.58:
            p_value = 0.01
        elif abs(t_statistic) > 1.96:
            p_value = 0.05
        elif abs(t_statistic) > 1.65:
            p_value = 0.10
        else:
            p_value = 0.50
    
    return {
        't_statistic': t_statistic,
        'p_value': p_value,
        'winrate_with': winrate_with,
        'winrate_without': winrate_without,
        'improvement': winrate_with - winrate_without,
        'is_significant': p_value < 0.05,
        'n_with': n_with,
        'n_without': n_without
    }


@dataclass
class OptimizationWeights:
    """Pesos optimizados para el sistema de puntuación"""
    engulfing: float = 2.0
    macd: float = 2.0
    rsi: float = 1.5
    stochastic: float = 1.0
    bollinger: float = 1.5
    ema: float = 1.0
    volume: float = 0.5
    
    macd_contra: float = -1.0
    rsi_contra: float = -0.5
    stochastic_contra: float = -0.5
