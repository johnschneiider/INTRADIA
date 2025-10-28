"""
Modelo estadístico híbrido para trading basado en análisis de ticks
Combina Mean Reversion y Momentum con detección de condiciones extremas
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from statistics import mean, stdev
import numpy as np

from django.utils import timezone
from market.models import Tick


@dataclass
class StatisticalSignal:
    """Señal generada por el modelo estadístico"""
    direction: str  # 'CALL' o 'PUT'
    confidence: float  # 0-1: Confianza en la señal
    signal_type: str  # 'mean_reversion', 'momentum', 'extreme'
    entry_price: float
    z_score: float  # Desviación desde la media en desviaciones estándar
    mean_price: float
    current_position: float  # Posición actual respecto a la media


class StatisticalStrategy:
    """
    Estrategia estadística híbrida mejorada que combina:
    1. Mean Reversion: Detecta cuando el precio se desvía mucho de su media
    2. Momentum: Detecta tendencias continuas
    3. Extreme Conditions: Detección de condiciones extremas
    4. FILTROS NUEVOS para mejorar win rate:
       - EMA (Exponential Moving Average) para filtrar tendencia
       - RSI para evitar sobrecompra/sobreventa
       - Tick Delta para confirmar momentum real
    """
    
    def __init__(self,
                 ticks_to_analyze: int = 50,
                 lookback_periods: int = 20,
                 z_score_threshold: float = 2.0,
                 momentum_threshold: float = 0.02,
                 ema_period: int = 10,
                 rsi_period: int = 14):
        """
        Inicializar estrategia
        
        Args:
            ticks_to_analyze: Número de ticks totales a analizar
            lookback_periods: Períodos para calcular media y desviación estándar
            z_score_threshold: Umbral para detección de condiciones extremas (desviaciones estándar)
            momentum_threshold: Umbral mínimo para confirmar momentum (%)
            ema_period: Período para EMA
            rsi_period: Período para RSI
        """
        self.ticks_to_analyze = ticks_to_analyze
        self.lookback_periods = lookback_periods
        self.z_score_threshold = z_score_threshold
        self.momentum_threshold = momentum_threshold
        self.ema_period = ema_period
        self.rsi_period = rsi_period
    
    def get_recent_ticks(self, symbol: str, limit: int) -> List[Tick]:
        """Obtener últimos ticks de un símbolo"""
        return list(
            Tick.objects.filter(symbol=symbol)
            .order_by('-timestamp')[:limit]
        )
    
    def calculate_statistics(self, prices: List[float]) -> Dict[str, float]:
        """
        Calcular estadísticas descriptivas de los precios
        
        Returns:
            Diccionario con media, desviación estándar, z-score, etc.
        """
        if len(prices) < 3:
            return {
                'mean': 0.0,
                'stdev': 0.0,
                'current_price': 0.0,
                'z_score': 0.0,
                'percentile': 0.5
            }
        
        # Calcular media y desviación estándar de los períodos más recientes
        recent_prices = prices[-self.lookback_periods:]
        
        try:
            mean_price = mean(recent_prices)
            current_price = prices[-1]
            
            # Solo calcular stdev si hay suficientes valores
            if len(recent_prices) > 1:
                std_dev = stdev(recent_prices)
            else:
                std_dev = 0.0001
            
            # Calcular z-score (cuántas desviaciones estándar está el precio actual)
            if std_dev > 0:
                z_score = (current_price - mean_price) / std_dev
            else:
                z_score = 0.0
            
            # Calcular percentil (posición actual respecto al rango)
            sorted_prices = sorted(recent_prices)
            percentile = sorted_prices.index(current_price) / len(sorted_prices) if sorted_prices else 0.5
            
            return {
                'mean': mean_price,
                'stdev': std_dev,
                'current_price': current_price,
                'z_score': z_score,
                'percentile': percentile
            }
            
        except Exception as e:
            return {
                'mean': 0.0,
                'stdev': 0.0,
                'current_price': prices[-1] if prices else 0.0,
                'z_score': 0.0,
                'percentile': 0.5
            }
    
    def calculate_ema(self, prices: List[float], period: int) -> Optional[float]:
        """
        Calcular Exponential Moving Average
        
        Args:
            prices: Lista de precios
            period: Período de la EMA
            
        Returns:
            Valor de la EMA o None si no hay suficientes datos
        """
        if len(prices) < period:
            return None
        
        # Calcular EMA
        multiplier = 2 / (period + 1)
        ema = mean(prices[:period])  # Primera EMA = SMA
        
        for price in prices[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    def calculate_rsi(self, prices: List[float], period: int) -> Optional[float]:
        """
        Calcular Relative Strength Index
        
        Args:
            prices: Lista de precios
            period: Período del RSI
            
        Returns:
            Valor del RSI (0-100) o None si no hay suficientes datos
        """
        if len(prices) < period + 1:
            return None
        
        # Calcular cambios de precio
        changes = []
        for i in range(len(prices) - period, len(prices)):
            if prices[i] > prices[i-1]:
                changes.append(prices[i] - prices[i-1])
            else:
                changes.append(0)
        
        # Calcular ganancias y pérdidas promedio
        gains = [c for c in changes if c > 0]
        losses = [-c for c in changes if c < 0]
        
        avg_gain = mean(gains) if gains else 0
        avg_loss = mean(losses) if losses else 0.0001  # Evitar división por cero
        
        # Calcular RSI
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def calculate_momentum(self, prices: List[float]) -> Dict[str, float]:
        """
        Calcular momentum (tendencia) del movimiento
        
        Returns:
            Diccionario con dirección, fuerza y confirmación
        """
        if len(prices) < 10:
            return {
                'direction': None,
                'strength': 0.0,
                'confirmed': False
            }
        
        # Analizar últimos 10 ticks vs anteriores 10 ticks
        recent_10 = prices[-10:]
        previous_10 = prices[-20:-10] if len(prices) >= 20 else prices[:10]
        
        try:
            recent_mean = mean(recent_10)
            previous_mean = mean(previous_10)
            
            # Calcular cambio porcentual
            change_pct = abs((recent_mean - previous_mean) / previous_mean) * 100 if previous_mean > 0 else 0.0
            
            # Dirección del momentum
            if recent_mean > previous_mean:
                direction = 'CALL'  # Momentum alcista
            elif recent_mean < previous_mean:
                direction = 'PUT'  # Momentum bajista
            else:
                direction = None
            
            # Confirmar momentum si el cambio supera el umbral
            confirmed = change_pct >= self.momentum_threshold
            
            strength = min(1.0, change_pct / (self.momentum_threshold * 2))
            
            return {
                'direction': direction,
                'strength': strength,
                'confirmed': confirmed,
                'change_pct': change_pct
            }
            
        except Exception as e:
            return {
                'direction': None,
                'strength': 0.0,
                'confirmed': False,
                'change_pct': 0.0
            }
    
    def analyze_symbol(self, symbol: str) -> Optional[StatisticalSignal]:
        """
        Analizar símbolo y generar señal estadística
        
        Args:
            symbol: Símbolo a analizar
            
        Returns:
            StatisticalSignal si hay señal válida
        """
        # Obtener ticks
        ticks = self.get_recent_ticks(symbol, self.ticks_to_analyze)
        
        if len(ticks) < 10:
            return None
        
        # Extraer precios
        prices = [float(tick.price) for tick in reversed(ticks)]
        
        # Calcular estadísticas
        stats = self.calculate_statistics(prices)
        momentum = self.calculate_momentum(prices)
        
        # FILTROS MEJORADOS: EMA y RSI
        ema = self.calculate_ema(prices, self.ema_period)
        rsi = self.calculate_rsi(prices, self.rsi_period)
        
        # Z-score para detectar condiciones extremas
        z_score = abs(stats['z_score'])
        
        # ESTRATEGIA 1: MEAN REVERSION (Condiciones extremas)
        # Si el precio está lejos de la media (|z_score| > threshold), esperar reversión
        if z_score > self.z_score_threshold:
            signal_type = 'mean_reversion'
            
            # Si está MUY por arriba, buscar PUT (reversión a la baja)
            if stats['z_score'] > 0:
                direction = 'PUT'
                confidence = min(0.9, z_score / (self.z_score_threshold * 2))
                
                # FILTRO RSI: No entrar PUT si RSI muy alto (>70 = sobrecomprado)
                if rsi and rsi > 70:
                    print(f"❌ {symbol}: Mean Reversion filtrado (RSI sobrecomprado: {rsi:.1f})")
                    return None
            # Si está MUY por abajo, buscar CALL (reversión al alza)
            else:
                direction = 'CALL'
                confidence = min(0.9, z_score / (self.z_score_threshold * 2))
                
                # FILTRO RSI: No entrar CALL si RSI muy bajo (<30 = sobrevendido)
                if rsi and rsi < 30:
                    print(f"❌ {symbol}: Mean Reversion filtrado (RSI sobrevendido: {rsi:.1f})")
                    return None
            
            # FILTRO EMA: Precio debe estar suficientemente alejado de EMA
            if ema:
                price_diff_pct = abs(stats['current_price'] - ema) / ema * 100
                if price_diff_pct < 0.005:  # Precio muy cerca de EMA (<0.005% de diferencia)
                    print(f"❌ {symbol}: Mean Reversion filtrado (Precio muy cerca de EMA: {price_diff_pct:.4f}%)")
                    return None
            
            print(f"📊 {symbol}: Mean Reversion | Z: {stats['z_score']:.2f} | {direction} | Conf: {confidence:.1%} | RSI: {rsi:.1f if rsi else 'N/A'}")
            
            return StatisticalSignal(
                direction=direction,
                confidence=confidence,
                signal_type=signal_type,
                entry_price=stats['current_price'],
                z_score=stats['z_score'],
                mean_price=stats['mean'],
                current_position=stats['percentile']
            )
        
        # ESTRATEGIA 2: MOMENTUM (Tendencias continuas)
        # Si hay momentum confirmado, seguir la tendencia
        if momentum['confirmed'] and momentum['direction']:
            signal_type = 'momentum'
            direction = momentum['direction']
            confidence = momentum['strength']
            
            # Solo operar si la confianza es suficiente (UMBRAL AUMENTADO a 0.4 = 40%)
            if confidence > 0.4:  # Al menos 40% de confianza (antes 30%)
                
                # FILTRO EMA: Confirmar dirección con EMA
                if ema and direction == 'CALL':
                    # Solo CALL si precio está por encima de EMA
                    if stats['current_price'] < ema * 1.001:  # Margen de 0.1%
                        print(f"❌ {symbol}: Momentum filtrado (CALL debajo de EMA)")
                        return None
                
                elif ema and direction == 'PUT':
                    # Solo PUT si precio está por debajo de EMA
                    if stats['current_price'] > ema * 0.999:  # Margen de 0.1%
                        print(f"❌ {symbol}: Momentum filtrado (PUT encima de EMA)")
                        return None
                
                print(f"📊 {symbol}: Momentum | Cambio: {momentum['change_pct']:.4f}% | {direction} | Conf: {confidence:.1%} | RSI: {rsi:.1f if rsi else 'N/A'}")
                
                return StatisticalSignal(
                    direction=direction,
                    confidence=confidence,
                    signal_type=signal_type,
                    entry_price=stats['current_price'],
                    z_score=stats['z_score'],
                    mean_price=stats['mean'],
                    current_position=stats['percentile']
                )
            else:
                print(f"❌ {symbol}: Momentum insuficiente | Cambio: {momentum['change_pct']:.4f}% | Conf: {confidence:.1%}")
        
        # ESTRATEGIA 3: EXTREME POSITION (Cerca de extremos)
        # Si el precio está en los percentiles extremos (>80% o <20%)
        if stats['percentile'] > 0.8 or stats['percentile'] < 0.2:
            signal_type = 'extreme'
            
            if stats['percentile'] > 0.8:
                # Precio muy alto, buscar PUT
                direction = 'PUT'
                confidence = 0.4
            else:
                # Precio muy bajo, buscar CALL
                direction = 'CALL'
                confidence = 0.4
            
            return StatisticalSignal(
                direction=direction,
                confidence=confidence,
                signal_type=signal_type,
                entry_price=stats['current_price'],
                z_score=stats['z_score'],
                mean_price=stats['mean'],
                current_position=stats['percentile']
            )
        
        # No hay señal clara
        return None
    
    def should_enter_trade(self, signal: StatisticalSignal) -> bool:
        """
        Validar si debe entrar en la operación
        
        Args:
            signal: Señal estadística
            
        Returns:
            True si debe entrar
        """
        if not signal:
            return False
        
        # Validar confianza mínima (UMBRAL AUMENTADO para mejorar win rate)
        if signal.confidence < 0.35:  # Antes: 0.3 (30%), Ahora: 0.35 (35%)
            return False
        
        # Validar dirección
        if signal.direction not in ['CALL', 'PUT']:
            return False
        
        return True
    
    def get_trade_params(self, signal: StatisticalSignal, duration: int = 30) -> Dict[str, Any]:
        """
        Obtener parámetros para la operación
        
        Args:
            signal: Señal estadística
            duration: Duración en segundos (default: 30)
            
        Returns:
            Diccionario con parámetros de la operación
        """
        if not signal:
            return {}
        
        return {
            'direction': signal.direction,
            'entry_price': signal.entry_price,
            'duration': duration,
            'basis': 'stake',
            'amount': 1.0,
            'signal_type': signal.signal_type,
            'confidence': signal.confidence,
            'z_score': signal.z_score
        }

