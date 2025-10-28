"""
Estrategia basada en análisis de ticks en tiempo real
Objetivo: Detectar tendencia y fuerza del movimiento para operar en CALL/PUT
"""

from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, List, Dict, Any

from django.utils import timezone
from market.models import Tick


@dataclass
class TrendSignal:
    """Señal de trading basada en análisis de ticks"""
    direction: str  # 'CALL' o 'PUT'
    strength: float  # Fuerza del movimiento (0-1)
    entry_price: float  # Precio actual
    ticks_analyzed: int  # Cantidad de ticks analizados
    upward_ticks_pct: float  # Porcentaje de ticks alcistas
    force_pct: float  # Porcentaje de fuerza calculado


class TickBasedStrategy:
    """Estrategia basada en análisis de ticks en tiempo real"""
    
    def __init__(self,
                 ticks_to_analyze: int = 50,
                 trend_threshold_pct: float = 65.0,
                 force_threshold_pct: float = 0.15):
        """
        Inicializar estrategia
        
        Args:
            ticks_to_analyze: Número de ticks a analizar (default: 50)
            trend_threshold_pct: Porcentaje mínimo para confirmar tendencia (default: 65%)
            force_threshold_pct: Umbral de fuerza en porcentaje (default: 0.15%)
        """
        self.ticks_to_analyze = ticks_to_analyze
        self.trend_threshold_pct = trend_threshold_pct
        self.force_threshold_pct = force_threshold_pct
    
    def get_recent_ticks(self, symbol: str, limit: int) -> List[Tick]:
        """
        Obtener últimos ticks de un símbolo
        
        Args:
            symbol: Símbolo a analizar
            limit: Número máximo de ticks
            
        Returns:
            Lista de ticks ordenados por timestamp
        """
        return list(
            Tick.objects.filter(symbol=symbol)
            .order_by('-timestamp')[:limit]
        )
    
    def calculate_trend_strength(self, ticks: List[Tick]) -> Dict[str, Any]:
        """
        Calcular tendencia y fuerza del movimiento
        
        Args:
            ticks: Lista de ticks (ordenados del más antiguo al más reciente)
            
        Returns:
            Diccionario con estadísticas de tendencia
        """
        if len(ticks) < 2:
            return {
                'direction': None,
                'strength': 0.0,
                'upward_ticks': 0,
                'downward_ticks': 0,
                'upward_pct': 0.0,
                'force_pct': 0.0
            }
        
        # Invertir lista para tener del más antiguo al más reciente
        ticks = list(reversed(ticks))
        
        upward_count = 0
        downward_count = 0
        price_differences = []
        
        current_price = float(ticks[0].price)
        
        for i in range(1, len(ticks)):
            prev_price = float(ticks[i-1].price)
            curr_price = float(ticks[i].price)
            
            # Contar ticks alcistas y bajistas
            if curr_price > prev_price:
                upward_count += 1
            elif curr_price < prev_price:
                downward_count += 1
            
            # Calcular diferencia porcentual
            if prev_price > 0:
                diff_pct = abs((curr_price - prev_price) / prev_price) * 100
                price_differences.append(diff_pct)
        
        total_moves = upward_count + downward_count
        upward_pct = (upward_count / total_moves * 100) if total_moves > 0 else 0.0
        
        # Calcular fuerza promedio en porcentaje
        force_pct = (sum(price_differences) / len(price_differences)) if price_differences else 0.0
        
        # DIFERENCIA: Fuerza va de 0.006% a 0.06%, necesitamos umbral de 0.01-0.05%
        # El umbral force_threshold_pct=0.05 significa 0.05% de movimiento promedio
        
        # Determinar dirección
        direction = None
        if upward_pct >= self.trend_threshold_pct:
            direction = 'CALL'  # Tendencia alcista
        elif upward_pct <= (100 - self.trend_threshold_pct):
            direction = 'PUT'  # Tendencia bajista
        
        # Calcular fuerza normalizada (0-1)
        # Consideramos fuerte si el movimiento promedio es significativo
        strength = min(1.0, force_pct / self.force_threshold_pct)
        
        return {
            'direction': direction,
            'strength': strength,
            'upward_ticks': upward_count,
            'downward_ticks': downward_count,
            'total_ticks': total_moves,
            'upward_pct': upward_pct,
            'force_pct': force_pct,
            'current_price': current_price
        }
    
    def analyze_symbol(self, symbol: str) -> Optional[TrendSignal]:
        """
        Analizar símbolo y generar señal de trading
        
        Args:
            symbol: Símbolo a analizar
            
        Returns:
            TrendSignal si hay señal válida, None si no
        """
        # Obtener últimos ticks
        ticks = self.get_recent_ticks(symbol, self.ticks_to_analyze)
        
        if len(ticks) < 2:
            return None
        
        # Calcular tendencia y fuerza
        trend_data = self.calculate_trend_strength(ticks)
        
        # Si no hay dirección clara, no hay señal
        if not trend_data['direction']:
            print(f"❌ {symbol}: Sin dirección clara (Up: {trend_data['upward_pct']:.1f}%, Down: {100-trend_data['upward_pct']:.1f}%)")
            return None
        
        # Validar que la fuerza supere el umbral
        print(f"✓ {symbol}: {trend_data['direction']} | Fuerza: {trend_data['force_pct']:.6f}% (umbral: {self.force_threshold_pct}%)")
        if trend_data['force_pct'] < self.force_threshold_pct:
            print(f"  ❌ Fuerza insuficiente")
            return None
        else:
            print(f"  ✅ FUERZA OK - SEÑAL GENERADA!")
        
        # Crear señal
        signal = TrendSignal(
            direction=trend_data['direction'],
            strength=trend_data['strength'],
            entry_price=trend_data['current_price'],
            ticks_analyzed=len(ticks),
            upward_ticks_pct=trend_data['upward_pct'],
            force_pct=trend_data['force_pct']
        )
        
        return signal
    
    def should_enter_trade(self, signal: TrendSignal) -> bool:
        """
        Decidir si entrar en la operación
        
        Args:
            signal: Señal de trading
            
        Returns:
            True si debe entrar, False si no
        """
        if not signal:
            return False
        
        # Validar que la fuerza sea suficiente
        if signal.force_pct < self.force_threshold_pct:
            return False
        
        # Validar dirección
        if signal.direction not in ['CALL', 'PUT']:
            return False
        
        # VALIDACIÓN ADICIONAL: Verificar que la tendencia sea clara (>60%)
        # No operar en rangos cercanos al 50% (mucho ruido)
        if 48.0 <= signal.upward_ticks_pct <= 52.0:
            return False
        
        # VALIDACIÓN ADICIONAL: Fuerza mínima calibrada a datos reales
        if signal.force_pct < 0.0005:  # Mínimo 0.0005% de fuerza realista
            return False
        
        return True
    
    def get_trade_params(self, signal: TrendSignal, duration: int = 60) -> Dict[str, Any]:
        """
        Obtener parámetros para la operación
        
        Args:
            signal: Señal de trading
            duration: Duración en segundos (default: 60)
            
        Returns:
            Diccionario con parámetros de la operación
        """
        if not signal:
            return {}
        
        return {
            'direction': signal.direction,
            'entry_price': signal.entry_price,
            'duration': duration,
            'basis': 'stake',  # Para Deriv binary options
            'amount': 1.0  # Monto por defecto
        }

