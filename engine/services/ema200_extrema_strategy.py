from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Literal
from decimal import Decimal
from django.utils import timezone
from market.models import Tick


Direction = Literal['CALL', 'PUT']


@dataclass
class EMAExtremaSignal:
    symbol: str
    direction: Direction
    entry_price: Decimal
    ema200: Decimal
    recent_high: Decimal
    recent_low: Decimal
    confidence: float  # 0..1
    atr_ratio: float


class EMA200ExtremaStrategy:
    def __init__(self, lookback_ticks: int = 200, extrema_window: int = 60, ema_period: int = 200):
        self.lookback_ticks = max(lookback_ticks, 200)
        self.extrema_window = max(extrema_window, 30)
        self.ema_period = max(ema_period, 2)

    def _fetch_ticks(self, symbol: str, limit: int) -> list[Tick]:
        return list(Tick.objects.filter(symbol=symbol).order_by('-timestamp')[:limit])

    def _compute_ema(self, prices: list[float], period: int = 200) -> Optional[float]:
        if len(prices) < period:
            return None
        k = 2.0 / (period + 1.0)
        ema = prices[-period]
        for p in prices[-period+1:]:
            ema = p * k + ema * (1 - k)
        return float(ema)

    def _recent_extrema(self, prices: list[float], window: int) -> tuple[Optional[float], Optional[float]]:
        if len(prices) < window:
            return None, None
        window_slice = prices[-window:]
        return max(window_slice), min(window_slice)

    def analyze_symbol(self, symbol: str) -> Optional[EMAExtremaSignal]:
        # Traer suficientes ticks
        ticks = self._fetch_ticks(symbol, max(self.lookback_ticks, self.extrema_window) + 5)
        if len(ticks) < self.lookback_ticks:
            return None
        prices = [float(t.price) for t in reversed(ticks)]  # cronológico
        last_price = Decimal(str(prices[-1]))

        ema200_val = self._compute_ema(prices, self.ema_period)
        if ema200_val is None:
            return None
        recent_high, recent_low = self._recent_extrema(prices, self.extrema_window)
        if recent_high is None or recent_low is None:
            return None

        # Aproximación de ATR% simple (rango último N / precio actual)
        try:
            last_n = prices[-min(20, len(prices)):]  # 20 últimos
            high_n, low_n = max(last_n), min(last_n)
            atr_ratio = (high_n - low_n) / prices[-1] if prices[-1] > 0 else 0.0
        except Exception:
            atr_ratio = 0.0

        ema200 = Decimal(str(round(ema200_val, 6)))
        recent_high_d = Decimal(str(round(recent_high, 6)))
        recent_low_d = Decimal(str(round(recent_low, 6)))

        direction: Optional[Direction] = None
        confidence = 0.0

        # Reglas:
        # - Si precio < EMA y tendencia bajista (precio debajo y testea máximo reciente), PUT
        # - Si precio > EMA y tendencia alcista (precio encima y testea mínimo reciente), CALL
        price_below = prices[-1] < ema200_val
        price_above = prices[-1] > ema200_val

        # Proximidad a los extremos (dentro de 0.05% del extremo)
        def near(value: float, target: float, tol: float = 0.0018) -> bool:
            return abs(value - target) / max(1e-9, target) <= tol

        if price_below and near(prices[-1], recent_high):
            direction = 'PUT'
        elif price_above and near(prices[-1], recent_low):
            direction = 'CALL'
        else:
            return None

        # Confianza: composición simple de señales
        dist_ema = abs(prices[-1] - ema200_val) / ema200_val
        # Cuanto más lejos de la EMA, más clara la tendencia de fondo
        conf_trend = min(1.0, max(0.0, dist_ema / 0.005))  # 0.5% distancia = confianza 1.0
        # Cercanía al extremo reciente
        if direction == 'PUT':
            dist_ext = abs(prices[-1] - recent_high) / recent_high
        else:
            dist_ext = abs(prices[-1] - recent_low) / recent_low
        conf_ext = 1.0 - min(1.0, dist_ext / 0.0008)  # 0.08% del extremo => 1.0 (más laxo)
        # Volatilidad: penalización más suave
        conf_vol = 1.0 - max(0.0, min(1.0, (atr_ratio - 0.015) / 0.08))

        confidence = max(0.0, min(1.0, 0.4*conf_trend + 0.5*conf_ext + 0.1*conf_vol))

        return EMAExtremaSignal(
            symbol=symbol,
            direction=direction,
            entry_price=last_price,
            ema200=ema200,
            recent_high=recent_high_d,
            recent_low=recent_low_d,
            confidence=confidence,
            atr_ratio=float(atr_ratio)
        )

