"""
Sistema Adaptativo de Gestión de Filtros durante Drawdowns
Ajusta dinámicamente los umbrales de filtros cuando el rendimiento cae
"""

from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Dict, Any
from datetime import timedelta
from django.utils import timezone
from monitoring.models import OrderAudit


@dataclass
class PerformanceMetrics:
    """Métricas de rendimiento actuales"""
    win_rate_global: float  # Win rate últimas N operaciones
    win_rate_recent: float  # Win rate últimas 10-20 operaciones
    drawdown_pct: float  # Porcentaje de drawdown desde pico
    current_balance: Decimal
    initial_balance: Decimal
    peak_balance: Decimal
    losing_streak: int  # Rachas perdedoras consecutivas
    winning_streak: int  # Rachas ganadoras consecutivas
    total_trades: int
    trades_today: int


@dataclass
class AdaptiveParameters:
    """Parámetros adaptativos ajustados dinámicamente"""
    z_score_threshold: float  # Umbral Z-Score ajustado
    momentum_threshold: float  # Umbral Momentum ajustado
    confidence_minimum: float  # Confidence mínima ajustada
    position_size_multiplier: float  # Multiplicador de tamaño de posición (0.25-1.0)
    is_conservative_mode: bool  # Si está en modo conservador


class AdaptiveFilterManager:
    """
    Gestiona el ajuste dinámico de filtros basado en rendimiento
    
    Sistema Híbrido:
    1. Ajuste dinámico de umbrales (z_score, momentum, confidence)
    2. Reducción de tamaño de posición durante drawdown
    3. Monitoreo continuo de métricas
    4. Recuperación gradual al volver a condiciones normales
    """
    
    def __init__(self,
                 # Umbrales de activación
                 win_rate_threshold: float = 0.52,  # 52%
                 drawdown_threshold: float = 0.05,  # 5%
                 losing_streak_threshold: int = 3,  # 3 pérdidas consecutivas
                 
                 # Parámetros base (normales)
                 base_z_score_threshold: float = 2.5,  # Más estricto
                 base_momentum_threshold: float = 0.020,  # 2.0%
                 base_confidence_minimum: float = 0.6,  # Más estricto
                 
                 # Ajustes durante drawdown
                 z_score_multiplier: float = 1.25,  # Aumentar 25%
                 momentum_multiplier: float = 1.33,  # Aumentar 33%
                 confidence_boost: float = 0.2,  # Aumentar en 0.2
                 
                 # Ventanas de análisis
                 win_rate_global_lookback: int = 50,  # Últimas 50 operaciones
                 win_rate_recent_lookback: int = 20,  # Últimas 20 operaciones
                 
                 # Umbrales de drawdown para reducción de posición
                 drawdown_level_1: float = 0.05,  # 5% → 75% tamaño
                 drawdown_level_2: float = 0.10,  # 10% → 50% tamaño
                 drawdown_level_3: float = 0.15,  # 15% → 25% tamaño
                 
                 # Recuperación
                 recovery_check_interval: int = 5,  # Revisar cada 5 trades
                 min_win_rate_recovery: float = 0.52,
                 recovery_steps: int = 10,  # Pasos graduales de recuperación
                 ):
        """
        Inicializar gestor adaptativo de filtros
        
        Args:
            win_rate_threshold: Win rate mínimo para considerar rendimiento normal (52%)
            drawdown_threshold: Drawdown mínimo para activar modo conservador (5%)
            losing_streak_threshold: Número de pérdidas consecutivas para activar modo (3)
        """
        self.win_rate_threshold = win_rate_threshold
        self.drawdown_threshold = drawdown_threshold
        self.losing_streak_threshold = losing_streak_threshold
        
        # Parámetros base
        self.base_z_score_threshold = base_z_score_threshold
        self.base_momentum_threshold = base_momentum_threshold
        self.base_confidence_minimum = base_confidence_minimum
        
        # Multiplicadores para ajustes
        self.z_score_multiplier = z_score_multiplier
        self.momentum_multiplier = momentum_multiplier
        self.confidence_boost = confidence_boost
        
        # Ventanas de análisis
        self.win_rate_global_lookback = win_rate_global_lookback
        self.win_rate_recent_lookback = win_rate_recent_lookback
        
        # Umbrales de drawdown
        self.drawdown_level_1 = drawdown_level_1
        self.drawdown_level_2 = drawdown_level_2
        self.drawdown_level_3 = drawdown_level_3
        
        # Recuperación
        self.recovery_check_interval = recovery_check_interval
        self.min_win_rate_recovery = min_win_rate_recovery
        self.recovery_steps = recovery_steps
        
        # Estado actual
        self.conservative_mode = False
        self.initial_balance = None
        self.peak_balance = None
        self.last_metrics_check = None
        self.recovery_progress = 0  # 0-100: Progreso de recuperación
        self.pause_active = False  # Si la pausa está activa
        self.pause_allowed_symbol = None  # Símbolo permitido durante pausa
        
        # Parámetros actuales ajustados
        self.current_parameters = AdaptiveParameters(
            z_score_threshold=self.base_z_score_threshold,
            momentum_threshold=self.base_momentum_threshold,
            confidence_minimum=self.base_confidence_minimum,
            position_size_multiplier=1.0,
            is_conservative_mode=False
        )
    
    def set_initial_balance(self, balance: Decimal):
        """Establecer balance inicial (desde el inicio de la sesión)"""
        if self.initial_balance is None:
            self.initial_balance = balance
            self.peak_balance = balance
            print(f"💰 Balance inicial establecido: ${balance:.2f}")
    
    def update_peak_balance(self, balance: Decimal):
        """Actualizar balance pico (máximo alcanzado)"""
        if self.peak_balance is None or balance > self.peak_balance:
            self.peak_balance = balance
    
    def calculate_metrics(self, current_balance: Decimal) -> PerformanceMetrics:
        """
        Calcular métricas de rendimiento actuales
        
        Args:
            current_balance: Balance actual
            
        Returns:
            PerformanceMetrics con todas las métricas calculadas
        """
        # Actualizar balance pico
        self.update_peak_balance(current_balance)
        
        # Establecer balance inicial si no está establecido
        if self.initial_balance is None:
            self.set_initial_balance(current_balance)
        
        # Calcular drawdown
        if self.peak_balance and self.peak_balance > 0:
            drawdown_pct = float((self.peak_balance - current_balance) / self.peak_balance)
        else:
            drawdown_pct = 0.0
        
        # Calcular win rate global (últimas N operaciones)
        try:
            global_trades = OrderAudit.objects.filter(
                accepted=True,
                status__in=['won', 'lost']
            ).order_by('-timestamp')[:self.win_rate_global_lookback]
            
            global_total = global_trades.count()
            global_won = global_trades.filter(status='won').count()
            win_rate_global = (global_won / global_total) if global_total > 0 else 0.0
        except Exception:
            win_rate_global = 0.0
        
        # Calcular win rate reciente (últimas 20 operaciones) - CRÍTICO PARA FILTRADO
        try:
            recent_trades = list(OrderAudit.objects.filter(
                accepted=True,
                status__in=['won', 'lost']
            ).order_by('-timestamp')[:20])  # Siempre últimos 20 trades
            
            recent_total = len(recent_trades)
            recent_won = sum(1 for t in recent_trades if t.status == 'won')
            win_rate_recent = (recent_won / recent_total) if recent_total > 0 else 0.0
        except Exception:
            win_rate_recent = 0.0
        
        # Calcular rachas (pérdidas/ganancias consecutivas)
        try:
            last_trades = list(
                OrderAudit.objects.filter(
                    accepted=True,
                    status__in=['won', 'lost']
                ).order_by('-timestamp')[:10]
            )
            
            losing_streak = 0
            winning_streak = 0
            
            for trade in last_trades:
                if trade.status == 'lost':
                    if losing_streak == 0:
                        losing_streak = 1
                    else:
                        losing_streak += 1
                    winning_streak = 0
                elif trade.status == 'won':
                    if winning_streak == 0:
                        winning_streak = 1
                    else:
                        winning_streak += 1
                    losing_streak = 0
        except Exception:
            losing_streak = 0
            winning_streak = 0
        
        # Contar trades totales y del día
        try:
            total_trades = OrderAudit.objects.filter(accepted=True).count()
            today = timezone.now().date()
            trades_today = OrderAudit.objects.filter(
                accepted=True,
                timestamp__date=today
            ).count()
        except Exception:
            total_trades = 0
            trades_today = 0
        
        return PerformanceMetrics(
            win_rate_global=win_rate_global,
            win_rate_recent=win_rate_recent,
            drawdown_pct=drawdown_pct,
            current_balance=current_balance,
            initial_balance=self.initial_balance or Decimal('0'),
            peak_balance=self.peak_balance or Decimal('0'),
            losing_streak=losing_streak,
            winning_streak=winning_streak,
            total_trades=total_trades,
            trades_today=trades_today
        )
    
    def should_activate_conservative_mode(self, metrics: PerformanceMetrics) -> bool:
        """
        Evaluar si debe activarse el modo conservador
        
        Criterios:
        - Win rate < 52% (global o reciente) - SOLO si hay >= 10 trades
        - Balance < balance inicial
        - Drawdown > 5%
        - Racha perdedora >= 3
        """
        conditions = []
        
        # Win rate solo si hay suficientes trades (mínimo 10)
        if metrics.total_trades >= 10:
            conditions.extend([
                metrics.win_rate_global < self.win_rate_threshold,
                metrics.win_rate_recent < self.win_rate_threshold
            ])
        
        # Estas condiciones siempre se evalúan
        conditions.extend([
            float(metrics.current_balance) < float(metrics.initial_balance),
            metrics.drawdown_pct > self.drawdown_threshold,
            metrics.losing_streak >= self.losing_streak_threshold
        ])
        
        return any(conditions)
    
    def calculate_position_size_multiplier(self, drawdown_pct: float) -> float:
        """
        Calcular multiplicador de tamaño de posición según drawdown
        
        Drawdown < 5%: 100% del tamaño normal
        Drawdown 5-10%: 75% del tamaño
        Drawdown 10-15%: 50% del tamaño
        Drawdown > 15%: 25% del tamaño
        """
        if drawdown_pct < self.drawdown_level_1:
            return 1.0  # 100%
        elif drawdown_pct < self.drawdown_level_2:
            return 0.75  # 75%
        elif drawdown_pct < self.drawdown_level_3:
            return 0.50  # 50%
        else:
            return 0.25  # 25%
    
    def adjust_parameters(self, metrics: PerformanceMetrics) -> AdaptiveParameters:
        """
        Ajustar parámetros según métricas actuales
        
        Returns:
            AdaptiveParameters con valores ajustados
        """
        should_conserve = self.should_activate_conservative_mode(metrics)
        
        if should_conserve and not self.conservative_mode:
            # Activar modo conservador
            self.conservative_mode = True
            print(f"⚠️  MODO CONSERVADOR ACTIVADO")
            print(f"   - Win Rate Global: {metrics.win_rate_global:.1%}")
            print(f"   - Win Rate Reciente: {metrics.win_rate_recent:.1%}")
            print(f"   - Drawdown: {metrics.drawdown_pct:.1%}")
            print(f"   - Balance: ${metrics.current_balance:.2f} (Inicial: ${metrics.initial_balance:.2f})")
            print(f"   - Racha Perdedora: {metrics.losing_streak}")
        
        elif not should_conserve and self.conservative_mode:
            # Evaluar recuperación
            recovery_ready = (
                metrics.win_rate_global >= self.min_win_rate_recovery and
                metrics.win_rate_recent >= self.min_win_rate_recovery and
                float(metrics.current_balance) >= float(metrics.initial_balance) and
                metrics.drawdown_pct < (self.drawdown_threshold * 0.4)  # 2%
            )
            
            if recovery_ready:
                # Iniciar recuperación gradual
                self.recovery_progress = min(100, self.recovery_progress + (100 / self.recovery_steps))
                
                if self.recovery_progress >= 100:
                    # Completar recuperación
                    self.conservative_mode = False
                    self.recovery_progress = 0
                    print(f"✅ MODO NORMAL RESTAURADO")
                    print(f"   - Win Rate Global: {metrics.win_rate_global:.1%}")
                    print(f"   - Balance: ${metrics.current_balance:.2f}")
                else:
                    print(f"🔄 RECUPERACIÓN EN PROGRESO: {self.recovery_progress:.0f}%")
        
        # Calcular parámetros ajustados
        if self.conservative_mode:
            # Ajustar umbrales durante drawdown
            # Z-Score: 2.0 → 2.5-3.0 (aumentar 25%)
            adjusted_z_score = self.base_z_score_threshold * self.z_score_multiplier
            
            # Momentum: 1.5% → 2.0-2.5% (aumentar 33%)
            adjusted_momentum = self.base_momentum_threshold * self.momentum_multiplier
            
            # Confidence: 0.5 → 0.7-0.8 (aumentar en 0.2)
            adjusted_confidence = min(0.9, self.base_confidence_minimum + self.confidence_boost)
            
            # Aplicar recuperación gradual si está en progreso
            if self.recovery_progress > 0:
                progress_factor = 1.0 - (self.recovery_progress / 100.0)
                adjusted_z_score = self.base_z_score_threshold + (adjusted_z_score - self.base_z_score_threshold) * progress_factor
                adjusted_momentum = self.base_momentum_threshold + (adjusted_momentum - self.base_momentum_threshold) * progress_factor
                adjusted_confidence = self.base_confidence_minimum + (adjusted_confidence - self.base_confidence_minimum) * progress_factor
        else:
            # Modo normal
            adjusted_z_score = self.base_z_score_threshold
            adjusted_momentum = self.base_momentum_threshold
            adjusted_confidence = self.base_confidence_minimum
        
        # Calcular multiplicador de tamaño de posición según drawdown
        position_multiplier = self.calculate_position_size_multiplier(metrics.drawdown_pct)
        
        return AdaptiveParameters(
            z_score_threshold=adjusted_z_score,
            momentum_threshold=adjusted_momentum,
            confidence_minimum=adjusted_confidence,
            position_size_multiplier=position_multiplier,
            is_conservative_mode=self.conservative_mode
        )
    
    def get_adjusted_parameters(self, current_balance: Decimal) -> AdaptiveParameters:
        """
        Obtener parámetros ajustados según métricas actuales
        
        Args:
            current_balance: Balance actual
            
        Returns:
            AdaptiveParameters con valores ajustados dinámicamente
        """
        # Calcular métricas
        metrics = self.calculate_metrics(current_balance)
        
        # Ajustar parámetros
        self.current_parameters = self.adjust_parameters(metrics)
        
        return self.current_parameters
    
    def get_current_parameters(self) -> AdaptiveParameters:
        """Obtener parámetros actuales"""
        return self.current_parameters
    
    def should_pause_trading(self, metrics: PerformanceMetrics, best_symbol: str = None) -> dict:
        """
        Determinar si debe pausarse el trading
        
        Pausar si:
        - Drawdown > 15% (ya en nivel mínimo de posición)
        - Racha perdedora >= 5
        
        Args:
            metrics: Métricas actuales
            best_symbol: Símbolo con mejor desempeño (para permitir durante pausa)
        
        Returns:
            dict con:
            - 'should_pause': bool - Si debe pausar
            - 'allowed_symbol': str o None - Símbolo permitido durante pausa (el mejor)
        """
        should_pause = False
        if metrics.drawdown_pct > self.drawdown_level_3:
            should_pause = True
        if metrics.losing_streak >= 5:
            should_pause = True
        
        # Si la racha perdedora se rompió (losing_streak < 5), desactivar pausa
        if self.pause_active and metrics.losing_streak < 5 and metrics.drawdown_pct <= self.drawdown_level_3:
            should_pause = False
            self.pause_active = False
            self.pause_allowed_symbol = None
        
        allowed_symbol = None
        if should_pause:
            self.pause_active = True
            # Usar el símbolo proporcionado (mejor desempeño)
            allowed_symbol = best_symbol if best_symbol else None
            self.pause_allowed_symbol = allowed_symbol
        else:
            self.pause_active = False
            self.pause_allowed_symbol = None
        
        return {
            'should_pause': should_pause,
            'allowed_symbol': allowed_symbol
        }
    
    def get_top_symbols_by_performance(self, lookback: int = 20, top_n: int = 5) -> List[Tuple[str, float]]:
        """
        Obtener los top N símbolos por desempeño
        
        Returns:
            Lista de tuplas (símbolo, score) ordenadas por score descendente
        """
        symbol_perf = self.calculate_symbol_performance(lookback=lookback)
        sorted_symbols = sorted(symbol_perf.items(), key=lambda x: x[1]['score'], reverse=True)
        return [(s, perf['score']) for s, perf in sorted_symbols[:top_n]]
    
    def calculate_symbol_performance(self, lookback: int = 20) -> Dict[str, Dict[str, float]]:
        """
        Calcular desempeño por símbolo basado en los últimos N trades
        
        Args:
            lookback: Número de trades a analizar (default: 20)
            
        Returns:
            Diccionario con métricas por símbolo: {
                'SYMBOL': {
                    'win_rate': 0.65,
                    'total_pnl': 15.50,
                    'avg_pnl': 0.78,
                    'trades_count': 20,
                    'score': 0.75  # Score combinado (0-1)
                }
            }
        """
        try:
            from decimal import Decimal
            
            # Obtener últimos N trades finalizados
            recent_trades = list(
                OrderAudit.objects.filter(
                    accepted=True,
                    status__in=['won', 'lost']
                ).order_by('-timestamp')[:lookback]
            )
            
            # Agrupar por símbolo
            symbol_stats: Dict[str, Dict[str, Any]] = {}
            
            for trade in recent_trades:
                symbol = trade.symbol
                
                if symbol not in symbol_stats:
                    symbol_stats[symbol] = {
                        'won': 0,
                        'lost': 0,
                        'total_pnl': Decimal('0.00'),
                        'trades': []
                    }
                
                symbol_stats[symbol]['trades'].append(trade)
                
                if trade.status == 'won':
                    symbol_stats[symbol]['won'] += 1
                elif trade.status == 'lost':
                    symbol_stats[symbol]['lost'] += 1
                
                # Sumar P&L
                if trade.pnl:
                    symbol_stats[symbol]['total_pnl'] += Decimal(str(trade.pnl))
            
            # Calcular métricas finales
            result: Dict[str, Dict[str, float]] = {}
            
            for symbol, stats in symbol_stats.items():
                total = stats['won'] + stats['lost']
                if total == 0:
                    continue
                
                win_rate = stats['won'] / total
                total_pnl = float(stats['total_pnl'])
                avg_pnl = total_pnl / total if total > 0 else 0.0
                
                # Calcular score combinado (0-1)
                # Factor 1: Win rate (peso 0.4)
                win_rate_score = win_rate
                
                # Factor 2: P&L promedio normalizado (peso 0.4)
                # Normalizar P&L promedio a rango 0-1 (asumiendo que -$2 a $2 es el rango típico)
                normalized_pnl = max(0, min(1, (avg_pnl + 2) / 4))
                
                # Factor 3: Consistencia (menos trades = menos confianza) (peso 0.2)
                # Preferir símbolos con más trades (más datos)
                consistency_score = min(1.0, total / 10)  # Máximo score con 10+ trades
                
                # Score combinado
                score = (win_rate_score * 0.4) + (normalized_pnl * 0.4) + (consistency_score * 0.2)
                
                result[symbol] = {
                    'win_rate': win_rate,
                    'total_pnl': total_pnl,
                    'avg_pnl': avg_pnl,
                    'trades_count': total,
                    'score': score
                }
            
            return result
            
        except Exception as e:
            print(f"Error calculando desempeño de símbolos: {e}")
            return {}

