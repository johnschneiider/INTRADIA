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
from monitoring.models import OrderAudit


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
    # Campos extendidos para filtros avanzados
    confluence_score: int = 0
    atr_ratio: float = 0.0
    up_streak: int = 0
    down_streak: int = 0


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
                 z_score_threshold: float = 2.5,  # Más estricto para reducir trades
                 momentum_threshold: float = 0.020,  # Más estricto para reducir trades
                 ema_period: int = 10,
                 rsi_period: int = 14,
                 atr_min_ratio: float = 0.0005,
                 trend_analysis_period: int = 60,  # ~60 ticks = ~1 hora
                 enable_symbol_filtering: bool = True,  # Filtrar símbolos con bajo win rate
                 min_trades_for_filtering: int = 5,  # Mínimo de trades antes de filtrar
                 min_win_rate_threshold: float = 0.30,  # Win rate mínimo (30%)
                 adaptive_params: Optional[Any] = None):  # Parámetros adaptativos
        """
        Inicializar estrategia
        
        Args:
            ticks_to_analyze: Número de ticks totales a analizar
            lookback_periods: Períodos para calcular media y desviación estándar
            z_score_threshold: Umbral para detección de condiciones extremas (desviaciones estándar)
            momentum_threshold: Umbral mínimo para confirmar momentum (%)
            ema_period: Período para EMA
            rsi_period: Período para RSI
            trend_analysis_period: Número de ticks para analizar tendencia principal (default: 60 = ~1 hora)
        """
        self.ticks_to_analyze = ticks_to_analyze
        self.lookback_periods = lookback_periods
        self.base_z_score_threshold = z_score_threshold
        self.base_momentum_threshold = momentum_threshold
        self.ema_period = ema_period
        self.rsi_period = rsi_period
        self.atr_min_ratio = atr_min_ratio
        self.trend_analysis_period = trend_analysis_period
        self.enable_symbol_filtering = enable_symbol_filtering
        self.min_trades_for_filtering = min_trades_for_filtering
        self.min_win_rate_threshold = min_win_rate_threshold
        self.adaptive_params = adaptive_params
        
        # Umbrales actuales (se ajustarán dinámicamente)
        self.z_score_threshold = z_score_threshold
        self.momentum_threshold = momentum_threshold
    
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
        
        # Calcular cambios de precio (incluyendo negativos)
        deltas = []
        for i in range(len(prices) - period, len(prices)):
            deltas.append(prices[i] - prices[i-1])

        # Calcular ganancias y pérdidas promedio
        gains = [d for d in deltas if d > 0]
        losses = [-d for d in deltas if d < 0]

        avg_gain = mean(gains) if gains else 0.0
        avg_loss = mean(losses) if losses else 0.0

        # Casos límite
        if avg_gain == 0 and avg_loss == 0:
            return 50.0
        if avg_loss == 0:
            return 100.0
        if avg_gain == 0:
            return 0.0

        # Calcular RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_atr(self, prices: List[float], period: int = 20) -> Optional[float]:
        """ATR simplificado a nivel de ticks: media del rango absoluto de deltas."""
        if len(prices) < period + 1:
            return None
        deltas = [abs(prices[i] - prices[i-1]) for i in range(1, len(prices))]
        window = deltas[-period:]
        return mean(window) if window else None

    def calculate_streaks(self, prices: List[float]) -> Dict[str, int]:
        """Cuenta rachas consecutivas de alzas/bajas en los últimos ~10 ticks."""
        if len(prices) < 3:
            return {'up_streak': 0, 'down_streak': 0}
        up_streak = down_streak = 0
        last_dir = 0
        for i in range(len(prices) - 10 if len(prices) > 10 else 1, len(prices)):
            d = prices[i] - prices[i-1]
            dir_ = 1 if d > 0 else (-1 if d < 0 else 0)
            if dir_ == 1:
                up_streak = (up_streak + 1) if last_dir == 1 else 1
                down_streak = 0
            elif dir_ == -1:
                down_streak = (down_streak + 1) if last_dir == -1 else 1
                up_streak = 0
            last_dir = dir_
        return {'up_streak': up_streak, 'down_streak': down_streak}
    
    def detect_main_trend(self, symbol: str) -> Optional[str]:
        """
        Detectar tendencia principal del instrumento
        
        Analiza los últimos N ticks (por defecto ~60 ticks = ~1 hora)
        para determinar si la tendencia general es ALCISTA o BAJISTA.
        
        Args:
            symbol: Símbolo a analizar
            
        Returns:
            'CALL' si tendencia es alcista (precio subiendo)
            'PUT' si tendencia es bajista (precio bajando)
            None si no hay suficientes datos o tendencia neutral
        """
        try:
            # Obtener más ticks para análisis de tendencia (últimas 1-2 horas)
            trend_ticks = self.get_recent_ticks(symbol, self.trend_analysis_period)
            
            if len(trend_ticks) < 10:  # Mínimo necesario para análisis
                return None
            
            # Extraer precios
            trend_prices = [float(tick.price) for tick in reversed(trend_ticks)]
            
            if len(trend_prices) < 10:
                return None
            
            # Calcular promedio móvil simple de largo plazo
            # Usar primeros 30 ticks como referencia inicial
            initial_period = min(30, len(trend_prices) // 2)
            initial_avg = mean(trend_prices[:initial_period])
            
            # Calcular promedio de últimos 30 ticks
            recent_period = min(30, len(trend_prices))
            recent_avg = mean(trend_prices[-recent_period:])
            
            # Precio actual
            current_price = trend_prices[-1]
            
            # Calcular cambio porcentual de la tendencia
            trend_change_pct = ((recent_avg - initial_avg) / initial_avg * 100) if initial_avg > 0 else 0
            
            # Determinar tendencia principal
            # Si el promedio reciente está por encima del inicial y el precio está por encima del promedio reciente → ALCISTA
            # Si el promedio reciente está por debajo del inicial y el precio está por debajo del promedio reciente → BAJISTA
            # Si hay conflicto o cambio pequeño → Neutral
            
            min_trend_strength = 0.05  # 0.05% mínimo para considerar tendencia clara
            
            if recent_avg > initial_avg * (1 + min_trend_strength / 100) and current_price >= recent_avg * 0.999:
                # Tendencia alcista clara
                return 'CALL'
            elif recent_avg < initial_avg * (1 - min_trend_strength / 100) and current_price <= recent_avg * 1.001:
                # Tendencia bajista clara
                return 'PUT'
            else:
                # Tendencia neutral o conflicto
                return None
                
        except Exception as e:
            print(f"⚠️ Error detectando tendencia principal para {symbol}: {e}")
            return None
    
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
    
    def get_symbol_win_rate(self, symbol: str) -> Optional[float]:
        """
        Obtener win rate histórico de un símbolo
        
        Args:
            symbol: Símbolo a analizar
            
        Returns:
            Win rate (0-1) o None si no hay suficientes datos
        """
        try:
            trades = OrderAudit.objects.filter(
                symbol=symbol,
                accepted=True,
                status__in=['won', 'lost']
            )
            
            total = trades.count()
            if total < self.min_trades_for_filtering:
                return None  # No hay suficientes trades para evaluar
            
            won = trades.filter(status='won').count()
            win_rate = won / total if total > 0 else 0.0
            
            return win_rate
        except Exception:
            return None
    
    def should_skip_symbol(self, symbol: str) -> bool:
        """
        Determinar si un símbolo debe ser excluido por bajo win rate
        
        Args:
            symbol: Símbolo a verificar
            
        Returns:
            True si debe ser excluido, False si puede operarse
        """
        if not self.enable_symbol_filtering:
            return False
        
        win_rate = self.get_symbol_win_rate(symbol)
        if win_rate is None:
            return False  # No hay suficientes datos, permitir trading
        
        if win_rate < self.min_win_rate_threshold:
            print(f"🚫 {symbol}: Excluido por bajo win rate ({win_rate*100:.1f}% < {self.min_win_rate_threshold*100:.1f}%)")
            return True
        
        return False
    
    def update_adaptive_parameters(self, adaptive_params):
        """Actualizar parámetros adaptativos dinámicamente"""
        self.adaptive_params = adaptive_params
        if adaptive_params:
            # Usar umbrales ajustados desde adaptive_params
            self.z_score_threshold = adaptive_params.z_score_threshold
            self.momentum_threshold = adaptive_params.momentum_threshold
        else:
            # Usar umbrales base
            self.z_score_threshold = self.base_z_score_threshold
            self.momentum_threshold = self.base_momentum_threshold
    
    def analyze_symbol(self, symbol: str) -> Optional[StatisticalSignal]:
        """
        Analizar símbolo y generar señal estadística
        
        Args:
            symbol: Símbolo a analizar
            
        Returns:
            StatisticalSignal si hay señal válida
        """
        # 🚫 FILTRO DE SÍMBOLOS CON BAJO WIN RATE (NUEVO)
        if self.should_skip_symbol(symbol):
            print(f"🚫 {symbol}: Excluido por bajo win rate")
            return None
        
        # Obtener ticks
        ticks = self.get_recent_ticks(symbol, self.ticks_to_analyze)
        
        if len(ticks) < 10:
            print(f"⚠️ {symbol}: Insuficientes ticks ({len(ticks)} < 10)")
            return None
        
        # Extraer precios
        prices = [float(tick.price) for tick in reversed(ticks)]
        
        # Calcular estadísticas
        stats = self.calculate_statistics(prices)
        momentum = self.calculate_momentum(prices)
        
        # FILTROS MEJORADOS: EMA, RSI, ATR, rachas de ticks
        ema = self.calculate_ema(prices, self.ema_period)
        rsi = self.calculate_rsi(prices, self.rsi_period)
        rsi_prev = None
        if len(prices) >= self.rsi_period + 2:
            rsi_prev = self.calculate_rsi(prices[:-1], self.rsi_period)
        atr = self.calculate_atr(prices, period=min(20, len(prices)-1))
        atr_ratio = (atr / stats['current_price']) if (atr and stats['current_price'] > 0) else 0.0
        streaks = self.calculate_streaks(prices)
        up_streak, down_streak = streaks['up_streak'], streaks['down_streak']

        # Gate: volatilidad mínima (ELIMINADO - permitir todos los símbolos)
        # Se eliminó el filtro de volatilidad mínima para permitir más operaciones
        # Los símbolos con muy baja volatilidad se filtrarán naturalmente por otros criterios
        # (Z-Score, Momentum, tendencia principal, etc.)
        
        # 🎯 DETECCIÓN DE TENDENCIA PRINCIPAL (NUEVO)
        # Antes de generar señales, verificar la tendencia principal
        main_trend = self.detect_main_trend(symbol)
        
        if main_trend:
            print(f"📈 {symbol}: Tendencia Principal = {main_trend} (últimas ~{self.trend_analysis_period} ticks)")
        else:
            print(f"📊 {symbol}: Tendencia Principal = NEUTRAL (insuficientes datos o conflicto)")
        
        # Obtener confidence mínima adaptativa si está disponible
        # Usar parámetros adaptativos si están disponibles, sino usar defaults
        if self.adaptive_params:
            self.z_score_threshold = self.adaptive_params.z_score_threshold
            self.momentum_threshold = self.adaptive_params.momentum_threshold
            confidence_minimum = self.adaptive_params.confidence_minimum
        else:
            # Usar umbrales base si no hay parámetros adaptativos
            self.z_score_threshold = self.base_z_score_threshold
            self.momentum_threshold = self.base_momentum_threshold
            confidence_minimum = 0.6  # Más estricto para reducir trades
        
        # Z-score para detectar condiciones extremas
        z_score = abs(stats['z_score'])
        
        # DEBUG: Mostrar estadísticas básicas
        print(f"🔍 {symbol}: Z-Score={z_score:.2f} (umbral: {self.z_score_threshold:.2f}), Momentum={momentum['strength']:.4f}% (umbral: {self.momentum_threshold:.4f}%), ATR%={atr_ratio*100:.4f}%")
        
        # ESTRATEGIA 1: MEAN REVERSION (Condiciones extremas)
        # Si el precio está lejos de la media (|z_score| > threshold), esperar reversión
        if z_score > self.z_score_threshold:
            signal_type = 'mean_reversion'
            
            # Si está MUY por arriba, buscar PUT (reversión a la baja)
            if stats['z_score'] > 0:
                direction = 'PUT'
                confidence = min(0.9, z_score / (self.z_score_threshold * 2))
                
                # 🎯 FILTRO DE TENDENCIA PRINCIPAL (NUEVO)
                # Si la tendencia principal es alcista, evitar PUTs (operar solo a favor)
                if main_trend == 'CALL':
                    print(f"❌ {symbol}: Mean Reversion PUT filtrado (Tendencia principal es ALCISTA - operar solo CALL)")
                    return None
                
                # FILTRO RSI: Más relajado para permitir más señales
                if rsi and rsi > 80:  # Solo filtrar extremos (80+)
                    print(f"❌ {symbol}: Mean Reversion filtrado (RSI extremo: {rsi:.1f})")
                    return None
            # Si está MUY por abajo, buscar CALL (reversión al alza)
            else:
                direction = 'CALL'
                confidence = min(0.9, z_score / (self.z_score_threshold * 2))
                
                # Aplicar filtro de confidence mínima adaptativa
                if confidence < confidence_minimum:
                    print(f"❌ {symbol}: Mean Reversion PUT filtrado (Confidence {confidence:.2f} < mínimo {confidence_minimum:.2f})")
                    return None
                
                # 🎯 FILTRO DE TENDENCIA PRINCIPAL (NUEVO)
                # Si la tendencia principal es bajista, evitar CALLs (operar solo a favor)
                if main_trend == 'PUT':
                    print(f"❌ {symbol}: Mean Reversion CALL filtrado (Tendencia principal es BAJISTA - operar solo PUT)")
                    return None
                
                # FILTRO RSI: Más relajado para permitir más señales
                if rsi and rsi < 20:  # Solo filtrar extremos (20-)
                    print(f"❌ {symbol}: Mean Reversion filtrado (RSI extremo: {rsi:.1f})")
                    return None
            
            # FILTRO EMA: Más relajado (solo filtrar si está muy cerca)
            if ema:
                price_diff_pct = abs(stats['current_price'] - ema) / ema * 100
                if price_diff_pct < 0.0001:  # Más relajado: 0.0001% en lugar de 0.001%
                    print(f"❌ {symbol}: Mean Reversion filtrado (Precio muy cerca de EMA: {price_diff_pct:.4f}%)")
                    return None

            # Micro‑tendencia: remover filtro de racha para Mean Reversion
            # Permitir señales aunque la racha sea corta
            # if max(up_streak, down_streak) < 2:
            #     return None
            
            # Confluencia de señales
            score = 0
            if z_score > self.z_score_threshold:
                score += 1
            if momentum['confirmed']:
                score += 1
            if stats['percentile'] > 0.8 or stats['percentile'] < 0.2:
                score += 1
            confidence = max(confidence, min(1.0, 0.35 + 0.2 * score))

            print(f"📊 {symbol}: Mean Reversion | Z: {stats['z_score']:.2f} | {direction} | Conf: {confidence:.1%} | Score: {score} | ATR%: {atr_ratio*100:.3f}")
            
            return StatisticalSignal(
                direction=direction,
                confidence=confidence,
                signal_type=signal_type,
                entry_price=stats['current_price'],
                z_score=stats['z_score'],
                mean_price=stats['mean'],
                current_position=stats['percentile'],
                confluence_score=score,
                atr_ratio=atr_ratio,
                up_streak=up_streak,
                down_streak=down_streak
            )
        
        # ESTRATEGIA 2: MOMENTUM (Tendencias continuas)
        # Si hay momentum confirmado, seguir la tendencia
        if momentum['confirmed'] and momentum['direction']:
            signal_type = 'momentum'
            direction = momentum['direction']
            confidence = momentum['strength']
            
            # 🎯 FILTRO DE TENDENCIA PRINCIPAL (NUEVO)
            # Solo operar momentum si está alineado con la tendencia principal
            if main_trend and direction != main_trend:
                print(f"❌ {symbol}: Momentum {direction} filtrado (Tendencia principal es {main_trend} - operar solo a favor)")
                return None
            
            # Solo operar si la confianza inicial es suficiente
            if confidence > 0.35:  # Más estricto para reducir trades
                
                # FILTRO EMA: Confirmar dirección con EMA
                if ema and direction == 'CALL':
                    # Solo CALL si precio está por encima de EMA
                    if stats['current_price'] < ema * 1.000:  # Sin margen adicional
                        print(f"❌ {symbol}: Momentum filtrado (CALL debajo de EMA)")
                        return None
                
                elif ema and direction == 'PUT':
                    # Solo PUT si precio está por debajo de EMA
                    if stats['current_price'] > ema * 1.000:  # Sin margen adicional
                        print(f"❌ {symbol}: Momentum filtrado (PUT encima de EMA)")
                        return None
                
                # RSI debe estar alineado con la dirección del momentum
                if rsi is not None and rsi_prev is not None:
                    if direction == 'CALL' and not (rsi > rsi_prev):
                        return None
                    if direction == 'PUT' and not (rsi < rsi_prev):
                        return None

                # Micro‑confirmación por racha: más relajado
                if direction == 'CALL' and up_streak < 1:
                    return None
                if direction == 'PUT' and down_streak < 1:
                    return None

                # Confluencia de señales (CALCULAR ANTES DE FILTRAR POR CONFIDENCE MÍNIMA)
                score = 0
                if z_score > self.z_score_threshold:
                    score += 1
                if momentum['confirmed']:
                    score += 1
                if stats['percentile'] > 0.8 or stats['percentile'] < 0.2:
                    score += 1
                # Calcular confidence final con score ANTES de filtrar
                confidence = max(confidence, min(1.0, 0.35 + 0.2 * score))

                # AHORA aplicar filtro de confidence mínima adaptativa (DESPUÉS del cálculo del score)
                if confidence < confidence_minimum:
                    print(f"❌ {symbol}: Momentum filtrado (Confidence {confidence:.2f} < mínimo {confidence_minimum:.2f})")
                    return None

                print(f"📊 {symbol}: Momentum | Δ%: {momentum['change_pct']:.4f}% | {direction} | Conf: {confidence:.1%} | Score: {score} | ATR%: {atr_ratio*100:.3f}")
                
                return StatisticalSignal(
                    direction=direction,
                    confidence=confidence,
                    signal_type=signal_type,
                    entry_price=stats['current_price'],
                    z_score=stats['z_score'],
                    mean_price=stats['mean'],
                    current_position=stats['percentile'],
                    confluence_score=score,
                    atr_ratio=atr_ratio,
                    up_streak=up_streak,
                    down_streak=down_streak
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
            
            # Confluencia: solo percentil suma 1; exigir score final en should_enter_trade
            score = 0
            if z_score > self.z_score_threshold:
                score += 1
            if momentum['confirmed']:
                score += 1
            if stats['percentile'] > 0.8 or stats['percentile'] < 0.2:
                score += 1

            return StatisticalSignal(
                direction=direction,
                confidence=confidence,
                signal_type=signal_type,
                entry_price=stats['current_price'],
                z_score=stats['z_score'],
                mean_price=stats['mean'],
                current_position=stats['percentile'],
                confluence_score=score,
                atr_ratio=atr_ratio,
                up_streak=up_streak,
                down_streak=down_streak
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
        
        # Validar confianza mínima (más estricto para menos operaciones)
        if signal.confidence < 0.50:  # Aumentado de 0.25 a 0.50
            return False
        
        # Requerir confluencia mínima
        if getattr(signal, 'confluence_score', 0) < 2:  # Aumentado de 1 a 2
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

