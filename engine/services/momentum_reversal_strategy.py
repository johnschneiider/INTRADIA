"""
Estrategia de Reversión por Fatiga y Ruptura
Detecta:
1. Fatiga del movimiento (5+ ticks consecutivos + momentum extremo)
2. Ruptura de consolidación (ATR% bajo → alto)
3. Reversión por momentum extremo
4. Divergencia de timeframes
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List, Literal
from decimal import Decimal
import numpy as np

from django.utils import timezone
from market.models import Tick


Direction = Literal['CALL', 'PUT']


@dataclass
class MomentumReversalSignal:
    """Señal generada por la estrategia de reversión"""
    symbol: str
    direction: Direction
    entry_price: Decimal
    confidence: float  # 0..1
    signal_type: str  # 'fatigue_reversal', 'breakout', 'momentum_extreme', 'timeframe_divergence'
    fatigue_count: int = 0
    momentum_extreme: float = 0.0
    atr_ratio: float = 0.0
    divergence_score: float = 0.0


class MomentumReversalStrategy:
    """
    Estrategia que combina:
    - Detección de fatiga del movimiento
    - Ruptura de consolidación
    - Reversión por momentum extremo
    - Divergencia de timeframes
    """
    
    def __init__(self,
                 fatigue_threshold: int = 5,  # Ticks consecutivos para fatiga
                 momentum_extreme_threshold: float = 0.05,  # 0.05% momentum extremo
                 consolidation_breakout_atr_ratio: float = 2.0,  # Duplicación de ATR
                 short_timeframe: int = 15,  # Ticks para timeframe corto
                 long_timeframe: int = 60,  # Ticks para timeframe largo
                 rsi_period: int = 14,  # Período para RSI
                 rsi_extreme_high: float = 75.0,  # RSI sobrecompra
                 rsi_extreme_low: float = 25.0):  # RSI sobreventa
        """
        Inicializar estrategia de reversión
        
        Args:
            fatigue_threshold: Número mínimo de ticks consecutivos para considerar fatiga
            momentum_extreme_threshold: Umbral de momentum extremo (%)
            consolidation_breakout_atr_ratio: Multiplicador de ATR para detectar ruptura
            short_timeframe: Ticks para análisis de corto plazo
            long_timeframe: Ticks para análisis de largo plazo
        """
        self.fatigue_threshold = fatigue_threshold
        self.momentum_extreme_threshold = momentum_extreme_threshold
        self.consolidation_breakout_atr_ratio = consolidation_breakout_atr_ratio
        self.short_timeframe = short_timeframe
        self.long_timeframe = long_timeframe
        self.rsi_period = rsi_period
        self.rsi_extreme_high = rsi_extreme_high
        self.rsi_extreme_low = rsi_extreme_low
    
    def _fetch_ticks(self, symbol: str, limit: int) -> List[Tick]:
        """Obtener últimos ticks de un símbolo"""
        return list(Tick.objects.filter(symbol=symbol).order_by('-timestamp')[:limit])
    
    def _calculate_rsi(self, prices: List[float], period: int = 14) -> Optional[float]:
        """Calcular RSI (Relative Strength Index)"""
        if len(prices) < period + 1:
            return None
        
        deltas = []
        for i in range(1, len(prices)):
            deltas.append(prices[i] - prices[i-1])
        
        gains = [d if d > 0 else 0 for d in deltas[-period:]]
        losses = [-d if d < 0 else 0 for d in deltas[-period:]]
        
        avg_gain = sum(gains) / period if gains else 0
        avg_loss = sum(losses) / period if losses else 0
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _calculate_atr_ratio(self, prices: List[float], period: int = 20) -> float:
        """Calcular ATR% (Average True Range como porcentaje)"""
        if len(prices) < period:
            return 0.0
        
        recent_prices = prices[-period:]
        high = max(recent_prices)
        low = min(recent_prices)
        current = prices[-1]
        
        if current == 0:
            return 0.0
        
        atr_ratio = (high - low) / current
        return float(atr_ratio)
    
    def _detect_fatigue(self, ticks: List[Tick]) -> Optional[dict]:
        """
        Detectar fatiga del movimiento:
        - 5+ ticks consecutivos en una dirección
        - Momentum acumulado alto
        - RSI en zona extrema
        """
        if len(ticks) < self.fatigue_threshold + 5:
            return None
        
        prices = [float(t.price) for t in reversed(ticks[-self.fatigue_threshold-5:])]
        consecutive_up = 0
        consecutive_down = 0
        momentum_accumulated = 0.0
        
        # Contar ticks consecutivos
        for i in range(1, len(prices)):
            diff = prices[i] - prices[i-1]
            if diff > 0:
                consecutive_up += 1
                consecutive_down = 0
                if prices[i-1] > 0:
                    momentum_accumulated += abs(diff / prices[i-1]) * 100
            elif diff < 0:
                consecutive_down += 1
                consecutive_up = 0
                if prices[i-1] > 0:
                    momentum_accumulated += abs(diff / prices[i-1]) * 100
            else:
                consecutive_up = 0
                consecutive_down = 0
        
        # Verificar fatiga
        fatigue_detected = False
        direction = None
        
        if consecutive_up >= self.fatigue_threshold:
            fatigue_detected = True
            direction = 'PUT'  # Reversión hacia abajo
        elif consecutive_down >= self.fatigue_threshold:
            fatigue_detected = True
            direction = 'CALL'  # Reversión hacia arriba
        
        if not fatigue_detected:
            return None
        
        # Calcular RSI
        all_prices = [float(t.price) for t in reversed(ticks[-50:])]
        rsi = self._calculate_rsi(all_prices, self.rsi_period)
        
        # Validar RSI en zona extrema
        if rsi is None:
            return None
        
        if direction == 'PUT' and rsi < self.rsi_extreme_high:
            return None  # No está sobrecomprado suficiente
        
        if direction == 'CALL' and rsi > self.rsi_extreme_low:
            return None  # No está sobrevendido suficiente
        
        # Validar momentum acumulado
        if momentum_accumulated < self.momentum_extreme_threshold:
            return None
        
        return {
            'direction': direction,
            'fatigue_count': max(consecutive_up, consecutive_down),
            'momentum_accumulated': momentum_accumulated,
            'rsi': rsi,
            'confidence': min(1.0, max(0.5, (momentum_accumulated / 0.10) * 0.3 + (abs(rsi - 50) / 50) * 0.7))
        }
    
    def _detect_breakout(self, ticks: List[Tick]) -> Optional[dict]:
        """
        Detectar ruptura de consolidación:
        - ATR% bajo (<0.001%) en últimos N ticks
        - ATR% aumenta 2x+ en tick actual
        - Precio rompe rango reciente
        """
        if len(ticks) < 25:
            return None
        
        prices = [float(t.price) for t in reversed(ticks[-25:])]
        
        # ATR% de los últimos 10 ticks (consolidación)
        atr_consolidation = self._calculate_atr_ratio(prices[-15:-5], period=10)
        
        # ATR% de los últimos 5 ticks (ruptura potencial)
        atr_recent = self._calculate_atr_ratio(prices[-5:], period=5)
        
        # Verificar si hay ruptura
        if atr_consolidation < 0.001 and atr_recent > atr_consolidation * self.consolidation_breakout_atr_ratio:
            # Determinar dirección de la ruptura
            recent_range = prices[-5:]
            consolidation_range = prices[-15:-5]
            
            consolidation_high = max(consolidation_range)
            consolidation_low = min(consolidation_range)
            recent_high = max(recent_range)
            recent_low = min(recent_range)
            
            direction = None
            if recent_high > consolidation_high:
                direction = 'CALL'  # Ruptura hacia arriba
            elif recent_low < consolidation_low:
                direction = 'PUT'  # Ruptura hacia abajo
            
            if direction:
                # Confianza basada en fuerza de la ruptura
                breakout_strength = (atr_recent / max(0.0001, atr_consolidation))
                confidence = min(1.0, max(0.5, breakout_strength / 5.0))
                
                return {
                    'direction': direction,
                    'atr_consolidation': atr_consolidation,
                    'atr_recent': atr_recent,
                    'breakout_strength': breakout_strength,
                    'confidence': confidence
                }
        
        return None
    
    def _detect_momentum_extreme(self, ticks: List[Tick]) -> Optional[dict]:
        """
        Detectar reversión por momentum extremo:
        - Momentum >0.05% (muy alto)
        - 3er tick consecutivo con momentum alto
        - Precio cerca de máximo/mínimo reciente
        """
        if len(ticks) < 35:
            return None
        
        prices = [float(t.price) for t in reversed(ticks[-35:])]
        
        # Calcular momentum de últimos 5 ticks
        recent_momentum = []
        for i in range(len(prices) - 5, len(prices) - 1):
            if prices[i] > 0:
                momentum = ((prices[i+1] - prices[i]) / prices[i]) * 100
                recent_momentum.append(momentum)
        
        if len(recent_momentum) < 3:
            return None
        
        # Contar ticks consecutivos con momentum extremo
        extreme_count = 0
        direction_consistent = None
        
        for momentum in recent_momentum[-3:]:
            if abs(momentum) > self.momentum_extreme_threshold:
                extreme_count += 1
                if direction_consistent is None:
                    direction_consistent = 'CALL' if momentum > 0 else 'PUT'
                elif (direction_consistent == 'CALL' and momentum < 0) or \
                     (direction_consistent == 'PUT' and momentum > 0):
                    direction_consistent = None
                    break
        
        if extreme_count < 3 or direction_consistent is None:
            return None
        
        # Verificar si precio está cerca de extremo reciente
        recent_30_prices = prices[-30:]
        recent_high = max(recent_30_prices)
        recent_low = min(recent_30_prices)
        current_price = prices[-1]
        
        near_extreme = False
        reversal_direction = None
        
        if direction_consistent == 'CALL':
            # Momentum alcista extremo → posible reversión bajista
            if abs(current_price - recent_high) / recent_high < 0.002:  # Dentro de 0.2% del máximo
                near_extreme = True
                reversal_direction = 'PUT'
        else:
            # Momentum bajista extremo → posible reversión alcista
            if abs(current_price - recent_low) / recent_low < 0.002:  # Dentro de 0.2% del mínimo
                near_extreme = True
                reversal_direction = 'CALL'
        
        if not near_extreme:
            return None
        
        # Confianza basada en fuerza del momentum
        avg_momentum = sum([abs(m) for m in recent_momentum[-3:]]) / 3
        confidence = min(1.0, max(0.5, (avg_momentum / 0.10) * 0.8))
        
        return {
            'direction': reversal_direction,
            'momentum_extreme': avg_momentum,
            'extreme_count': extreme_count,
            'confidence': confidence
        }
    
    def _detect_timeframe_divergence(self, ticks: List[Tick]) -> Optional[dict]:
        """
        Detectar divergencia de timeframes:
        - Tendencia larga (60 ticks) vs corta (15 ticks) opuestas
        - Momentum reciente aumentando
        """
        if len(ticks) < self.long_timeframe:
            return None
        
        prices = [float(t.price) for t in reversed(ticks[-self.long_timeframe:])]
        
        # Tendencia de largo plazo
        long_prices = prices[-self.long_timeframe:]
        long_trend = 'CALL' if long_prices[-1] > long_prices[0] else 'PUT'
        
        # Tendencia de corto plazo
        short_prices = prices[-self.short_timeframe:]
        short_trend = 'CALL' if short_prices[-1] > short_prices[0] else 'PUT'
        
        # Si no hay divergencia, no hay señal
        if long_trend == short_trend:
            return None
        
        # Calcular momentum reciente (últimos 5 ticks)
        recent_momentum = []
        for i in range(len(prices) - 5, len(prices) - 1):
            if prices[i] > 0:
                momentum = ((prices[i+1] - prices[i]) / prices[i]) * 100
                recent_momentum.append(momentum)
        
        if not recent_momentum:
            return None
        
        # Verificar si el momentum está aumentando
        momentum_increasing = False
        if len(recent_momentum) >= 2:
            momentum_increasing = abs(recent_momentum[-1]) > abs(recent_momentum[-2])
        
        if not momentum_increasing:
            return None
        
        # Seguir el timeframe corto (más reciente)
        direction = short_trend
        
        # Confianza basada en fuerza de la divergencia y momentum
        divergence_strength = abs(prices[-1] - prices[-self.short_timeframe]) / prices[-self.short_timeframe]
        momentum_strength = abs(recent_momentum[-1])
        
        confidence = min(1.0, max(0.5, (divergence_strength * 100) * 0.5 + (momentum_strength / 0.05) * 0.5))
        
        return {
            'direction': direction,
            'long_trend': long_trend,
            'short_trend': short_trend,
            'momentum_strength': momentum_strength,
            'confidence': confidence
        }
    
    def analyze_symbol(self, symbol: str) -> Optional[MomentumReversalSignal]:
        """
        Analizar símbolo y generar señal de reversión
        
        Returns:
            MomentumReversalSignal si hay señal válida, None si no
        """
        # Obtener suficientes ticks
        ticks = self._fetch_ticks(symbol, max(self.long_timeframe, 50) + 10)
        
        if len(ticks) < self.long_timeframe:
            return None
        
        prices = [float(t.price) for t in reversed(ticks)]
        last_price = Decimal(str(prices[-1]))
        
        signals = []
        
        # 1. Detectar fatiga
        fatigue = self._detect_fatigue(ticks)
        if fatigue:
            signals.append({
                'type': 'fatigue_reversal',
                'direction': fatigue['direction'],
                'confidence': fatigue['confidence'],
                'fatigue_count': fatigue['fatigue_count'],
                'momentum_extreme': fatigue['momentum_accumulated'],
                'weight': 0.30
            })
        
        # 2. Detectar ruptura
        breakout = self._detect_breakout(ticks)
        if breakout:
            signals.append({
                'type': 'breakout',
                'direction': breakout['direction'],
                'confidence': breakout['confidence'],
                'atr_ratio': breakout['atr_recent'],
                'weight': 0.25
            })
        
        # 3. Detectar momentum extremo
        momentum_extreme = self._detect_momentum_extreme(ticks)
        if momentum_extreme:
            signals.append({
                'type': 'momentum_extreme',
                'direction': momentum_extreme['direction'],
                'confidence': momentum_extreme['confidence'],
                'momentum_extreme': momentum_extreme['momentum_extreme'],
                'weight': 0.25
            })
        
        # 4. Detectar divergencia
        divergence = self._detect_timeframe_divergence(ticks)
        if divergence:
            signals.append({
                'type': 'timeframe_divergence',
                'direction': divergence['direction'],
                'confidence': divergence['confidence'],
                'divergence_score': divergence['momentum_strength'],
                'weight': 0.20
            })
        
        if not signals:
            return None
        
        # Calcular confianza ponderada
        total_weighted_confidence = 0.0
        total_weight = 0.0
        
        for sig in signals:
            total_weighted_confidence += sig['confidence'] * sig['weight']
            total_weight += sig['weight']
        
        final_confidence = total_weighted_confidence / total_weight if total_weight > 0 else 0.0
        
        # Si la confianza es muy baja, no generar señal
        if final_confidence < 0.50:
            return None
        
        # Determinar dirección (mayoría)
        direction_counts = {}
        for sig in signals:
            direction_counts[sig['direction']] = direction_counts.get(sig['direction'], 0) + sig['weight']
        
        final_direction = max(direction_counts, key=direction_counts.get)
        
        # Obtener datos del tipo de señal principal
        main_signal = max(signals, key=lambda x: x['confidence'] * x['weight'])
        
        # Calcular ATR% para el signal
        atr_ratio = self._calculate_atr_ratio(prices, period=20)
        
        return MomentumReversalSignal(
            symbol=symbol,
            direction=final_direction,  # type: ignore
            entry_price=last_price,
            confidence=final_confidence,
            signal_type=main_signal['type'],
            fatigue_count=main_signal.get('fatigue_count', 0),
            momentum_extreme=main_signal.get('momentum_extreme', 0.0),
            atr_ratio=atr_ratio,
            divergence_score=main_signal.get('divergence_score', 0.0)
        )

