"""
Sistema de decisión de entrada con filtros estadísticos avanzados
Incluye: Engulfing, MACD, Bandas de Bollinger, Estocástico, RSI, y sistema de puntuación bayesiana
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Dict, List

from market.models import Zone
from market.indicators import (
    atr, detect_engulfing, macd, bollinger_bands, stochastic, rsi, 
    ema, SignalScore, OptimizationWeights
)


@dataclass
class EntryDecision:
    side: str  # 'buy' or 'sell'
    entry_level: Decimal
    stop_level: Decimal
    tp_level: Optional[Decimal]
    risk_percent: float
    confidence_score: float = 0.0  # Puntuación de confianza (0-1)
    signal_quality: str = 'medium'  # 'high', 'medium', 'low'


def calculate_bayesian_score(
    direction: str,
    engulfing_present: bool,
    engulfing_confirms: bool,
    macd_line: Optional[float],
    signal_line: Optional[float],
    rsi_val: Optional[float],
    stochastic_k: Optional[float],
    stochastic_d: Optional[float],
    bb_position: str,  # 'upper', 'middle', 'lower', 'none'
    current_price: float,
    bb_upper: Optional[float],
    bb_lower: Optional[float],
    ema_value: Optional[float],
    volume_factor: float = 1.0,
    weights: Optional[OptimizationWeights] = None,
    # MEJORA: Añadir filtro de tendencia macro
    ema_200: Optional[float] = None,
    atr_volatility: float = 1.0
) -> SignalScore:
    """
    Calcula puntuación bayesiana combinada con pesos configurables.
    
    Args:
        direction: 'long' o 'short'
        engulfing_present: Si hay patrón engulfing presente
        engulfing_confirms: Si el engulfing confirma la dirección
        macd_line: Valor de MACD line
        signal_line: Valor de Signal line
        rsi_val: Valor de RSI
        stochastic_k: Valor de %K del estocástico
        stochastic_d: Valor de %D del estocástico
        bb_position: Posición respecto a Bollinger Bands
        current_price: Precio actual
        bb_upper: Banda superior de Bollinger
        bb_lower: Banda inferior de Bollinger
        ema_value: Valor de EMA
        volume_factor: Factor de volumen (>1 indica volumen alto)
        weights: Pesos para cada indicador. Si None, usa valores por defecto.
        
    Returns:
        SignalScore con la puntuación total y desglose
    """
    # Usar pesos por defecto si no se especifican
    if weights is None:
        weights = OptimizationWeights()
    
    max_score = (
        weights.engulfing + weights.macd + weights.rsi + weights.stochastic +
        weights.bollinger + weights.ema + weights.volume
    )
    scores = {}
    total_score = 0.0
    
    # 1. ENGULFING (2 puntos si confirma, 0 si contradice, 1 si presente pero neutro)
    if engulfing_present:
        if engulfing_confirms:
            scores['engulfing'] = 2.0
            total_score += 2.0
        else:
            scores['engulfing'] = 0.0  # Contradice la señal
    else:
        scores['engulfing'] = 0.5  # No hay engulfing, neutral
        total_score += 0.5
    
    # 2. MACD (2 puntos si confirma, -1 si contradice, 0.5 si neutral)
    if macd_line is not None and signal_line is not None:
        macd_histogram = macd_line - signal_line
        if direction == 'long':
            if macd_histogram > 0 and macd_line > signal_line:
                scores['macd'] = 2.0
                total_score += 2.0
            elif macd_histogram < 0 and macd_line < signal_line:
                scores['macd'] = -1.0
                total_score -= 1.0
            else:
                scores['macd'] = 0.5
                total_score += 0.5
        else:  # short
            if macd_histogram < 0 and macd_line < signal_line:
                scores['macd'] = 2.0
                total_score += 2.0
            elif macd_histogram > 0 and macd_line > signal_line:
                scores['macd'] = -1.0
                total_score -= 1.0
            else:
                scores['macd'] = 0.5
                total_score += 0.5
    else:
        scores['macd'] = 0.0
    
    # 3. RSI (1.5 puntos si confirma extremos)
    if rsi_val is not None:
        if direction == 'long' and rsi_val < 30:
            scores['rsi'] = 1.5
            total_score += 1.5
        elif direction == 'short' and rsi_val > 70:
            scores['rsi'] = 1.5
            total_score += 1.5
        elif direction == 'long' and rsi_val > 75:
            scores['rsi'] = -0.5
            total_score -= 0.5
        elif direction == 'short' and rsi_val < 25:
            scores['rsi'] = -0.5
            total_score -= 0.5
        else:
            scores['rsi'] = 0.5
            total_score += 0.5
    else:
        scores['rsi'] = 0.0
    
    # 4. Estocástico (1 punto si confirma)
    if stochastic_k is not None and stochastic_d is not None:
        if direction == 'long':
            if stochastic_k < 20 and stochastic_k > stochastic_d:
                scores['stochastic'] = 1.0
                total_score += 1.0
            elif stochastic_k > 80:
                scores['stochastic'] = -0.5
                total_score -= 0.5
            else:
                scores['stochastic'] = 0.25
                total_score += 0.25
        else:  # short
            if stochastic_k > 80 and stochastic_k < stochastic_d:
                scores['stochastic'] = 1.0
                total_score += 1.0
            elif stochastic_k < 20:
                scores['stochastic'] = -0.5
                total_score -= 0.5
            else:
                scores['stochastic'] = 0.25
                total_score += 0.25
    else:
        scores['stochastic'] = 0.0
    
    # 5. Bandas de Bollinger (1.5 puntos si precio está en extremos)
    if bb_position == 'lower' and direction == 'long':
        scores['bollinger'] = 1.5
        total_score += 1.5
    elif bb_position == 'upper' and direction == 'short':
        scores['bollinger'] = 1.5
        total_score += 1.5
    elif bb_position == 'middle':
        scores['bollinger'] = 0.5
        total_score += 0.5
    else:
        scores['bollinger'] = 0.0
    
    # 6. EMA (1 punto si confirma tendencia)
    if ema_value is not None:
        if direction == 'long' and current_price > ema_value * 0.999:
            scores['ema'] = 1.0
            total_score += 1.0
        elif direction == 'short' and current_price < ema_value * 1.001:
            scores['ema'] = 1.0
            total_score += 1.0
        else:
            scores['ema'] = 0.0
    else:
        scores['ema'] = 0.0
    
    # 7. Volumen (0.5 puntos si volumen alto)
    if volume_factor > 1.2:
        scores['volume'] = 0.5
        total_score += 0.5
    elif volume_factor > 0.8:
        scores['volume'] = 0.25
        total_score += 0.25
    else:
        scores['volume'] = 0.0
    
    # Normalizar puntuación negativa a 0
    if total_score < 0:
        total_score = 0.0
    
    # ──────────────────────────────────────────────────────
    # MEJORA CRÍTICA #1: Filtro de tendencia macro (EMA 200)
    # ──────────────────────────────────────────────────────
    # Solo permitir long si precio > EMA200, short si precio < EMA200
    if ema_200 is not None:
        if direction == 'long' and current_price <= ema_200:
            # Entrar long debajo de EMA200: contra-tendencia
            scores['trend_filter'] = -2.0
            total_score -= 2.0
        elif direction == 'short' and current_price >= ema_200:
            # Entrar short encima de EMA200: contra-tendencia
            scores['trend_filter'] = -2.0
            total_score -= 2.0
        else:
            scores['trend_filter'] = 1.0
            total_score += 1.0
    else:
        scores['trend_filter'] = 0.0
    
    # ──────────────────────────────────────────────────────
    # MEJORA CRÍTICA #2: Filtro de volatilidad
    # ──────────────────────────────────────────────────────
    # No operar en condiciones de baja volatilidad
    if atr_volatility < 0.8:
        # Volatilidad < 80% del promedio: momentum débil
        scores['volatility_filter'] = -1.0
        total_score -= 1.0
    else:
        scores['volatility_filter'] = 0.0
    
    # Actualizar max_score para incluir nuevos filtros
    max_score = (
        weights.engulfing + weights.macd + weights.rsi + weights.stochastic +
        weights.bollinger + weights.ema + weights.volume + 1.0  # +1 for trend_filter
    )
    
    # Determinar si pasa (umbral: 5.5 de 10.0, o 55% - MEJORA: reducir trades marginales)
    # Nota: Si prefieres más selectividad, subir a 6.0 (60%)
    passed = total_score >= 5.5
    
    reason = (
        f"Score: {total_score:.1f}/{max_score:.1f} | "
        f"Eng: {scores['engulfing']:.1f} | "
        f"MACD: {scores['macd']:.1f} | "
        f"RSI: {scores['rsi']:.1f} | "
        f"Stoch: {scores['stochastic']:.1f} | "
        f"BB: {scores['bollinger']:.1f} | "
        f"EMA: {scores['ema']:.1f} | "
        f"Vol: {scores['volume']:.1f}"
    )
    
    return SignalScore(
        total_score=total_score,
        max_score=max_score,
        score_breakdown=scores,
        passed=passed,
        reason=reason
    )


def get_bb_position(current_price: float, bb_upper: float, bb_lower: float, bb_middle: float) -> str:
    """Determina la posición del precio relativa a las Bandas de Bollinger"""
    bb_width = bb_upper - bb_lower
    if bb_width == 0:
        return 'middle'
    
    position_from_lower = (current_price - bb_lower) / bb_width
    
    if position_from_lower < 0.2:
        return 'lower'
    elif position_from_lower > 0.8:
        return 'upper'
    else:
        return 'middle'


def decide_entry_after_sweep(
    direction: str, 
    zone: Zone, 
    intraday_highs: List[float],
    intraday_lows: List[float],
    intraday_closes: List[float],
    vol_series: List[float],
    *,
    intraday_opens: Optional[List[float]] = None,
                             rr_min: float = 1.5,
    vol_factor: float = 1.2,
    use_advanced_filters: bool = True
) -> Optional[EntryDecision]:
    """
    Decide entrada después de un sweep con filtros estadísticos avanzados.
    
    Args:
        direction: 'long' o 'short'
        zone: Zona de liquidez
        intraday_highs: Lista de máximos intradiarios
        intraday_lows: Lista de mínimos intradiarios
        intraday_closes: Lista de cierres intradiarios
        vol_series: Serie de volúmenes
        intraday_opens: Lista de aperturas intradiarias
        rr_min: Risk/Reward mínimo
        vol_factor: Factor de volumen
        use_advanced_filters: Si usar el sistema de puntuación bayesiana
        
    Returns:
        EntryDecision si cumple todos los filtros
    """
    if not intraday_highs or not intraday_lows or not intraday_closes:
        return None
    
    # Calcular ATR
    atr_val_series = atr(intraday_highs, intraday_lows, intraday_closes, period=14)
    if not atr_val_series or len(atr_val_series) == 0:
        return None
    atr_val = atr_val_series[-1]
    current_price = intraday_closes[-1]
    
    # PRE-CÁLCULOS DE INDICADORES
    engulfing_present = False
    engulfing_confirms = False
    macd_line = None
    signal_line = None
    rsi_val = None
    stochastic_k = None
    stochastic_d = None
    bb_upper = None
    bb_lower = None
    bb_middle = None
    bb_position = 'none'
    ema_value = None
    volume_factor = 1.0
    
    # MEJORA: Añadir indicadores macro
    ema_200_value = None
    atr_volatility_factor = 1.0
    
    # 1. ENGULFING
    if intraday_opens and len(intraday_opens) >= 2:
        engulfing_pattern = detect_engulfing(intraday_opens, intraday_closes)
        if engulfing_pattern:
            engulfing_present = True
            if direction == 'long' and engulfing_pattern == 'bullish':
                engulfing_confirms = True
            elif direction == 'short' and engulfing_pattern == 'bearish':
                engulfing_confirms = True
    
    # 2. MACD
    if len(intraday_closes) >= 35:  # Necesitamos al menos 35 períodos para MACD
        macd_data = macd(intraday_closes)
        if macd_data and macd_data['macd_line'] and macd_data['signal_line']:
            macd_line = macd_data['macd_line'][-1]
            signal_line = macd_data['signal_line'][-1]
    
    # 3. RSI
    if len(intraday_closes) >= 15:
        rsi_vals = rsi(intraday_closes)
        if rsi_vals:
            rsi_val = rsi_vals[-1]
    
    # 4. Estocástico
    if len(intraday_highs) >= 14 and len(intraday_lows) >= 14:
        stoch_data = stochastic(intraday_highs, intraday_lows, intraday_closes)
        if stoch_data:
            stochastic_k = stoch_data['k_percent'][-1]
            stochastic_d = stoch_data['d_percent'][-1]
    
    # 5. Bandas de Bollinger
    if len(intraday_closes) >= 20:
        bb_data = bollinger_bands(intraday_closes)
        if bb_data and bb_data['upper'] and bb_data['lower']:
            bb_upper = bb_data['upper'][-1]
            bb_lower = bb_data['lower'][-1]
            bb_middle = bb_data['middle'][-1]
            bb_position = get_bb_position(current_price, bb_upper, bb_lower, bb_middle)
    
    # 6. EMA
    if len(intraday_closes) >= 10:
        ema_vals = ema(intraday_closes, 10)
        if ema_vals:
            ema_value = ema_vals[-1]
    
    # 7. Volumen
    if vol_series and len(vol_series) >= 20:
        vol_mean = sum(vol_series[-20:]) / 20
        if vol_mean > 0:
            volume_factor = vol_series[-1] / vol_mean
    
    # MEJORA: 8. EMA 200 (tendencia macro)
    if len(intraday_closes) >= 200:
        ema_200_vals = ema(intraday_closes, 200)
        if ema_200_vals:
            ema_200_value = ema_200_vals[-1]
    
    # MEJORA: 9. Factor de volatilidad ATR
    if len(atr_val_series) >= 14:
        atr_mean = sum(atr_val_series[-14:]) / 14
        if atr_mean > 0:
            atr_volatility_factor = atr_val / atr_mean
    
    # SISTEMA DE PUNTUACIÓN BAYESIANA
    if use_advanced_filters:
        signal_score = calculate_bayesian_score(
            direction=direction,
            engulfing_present=engulfing_present,
            engulfing_confirms=engulfing_confirms,
            macd_line=macd_line,
            signal_line=signal_line,
            rsi_val=rsi_val,
            stochastic_k=stochastic_k,
            stochastic_d=stochastic_d,
            bb_position=bb_position,
            current_price=current_price,
            bb_upper=bb_upper,
            bb_lower=bb_lower,
            ema_value=ema_value,
            volume_factor=volume_factor,
            ema_200=ema_200_value,
            atr_volatility=atr_volatility_factor
        )
        
        # Si no pasa el umbral de puntuación, rechazar
        if not signal_score.passed:
            return None
        
        confidence_score = signal_score.total_score / signal_score.max_score
        
        # Determinar calidad de señal
        if confidence_score >= 0.7:
            signal_quality = 'high'
        elif confidence_score >= 0.5:
            signal_quality = 'medium'
        else:
            signal_quality = 'low'
    else:
        confidence_score = 0.5
        signal_quality = 'medium'
    
    # CÁLCULOS DE NIVELES DE PRECIO
    entry_offset = min(0.3 * atr_val, 0.25 * float(zone.zone_height))
    zone_low = float(zone.zone_low)
    zone_high = float(zone.zone_high)
    zone_height = float(zone.zone_height)

    if direction == 'long':
        entry_level = Decimal(str(zone_low + entry_offset))
        risk_distance = max(0.5 * atr_val, 0.1 * zone_height)
        stop_level = Decimal(str(zone_low - risk_distance))
        tp_level = Decimal(str(float(entry_level) + rr_min * risk_distance))
        
        return EntryDecision(
            side='buy',
            entry_level=entry_level,
            stop_level=stop_level,
            tp_level=tp_level,
            risk_percent=0.5,
            confidence_score=confidence_score,
            signal_quality=signal_quality
        )
    else:  # short
        entry_level = Decimal(str(zone_high - entry_offset))
        risk_distance = max(0.5 * atr_val, 0.1 * zone_height)
        stop_level = Decimal(str(zone_high + risk_distance))
        tp_level = Decimal(str(float(entry_level) - rr_min * risk_distance))
        
        return EntryDecision(
            side='sell',
            entry_level=entry_level,
            stop_level=stop_level,
            tp_level=tp_level,
            risk_percent=0.5,
            confidence_score=confidence_score,
            signal_quality=signal_quality
        )
