"""
Gestor de Capital Avanzado con Técnicas Matemáticas y Estadísticas
Implementa Kelly Criterion, Anti-Martingala, Fixed Fractional, VaR, etc.
"""

from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, List
from django.utils import timezone
from django.db.models import Sum, Avg, StdDev
from monitoring.models import OrderAudit
import math


@dataclass
class PositionSizeResult:
    """Resultado del cálculo de tamaño de posición"""
    contract_amount: Decimal
    risk_amount: Decimal
    recommended_contracts: int
    method_used: str
    confidence: float  # 0-1


class AdvancedCapitalManager:
    """
    Gestor de Capital Avanzado con múltiples estrategias matemáticas
    
    Estrategias disponibles:
    1. Kelly Criterion - Tamaño óptimo basado en win rate y win/loss ratio
    2. Fixed Fractional - Porcentaje fijo del capital
    3. Anti-Martingala - Aumentar después de ganancias
    4. Risk Parity - Distribución equitativa del riesgo
    5. Volatility-Based - Ajuste según volatilidad (ATR)
    6. Value at Risk (VaR) - Análisis de riesgo potencial
    """
    
    def __init__(self,
                 # Configuración básica (heredada)
                 profit_target: Decimal = Decimal('100.00'),
                 max_loss: Decimal = Decimal('-50.00'),
                 max_trades: int = 50,
                 profit_target_pct: float = 2.0,
                 max_loss_pct: float = 1.0,
                 
                 # Estrategia de position sizing
                 position_sizing_method: str = 'kelly_fractional',  # kelly, fixed_fractional, anti_martingale, risk_parity, volatility
                 
                 # Kelly Criterion
                 kelly_fraction: float = 0.25,  # Usar 25% del Kelly óptimo (más conservador)
                 
                 # Fixed Fractional
                 risk_per_trade_pct: float = 1.0,  # 1% del capital por trade
                 
                 # Anti-Martingala
                 anti_martingale_multiplier: float = 1.5,  # Multiplicar por 1.5 después de ganancia
                 anti_martingale_reset_on_loss: bool = True,  # Resetear a tamaño base después de pérdida
                 
                 # Martingala (Aumentar después de pérdidas)
                 enable_martingale: bool = False,
                 martingale_multiplier: float = 2.0,  # Multiplicador después de pérdida
                 martingale_base_amount: Decimal = Decimal('0.10'),  # Monto base
                 martingale_max_levels: int = 5,  # Profundidad máxima
                 martingale_reset_on_win: bool = True,  # Resetear después de ganancia
                 
                 # Volatility-Based
                 atr_multiplier: float = 2.0,  # Multiplicador del ATR para stop loss
                 max_risk_per_trade_pct: float = 2.0,  # Máximo 2% del capital por trade
                 
                 # Drawdown Protection
                 max_drawdown_pct: float = 10.0,  # Máximo 10% de drawdown permitido
                 reduce_size_on_drawdown: bool = True,  # Reducir tamaño en drawdown
                 
                 # Value at Risk
                 var_confidence: float = 0.95,  # 95% de confianza
                 var_horizon_days: int = 1,  # Horizonte de 1 día
                 
                 # Portfolio Optimization
                 max_concurrent_positions: int = 5,  # Máximo de posiciones simultáneas
                 
                 # Risk Parity
                 target_volatility: float = 0.15,  # 15% de volatilidad objetivo
                 ):
        """
        Inicializar gestor avanzado de capital
        """
        self.profit_target = profit_target
        self.max_loss = max_loss
        self.max_trades = max_trades
        self.profit_target_pct = profit_target_pct
        self.max_loss_pct = max_loss_pct
        
        self.position_sizing_method = position_sizing_method
        self.kelly_fraction = kelly_fraction
        self.risk_per_trade_pct = risk_per_trade_pct
        self.anti_martingale_multiplier = anti_martingale_multiplier
        self.anti_martingale_reset_on_loss = anti_martingale_reset_on_loss
        self.enable_martingale = enable_martingale
        self.martingale_multiplier = martingale_multiplier
        self.martingale_base_amount = martingale_base_amount
        self.martingale_max_levels = martingale_max_levels
        self.martingale_reset_on_win = martingale_reset_on_win
        self.atr_multiplier = atr_multiplier
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.reduce_size_on_drawdown = reduce_size_on_drawdown
        self.var_confidence = var_confidence
        self.var_horizon_days = var_horizon_days
        self.max_concurrent_positions = max_concurrent_positions
        self.target_volatility = target_volatility
        
        # Estado de trading
        self._consecutive_wins = 0
        self._consecutive_losses = 0
        self._martingale_level = 0  # Nivel actual de martingala (0 = base)
        self._martingale_accumulated_losses = Decimal('0.00')  # Pérdidas acumuladas para calcular siguiente monto
        self._base_position_size = None
        self._current_position_size = None
        self._peak_balance = None
    
    def calculate_kelly_criterion(self, win_rate: float, avg_win: Decimal, avg_loss: Decimal) -> float:
        """
        Calcular Kelly Criterion: porcentaje óptimo del capital a arriesgar
        
        Fórmula: f = (bp - q) / b
        donde:
        - f = fracción del capital a arriesgar
        - b = ratio ganancia/pérdida (odds)
        - p = probabilidad de ganar
        - q = probabilidad de perder (1 - p)
        
        Returns:
            Kelly percentage (0-1), o 0 si no es viable
        """
        if avg_loss == 0 or win_rate <= 0 or win_rate >= 1:
            return 0.0
        
        # Ratio de ganancia/pérdida
        b = float(avg_win / abs(avg_loss))
        p = win_rate
        q = 1 - p
        
        # Fórmula de Kelly
        kelly = (b * p - q) / b
        
        # Usar fracción del Kelly para ser más conservador
        kelly_fraction = kelly * self.kelly_fraction
        
        # Asegurar que está en rango válido [0, 0.25]
        return max(0.0, min(0.25, kelly_fraction))
    
    def get_trading_statistics(self, symbol: Optional[str] = None, days: int = 30) -> Dict[str, Any]:
        """
        Obtener estadísticas de trading para cálculos avanzados
        
        Returns:
            Dict con win_rate, avg_win, avg_loss, total_trades, etc.
        """
        since = timezone.now() - timedelta(days=days)
        
        queryset = OrderAudit.objects.filter(
            timestamp__gte=since,
            status__in=['won', 'lost'],
            pnl__isnull=False
        )
        
        if symbol:
            queryset = queryset.filter(symbol=symbol)
        
        won_trades = queryset.filter(status='won')
        lost_trades = queryset.filter(status='lost')
        
        total_trades = queryset.count()
        won_count = won_trades.count()
        lost_count = lost_trades.count()
        
        win_rate = (won_count / total_trades) if total_trades > 0 else 0.0
        
        # Promedios
        avg_win = won_trades.aggregate(avg=Avg('pnl'))['avg'] or Decimal('0.00')
        avg_loss = lost_trades.aggregate(avg=Avg('pnl'))['avg'] or Decimal('0.00')
        
        # Desviación estándar para VaR
        pnl_values = list(queryset.values_list('pnl', flat=True))
        if pnl_values:
            mean_pnl = float(avg_win) * win_rate + float(avg_loss) * (1 - win_rate)
            variance = sum((float(x) - mean_pnl) ** 2 for x in pnl_values) / len(pnl_values)
            std_dev = math.sqrt(variance) if variance > 0 else 0.0
        else:
            std_dev = 0.0
        
        # Calcular Kelly
        kelly_pct = self.calculate_kelly_criterion(win_rate, avg_win, avg_loss)
        
        return {
            'total_trades': total_trades,
            'won_trades': won_count,
            'lost_trades': lost_count,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'kelly_percentage': kelly_pct,
            'std_dev': std_dev,
            'profit_factor': float(avg_win) / float(abs(avg_loss)) if avg_loss != 0 else 0.0,
        }
    
    def calculate_position_size(self, 
                               current_balance: Decimal,
                               symbol: Optional[str] = None,
                               entry_price: Optional[Decimal] = None,
                               stop_loss_price: Optional[Decimal] = None,
                               atr_value: Optional[Decimal] = None) -> PositionSizeResult:
        """
        Calcular tamaño óptimo de posición según la estrategia seleccionada
        
        Args:
            current_balance: Balance actual
            symbol: Símbolo a operar (opcional, para estadísticas específicas)
            entry_price: Precio de entrada (para stop loss basado en precio)
            stop_loss_price: Precio de stop loss (para cálculo de riesgo)
            atr_value: Valor de ATR actual (para volatility-based sizing)
        
        Returns:
            PositionSizeResult con tamaño recomendado
        """
        stats = self.get_trading_statistics(symbol=symbol)
        
        if self.position_sizing_method == 'kelly':
            # Kelly Criterion
            kelly_pct = stats['kelly_percentage']
            if kelly_pct > 0:
                risk_amount = current_balance * Decimal(str(kelly_pct))
                method = 'Kelly Criterion'
                confidence = min(0.95, stats['win_rate'] * 1.2)  # Boost confidence con win rate
            else:
                # Fallback a fixed fractional
                risk_amount = current_balance * Decimal(str(self.risk_per_trade_pct / 100))
                method = 'Fixed Fractional (fallback)'
                confidence = 0.5
        
        elif self.position_sizing_method == 'fixed_fractional':
            # Fixed Fractional - porcentaje fijo del capital
            risk_amount = current_balance * Decimal(str(self.risk_per_trade_pct / 100))
            method = 'Fixed Fractional'
            confidence = 0.7
        
        elif self.position_sizing_method == 'anti_martingale':
            # Anti-Martingala - aumentar después de ganancias
            base_risk = current_balance * Decimal(str(self.risk_per_trade_pct / 100))
            
            if self._consecutive_wins > 0:
                multiplier = self.anti_martingale_multiplier ** min(self._consecutive_wins, 3)  # Max 3x
                risk_amount = base_risk * Decimal(str(multiplier))
            else:
                risk_amount = base_risk
            
            # Limitar máximo riesgo
            max_risk = current_balance * Decimal(str(self.max_risk_per_trade_pct / 100))
            risk_amount = min(risk_amount, max_risk)
            
            method = 'Anti-Martingala'
            confidence = min(0.9, 0.6 + (self._consecutive_wins * 0.1))
        
        elif self.position_sizing_method == 'volatility':
            # Volatility-Based - ajustar según ATR
            if atr_value and entry_price:
                # Calcular stop loss basado en ATR
                stop_distance = atr_value * Decimal(str(self.atr_multiplier))
                risk_per_contract = stop_distance / entry_price * current_balance
                
                # Ajustar para que el riesgo total no exceda el máximo
                max_risk = current_balance * Decimal(str(self.max_risk_per_trade_pct / 100))
                risk_amount = min(risk_per_contract, max_risk)
            else:
                # Fallback a fixed fractional
                risk_amount = current_balance * Decimal(str(self.risk_per_trade_pct / 100))
            
            method = 'Volatility-Based (ATR)'
            confidence = 0.75
        
        elif self.position_sizing_method == 'risk_parity':
            # Risk Parity - distribución equitativa del riesgo
            # Calcular riesgo objetivo por posición
            target_risk = current_balance * Decimal(str(self.target_volatility / self.max_concurrent_positions))
            risk_amount = min(target_risk, current_balance * Decimal(str(self.max_risk_per_trade_pct / 100)))
            
            method = 'Risk Parity'
            confidence = 0.8
        
        elif self.position_sizing_method == 'kelly_fractional':
            # Kelly Fractional - usar fracción del Kelly óptimo (más conservador)
            kelly_pct = stats['kelly_percentage']
            if kelly_pct > 0:
                # Aplicar fracción (ej: 25% del Kelly óptimo)
                fractional_kelly = kelly_pct * self.kelly_fraction
                risk_amount = current_balance * Decimal(str(fractional_kelly))
            else:
                # Fallback a fixed fractional
                risk_amount = current_balance * Decimal(str(self.risk_per_trade_pct / 100))
            method = 'Kelly Fractional (Conservative)'
            confidence = min(0.9, stats['win_rate'] * 1.1)
        
        elif self.position_sizing_method == 'martingale' or self.enable_martingale:
            # Martingala - calcular monto para recuperar pérdidas acumuladas
            # Fórmula: M_{n+1} = Pérdidas acumuladas / 0.9 (payout 90%)
            payout_rate = Decimal('0.90')  # Payout del 90%
            
            if self._martingale_level == 0:
                # Primer nivel: usar monto base
                risk_amount = self.martingale_base_amount
            else:
                # Niveles siguientes: calcular para recuperar pérdidas acumuladas
                # Si ganamos este trade con payout 90%, recuperamos: risk_amount * 0.9
                # Necesitamos que: risk_amount * 0.9 >= pérdidas_acumuladas
                # Por tanto: risk_amount >= pérdidas_acumuladas / 0.9
                if self._martingale_accumulated_losses > 0:
                    risk_amount = self._martingale_accumulated_losses / payout_rate
                    # Redondear a 2 decimales (Deriv requiere máximo 2 decimales)
                    risk_amount = risk_amount.quantize(Decimal('0.01'))
                    # Mínimo: monto base
                    risk_amount = max(risk_amount, self.martingale_base_amount)
                else:
                    # Si no hay pérdidas acumuladas, usar monto base
                    risk_amount = self.martingale_base_amount
            
            # Verificar límite de profundidad (máximo nivel 8)
            max_allowed_level = min(self.martingale_max_levels, 8)  # Máximo nivel 8
            if self._martingale_level >= max_allowed_level:
                # Resetear si alcanzó el máximo (nivel 8)
                self._martingale_level = 0
                self._martingale_accumulated_losses = Decimal('0.00')
                risk_amount = self.martingale_base_amount
                method = f'Martingala (Reset por máximo nivel {max_allowed_level})'
            else:
                method = f'Martingala (Nivel {self._martingale_level + 1}/{max_allowed_level}, Recuperar ${self._martingale_accumulated_losses:.2f})'
            
            # NO resetear por balance insuficiente - permitir que continúe hasta el nivel máximo
            # Solo verificar que el monto no exceda el 95% del balance disponible para evitar problemas
            max_allowed_balance = current_balance * Decimal('0.95')  # Dejar 5% de margen
            if risk_amount > max_allowed_balance and self._martingale_level < max_allowed_level:
                # Si excede pero aún no alcanzó el máximo nivel, reducir ligeramente pero continuar
                risk_amount = max_allowed_balance
                method = f'Martingala (Nivel {self._martingale_level + 1}/{max_allowed_level}, Ajustado a ${risk_amount:.2f})'
            elif risk_amount > max_allowed_balance and self._martingale_level >= max_allowed_level:
                # Solo resetear si ya alcanzó el máximo nivel Y excede el balance
                self._martingale_level = 0
                self._martingale_accumulated_losses = Decimal('0.00')
                risk_amount = self.martingale_base_amount
                method = 'Martingala (Reset: máximo nivel + balance insuficiente)'
            
            confidence = max(0.3, 0.7 - (self._martingale_level * 0.1))  # Menos confianza en niveles altos
        
        else:
            # Default fallback: fixed fractional
            risk_amount = current_balance * Decimal(str(self.risk_per_trade_pct / 100))
            method = 'Fixed Fractional (default)'
            confidence = 0.6
        
        # Aplicar protección de drawdown
        if self.reduce_size_on_drawdown:
            drawdown = self.calculate_drawdown(current_balance)
            if drawdown > self.max_drawdown_pct:
                # Reducir tamaño proporcionalmente al drawdown
                reduction_factor = 1 - ((drawdown - self.max_drawdown_pct) / 100)
                risk_amount = risk_amount * Decimal(str(max(0.1, reduction_factor)))  # Mínimo 10% del tamaño
        
        # Calcular número de contratos (asumiendo $1 por contrato)
        contract_amount = risk_amount
        recommended_contracts = int(float(contract_amount))
        
        return PositionSizeResult(
            contract_amount=contract_amount,
            risk_amount=risk_amount,
            recommended_contracts=max(1, recommended_contracts),
            method_used=method,
            confidence=confidence
        )
    
    def calculate_drawdown(self, current_balance: Decimal) -> float:
        """
        Calcular drawdown actual como porcentaje del peak
        """
        if self._peak_balance is None or current_balance > self._peak_balance:
            self._peak_balance = current_balance
        
        if self._peak_balance == 0:
            return 0.0
        
        drawdown = (float(self._peak_balance - current_balance) / float(self._peak_balance)) * 100
        return drawdown
    
    def calculate_var(self, current_balance: Decimal, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Calcular Value at Risk (VaR) - pérdida potencial con cierta confianza
        
        Returns:
            Dict con VaR en USD y porcentaje
        """
        stats = self.get_trading_statistics(symbol=symbol, days=30)
        
        if stats['std_dev'] == 0:
            return {
                'var_usd': Decimal('0.00'),
                'var_pct': 0.0,
                'confidence': self.var_confidence,
            }
        
        # VaR usando distribución normal (simplificado)
        # Para 95% confianza, z-score ≈ 1.96
        z_score = 1.96 if self.var_confidence == 0.95 else 2.33  # 99% confianza
        
        var_amount = Decimal(str(stats['std_dev'] * z_score * math.sqrt(self.var_horizon_days)))
        var_pct = (float(var_amount) / float(current_balance)) * 100 if current_balance > 0 else 0.0
        
        return {
            'var_usd': var_amount,
            'var_pct': var_pct,
            'confidence': self.var_confidence,
            'std_dev': stats['std_dev'],
        }
    
    def update_trade_result(self, won: bool):
        """
        Actualizar estado interno después de un trade
        
        Args:
            won: True si el trade fue ganador
        """
        if won:
            self._consecutive_wins += 1
            self._consecutive_losses = 0
        else:
            self._consecutive_losses += 1
            if self.anti_martingale_reset_on_loss:
                self._consecutive_wins = 0
    
    def can_trade(self, current_balance: Decimal) -> Tuple[bool, Optional[str]]:
        """
        Verificar si se puede realizar un nuevo trade (heredado de CapitalManager básico)
        """
        # Verificar drawdown máximo
        drawdown = self.calculate_drawdown(current_balance)
        if drawdown > self.max_drawdown_pct:
            return False, f"Drawdown máximo excedido: {drawdown:.2f}% > {self.max_drawdown_pct}%"
        
        # Verificar límites básicos (del CapitalManager original)
        # max_trades siempre ilimitado para operación perpetua
        from engine.services.capital_manager import CapitalManager
        basic_manager = CapitalManager(
            profit_target=self.profit_target,
            max_loss=self.max_loss,
            max_trades=999999,  # Siempre ilimitado
            profit_target_pct=self.profit_target_pct,
            max_loss_pct=self.max_loss_pct
        )
        
        can_trade, reason = basic_manager.can_trade(current_balance)
        return can_trade, reason
    
    def get_recommended_position_size(self,
                                     current_balance: Decimal,
                                     symbol: str,
                                     entry_price: Decimal,
                                     stop_loss_price: Optional[Decimal] = None,
                                     atr_value: Optional[Decimal] = None) -> PositionSizeResult:
        """
        Obtener tamaño recomendado de posición con todos los factores
        
        Args:
            current_balance: Balance actual
            symbol: Símbolo a operar
            entry_price: Precio de entrada
            stop_loss_price: Precio de stop loss (opcional)
            atr_value: Valor ATR (opcional, para volatility-based)
        
        Returns:
            PositionSizeResult con recomendación
        """
        # Calcular tamaño base según estrategia
        position_size = self.calculate_position_size(
            current_balance=current_balance,
            symbol=symbol,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            atr_value=atr_value
        )
        
        # Aplicar límites adicionales
        max_risk = current_balance * Decimal(str(self.max_risk_per_trade_pct / 100))
        if position_size.risk_amount > max_risk:
            position_size.risk_amount = max_risk
            position_size.contract_amount = max_risk
        
        return position_size
    
    def update_martingale_level(self, trade_won: bool, trade_amount: Decimal = None):
        """
        Actualizar nivel de martingala después de un trade
        
        Args:
            trade_won: True si el trade ganó, False si perdió
            trade_amount: Monto del trade (para acumular pérdidas)
        """
        if not self.enable_martingale and self.position_sizing_method != 'martingale':
            return
        
        if trade_won:
            # Si ganó, resetear todo (recuperó las pérdidas acumuladas)
            if self.martingale_reset_on_win:
                self._martingale_level = 0
                self._martingale_accumulated_losses = Decimal('0.00')
                self._consecutive_wins += 1
                self._consecutive_losses = 0
            else:
                # Si no resetear, mantener nivel pero aumentar wins
                self._consecutive_wins += 1
                self._consecutive_losses = 0
        else:
            # Si perdió, acumular la pérdida y aumentar nivel
            if trade_amount:
                self._martingale_accumulated_losses += trade_amount
            
            if self._martingale_level < self.martingale_max_levels:
                self._martingale_level += 1
            else:
                # Si alcanzó el máximo, resetear
                self._martingale_level = 0
                self._martingale_accumulated_losses = Decimal('0.00')
            self._consecutive_losses += 1
            self._consecutive_wins = 0
    
    def get_advanced_statistics(self, current_balance: Decimal) -> Dict[str, Any]:
        """
        Obtener estadísticas avanzadas para visualización
        
        Returns:
            Dict con métricas avanzadas (Kelly, VaR, Sharpe, etc.)
        """
        stats = self.get_trading_statistics()
        var_data = self.calculate_var(current_balance)
        drawdown = self.calculate_drawdown(current_balance)
        
        # Calcular Sharpe Ratio (simplificado)
        # Sharpe = (Retorno - Risk Free Rate) / Volatilidad
        # Asumimos risk-free rate = 0 para simplificar
        sharpe_ratio = 0.0
        if stats['std_dev'] > 0:
            # Retorno promedio diario aproximado
            avg_daily_return = (float(stats['avg_win']) * stats['win_rate'] + 
                              float(stats['avg_loss']) * (1 - stats['win_rate']))
            sharpe_ratio = avg_daily_return / stats['std_dev'] if stats['std_dev'] > 0 else 0.0
        
        return {
            'trading_stats': stats,
            'var': var_data,
            'drawdown_pct': drawdown,
            'peak_balance': self._peak_balance or current_balance,
            'sharpe_ratio': sharpe_ratio,
            'consecutive_wins': self._consecutive_wins,
            'consecutive_losses': self._consecutive_losses,
            'position_sizing_method': self.position_sizing_method,
        }

