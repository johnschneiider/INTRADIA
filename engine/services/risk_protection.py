"""
Sistema Avanzado de Protección de Riesgo
Implementa múltiples capas de protección para mantener seguras las inversiones
"""

from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from django.utils import timezone
from django.db.models import Q, Count
from monitoring.models import OrderAudit
from market.models import Tick
import statistics


@dataclass
class RiskCheckResult:
    """Resultado de verificación de riesgo"""
    allowed: bool
    reason: Optional[str] = None
    adjusted_size: Optional[Decimal] = None
    protection_applied: Optional[str] = None


@dataclass
class PortfolioRiskMetrics:
    """Métricas de riesgo del portafolio"""
    total_exposure_pct: float  # Porcentaje total del capital en riesgo
    correlated_exposure_pct: float  # Exposición a símbolos correlacionados
    max_position_risk_pct: float  # Riesgo de la posición más grande
    active_positions_count: int  # Número de posiciones activas
    average_position_size: Decimal  # Tamaño promedio de posiciones


class RiskProtectionSystem:
    """
    Sistema de Protección de Riesgo Multi-Capa
    
    Protecciones implementadas:
    1. Maximum Portfolio Risk - Limita riesgo total
    2. Correlation Limits - Evita sobreexposición correlacionada
    3. Maximum Position Size - Limita tamaño máximo por posición
    4. Volatility Scaling - Reduce tamaño en alta volatilidad
    5. Time-Based Stop Loss - Cierra posiciones estancadas
    6. Emergency Stop - Detiene trading en caídas súbitas
    7. Trailing Stop Loss - Protege ganancias automáticamente
    """
    
    def __init__(self,
                 # Límites de Portfolio
                 max_portfolio_risk_pct: float = 15.0,  # Máximo 15% del capital total en riesgo
                 max_single_position_risk_pct: float = 5.0,  # Máximo 5% por posición individual
                 max_correlated_exposure_pct: float = 10.0,  # Máximo 10% en símbolos correlacionados
                 max_active_positions: int = 10,  # Máximo 10 posiciones simultáneas
                 
                 # Volatility Protection
                 high_volatility_threshold: float = 2.0,  # 2x la volatilidad promedio = alta
                 volatility_reduction_pct: float = 50.0,  # Reducir 50% en alta volatilidad
                 
                 # Time-Based Protection
                 max_position_duration_minutes: int = 60,  # Cerrar posiciones después de 60 min sin ganar
                 close_losing_positions_after_minutes: int = 30,  # Cerrar pérdidas después de 30 min
                 
                # Emergency Stop
                emergency_drawdown_threshold_pct: float = 10.0,  # Detener si caída > 10% en 5 minutos (aumentado de 5.0)
                 emergency_volatility_spike: float = 3.0,  # Detener si volatilidad sube 3x
                 
                 # Trailing Stop
                 enable_trailing_stop: bool = True,
                 trailing_stop_distance_pct: float = 1.0,  # 1% de distancia para trailing stop
                 min_profit_for_trailing_pct: float = 0.5,  # Mínimo 0.5% de ganancia para activar
                 
                 # Correlation Groups
                 correlation_groups: Optional[Dict[str, List[str]]] = None):
        """
        Inicializar sistema de protección de riesgo
        """
        self.max_portfolio_risk_pct = max_portfolio_risk_pct
        self.max_single_position_risk_pct = max_single_position_risk_pct
        self.max_correlated_exposure_pct = max_correlated_exposure_pct
        self.max_active_positions = max_active_positions
        self.high_volatility_threshold = high_volatility_threshold
        self.volatility_reduction_pct = volatility_reduction_pct
        self.max_position_duration_minutes = max_position_duration_minutes
        self.close_losing_positions_after_minutes = close_losing_positions_after_minutes
        self.emergency_drawdown_threshold_pct = emergency_drawdown_threshold_pct
        self.emergency_volatility_spike = emergency_volatility_spike
        self.enable_trailing_stop = enable_trailing_stop
        self.trailing_stop_distance_pct = trailing_stop_distance_pct
        self.min_profit_for_trailing_pct = min_profit_for_trailing_pct
        
        # Grupos de correlación (símbolos que se mueven juntos)
        if correlation_groups is None:
            self.correlation_groups = {
                'indices': ['R_10', 'R_25', 'R_50', 'R_75', 'R_100'],
                'crypto': ['cryBTCUSD', 'cryETHUSD'],
                'booms_crashes': ['BOOM500', 'BOOM600', 'BOOM1000', 'CRASH500', 'CRASH600', 'CRASH1000'],
                'jp_indices': ['JD10', 'JD25', 'JD50', 'JD75'],
            }
        else:
            self.correlation_groups = correlation_groups
        
        # Estado de emergencia
        self._emergency_stop_active = False
        self._emergency_stop_reason = None
        self._last_balance_check = None
        self._balance_history = []  # Historial de balances para detectar caídas súbitas
        self._emergency_activation_time = None  # Timestamp cuando se activó la emergencia
    
    def check_portfolio_risk(self, current_balance: Decimal, new_position_risk: Decimal) -> RiskCheckResult:
        """
        Verificar riesgo total del portafolio
        
        Returns:
            RiskCheckResult indicando si se permite la nueva posición
        """
        # Obtener todas las posiciones activas
        active_positions = OrderAudit.objects.filter(
            status__in=['pending', 'active', 'open']
        )
        
        # Calcular riesgo total actual (simplificado: suma de riesgos)
        total_risk = Decimal('0.00')
        position_risks = []
        
        for position in active_positions:
            # Estimar riesgo basado en tamaño de posición
            if hasattr(position, 'risk_amount') and position.risk_amount:
                pos_risk = position.risk_amount
            else:
                # Si no hay risk_amount, estimar desde pnl flotante o usar valor por defecto
                pos_risk = current_balance * Decimal('0.01')  # Asumir 1% por defecto
            
            total_risk += pos_risk
            position_risks.append(float(pos_risk / current_balance * 100))
        
        # Agregar riesgo de la nueva posición
        new_risk_pct = float(new_position_risk / current_balance * 100)
        total_risk_pct = float(total_risk / current_balance * 100) + new_risk_pct
        
        # Verificar límite de portfolio
        if total_risk_pct > self.max_portfolio_risk_pct:
            return RiskCheckResult(
                allowed=False,
                reason=f"Riesgo total del portafolio excedido: {total_risk_pct:.2f}% > {self.max_portfolio_risk_pct}%"
            )
        
        # Verificar límite por posición individual
        if new_risk_pct > self.max_single_position_risk_pct:
            # Reducir tamaño para cumplir límite
            max_allowed_risk = current_balance * Decimal(str(self.max_single_position_risk_pct / 100))
            adjusted_size = min(new_position_risk, max_allowed_risk)
            
            return RiskCheckResult(
                allowed=True,
                adjusted_size=adjusted_size,
                protection_applied=f"Tamaño reducido por límite individual: {new_risk_pct:.2f}% > {self.max_single_position_risk_pct}%"
            )
        
        # Verificar número máximo de posiciones
        if active_positions.count() >= self.max_active_positions:
            return RiskCheckResult(
                allowed=False,
                reason=f"Máximo de posiciones activas alcanzado: {active_positions.count()} >= {self.max_active_positions}"
            )
        
        return RiskCheckResult(allowed=True)
    
    def check_correlation_risk(self, symbol: str, new_position_risk: Decimal, current_balance: Decimal) -> RiskCheckResult:
        """
        Verificar riesgo por correlación (evitar sobreexposición a símbolos relacionados)
        """
        # Encontrar grupo de correlación del símbolo
        symbol_group = None
        for group_name, symbols in self.correlation_groups.items():
            if symbol in symbols:
                symbol_group = group_name
                break
        
        if not symbol_group:
            # Símbolo sin grupo = sin restricción de correlación
            return RiskCheckResult(allowed=True)
        
        # Calcular exposición total en símbolos del mismo grupo
        correlated_symbols = self.correlation_groups[symbol_group]
        correlated_positions = OrderAudit.objects.filter(
            status__in=['pending', 'active', 'open'],
            symbol__in=correlated_symbols
        )
        
        correlated_exposure = Decimal('0.00')
        for position in correlated_positions:
            if hasattr(position, 'risk_amount') and position.risk_amount:
                correlated_exposure += position.risk_amount
            else:
                correlated_exposure += current_balance * Decimal('0.01')
        
        # Agregar nueva posición
        total_correlated_exposure = correlated_exposure + new_position_risk
        correlated_exposure_pct = float(total_correlated_exposure / current_balance * 100)
        
        if correlated_exposure_pct > self.max_correlated_exposure_pct:
            return RiskCheckResult(
                allowed=False,
                reason=f"Exposición correlacionada excedida ({symbol_group}): {correlated_exposure_pct:.2f}% > {self.max_correlated_exposure_pct}%"
            )
        
        return RiskCheckResult(allowed=True)
    
    def get_symbol_volatility(self, symbol: str, hours: int = 24) -> float:
        """
        Calcular volatilidad actual del símbolo (basado en ATR o desviación estándar)
        """
        since = timezone.now() - timedelta(hours=hours)
        ticks = Tick.objects.filter(
            symbol=symbol,
            timestamp__gte=since
        ).order_by('timestamp')[:100]
        
        if ticks.count() < 10:
            return 1.0  # Volatilidad neutral si no hay datos
        
        prices = [float(tick.price) for tick in ticks]
        
        # Calcular volatilidad como desviación estándar de cambios porcentuales
        price_changes = []
        for i in range(1, len(prices)):
            if prices[i-1] != 0:
                change_pct = abs((prices[i] - prices[i-1]) / prices[i-1]) * 100
                price_changes.append(change_pct)
        
        if not price_changes:
            return 1.0
        
        avg_change = statistics.mean(price_changes)
        volatility = statistics.stdev(price_changes) if len(price_changes) > 1 else avg_change
        
        return volatility
    
    def check_volatility_risk(self, symbol: str, base_risk: Decimal) -> RiskCheckResult:
        """
        Verificar y ajustar riesgo basado en volatilidad actual
        """
        current_volatility = self.get_symbol_volatility(symbol)
        
        # Calcular volatilidad promedio (simplificado: usar valor base)
        # En producción, calcular promedio histórico
        avg_volatility = 1.0  # Valor base
        
        volatility_ratio = current_volatility / avg_volatility if avg_volatility > 0 else 1.0
        
        if volatility_ratio > self.high_volatility_threshold:
            # Alta volatilidad: reducir tamaño
            reduction_factor = 1.0 - (self.volatility_reduction_pct / 100.0)
            adjusted_risk = base_risk * Decimal(str(reduction_factor))
            
            return RiskCheckResult(
                allowed=True,
                adjusted_size=adjusted_risk,
                protection_applied=f"Volatilidad alta ({volatility_ratio:.2f}x): tamaño reducido {self.volatility_reduction_pct}%"
            )
        
        return RiskCheckResult(allowed=True)
    
    def check_emergency_conditions(self, current_balance: Decimal) -> Tuple[bool, Optional[str]]:
        """
        Verificar condiciones de emergencia (caída súbita, volatilidad extrema)
        
        Returns:
            (emergency_active, reason)
        """
        now = timezone.now()
        
        # Mantener historial de balances (últimos 10 minutos)
        self._balance_history.append((now, current_balance))
        
        # Limpiar historial antiguo (> 10 minutos)
        cutoff = now - timedelta(minutes=10)
        self._balance_history = [(t, b) for t, b in self._balance_history if t >= cutoff]
        
        if len(self._balance_history) < 2:
            # Si no hay suficiente historial, desactivar emergencia si estaba activa
            if self._emergency_stop_active:
                self._emergency_stop_active = False
                self._emergency_stop_reason = None
            return False, None
        
        # Detectar caída súbita (últimos 5 minutos)
        recent_history = [(t, b) for t, b in self._balance_history if t >= (now - timedelta(minutes=5))]
        if len(recent_history) >= 2:
            # Usar el balance MÁXIMO de los últimos 5 minutos como referencia
            # Esto evita falsos positivos cuando se abren trades (balance disponible baja)
            max_balance = max(b for _, b in recent_history)
            newest_balance = recent_history[-1][1]
            
            if max_balance > 0:
                # Calcular drawdown desde el pico máximo reciente
                drawdown_pct = float((max_balance - newest_balance) / max_balance * 100)
                
                # Verificar si supera el umbral
                if drawdown_pct > self.emergency_drawdown_threshold_pct:
                    # Solo activar si es una caída REAL (no solo trades pendientes)
                    # Si el balance actual es significativamente menor al máximo, es una emergencia real
                    if not self._emergency_stop_active:
                        self._emergency_activation_time = now
                    self._emergency_stop_active = True
                    self._emergency_stop_reason = f"Caída súbita detectada: {drawdown_pct:.2f}% en 5 minutos"
                    return True, self._emergency_stop_reason
                else:
                    # Si el drawdown está por debajo del umbral, desactivar emergencia inmediatamente
                    if self._emergency_stop_active:
                        self._emergency_stop_active = False
                        self._emergency_stop_reason = None
                        self._emergency_activation_time = None
        
        # Si hay emergencia activa pero no hay historial reciente suficiente, verificar timeout
        if self._emergency_stop_active and self._emergency_activation_time:
            # Desactivar automáticamente después de 10 minutos
            if now - self._emergency_activation_time > timedelta(minutes=10):
                self._emergency_stop_active = False
                self._emergency_stop_reason = None
                self._emergency_activation_time = None
                return False, None
        
        # Detectar volatilidad extrema (simplificado: revisar múltiples símbolos)
        # En producción, calcular volatilidad agregada del portafolio
        
        return self._emergency_stop_active, self._emergency_stop_reason
    
    def should_close_stale_position(self, position: OrderAudit) -> Tuple[bool, Optional[str]]:
        """
        Verificar si una posición debe cerrarse por tiempo (sin ganar o perdiendo)
        """
        if position.status not in ['pending', 'active', 'open']:
            return False, None
        
        position_age = timezone.now() - position.timestamp
        
        # Cerrar posiciones perdedoras después de X minutos
        if position_age >= timedelta(minutes=self.close_losing_positions_after_minutes):
            # Verificar si está perdiendo (simplificado: si no ha ganado)
            # En producción, verificar PnL flotante
            return True, f"Posición perdedora abierta más de {self.close_losing_positions_after_minutes} minutos"
        
        # Cerrar posiciones sin ganar después de X minutos
        if position_age >= timedelta(minutes=self.max_position_duration_minutes):
            return True, f"Posición sin ganar por más de {self.max_position_duration_minutes} minutos"
        
        return False, None
    
    def calculate_trailing_stop(self, position: OrderAudit, current_price: Decimal) -> Optional[Decimal]:
        """
        Calcular nuevo stop loss usando trailing stop
        
        Returns:
            Nuevo precio de stop loss, o None si no se aplica
        """
        if not self.enable_trailing_stop:
            return None
        
        # Obtener precio de entrada (simplificado: desde order data)
        entry_price = None
        if hasattr(position, 'entry_price') and position.entry_price:
            entry_price = position.entry_price
        elif position.response_payload:
            entry_price = Decimal(str(position.response_payload.get('buy_price', 0)))
        
        if not entry_price or entry_price == 0:
            return None
        
        # Determinar dirección
        is_long = True  # Simplificado, en producción verificar desde signal/order
        if hasattr(position, 'action'):
            is_long = position.action.upper() == 'BUY' or 'CALL' in str(position.action).upper()
        
        # Calcular ganancia actual
        if is_long:
            profit_pct = float((current_price - entry_price) / entry_price * 100)
        else:
            profit_pct = float((entry_price - current_price) / entry_price * 100)
        
        # Solo aplicar trailing stop si hay ganancia mínima
        if profit_pct < self.min_profit_for_trailing_pct:
            return None
        
        # Calcular nuevo stop loss (trailing)
        if is_long:
            # Para long: stop = precio actual - distancia
            new_stop = current_price * Decimal(str(1 - self.trailing_stop_distance_pct / 100))
            # No permitir que baje del stop original
            if hasattr(position, 'stop_loss') and position.stop_loss:
                new_stop = max(new_stop, position.stop_loss)
        else:
            # Para short: stop = precio actual + distancia
            new_stop = current_price * Decimal(str(1 + self.trailing_stop_distance_pct / 100))
            # No permitir que suba del stop original
            if hasattr(position, 'stop_loss') and position.stop_loss:
                new_stop = min(new_stop, position.stop_loss)
        
        return new_stop
    
    def validate_new_position(self, 
                             symbol: str,
                             base_risk: Decimal,
                             current_balance: Decimal) -> RiskCheckResult:
        """
        Validación completa antes de abrir una nueva posición
        
        Args:
            symbol: Símbolo a operar
            base_risk: Riesgo base calculado
            current_balance: Balance actual
        
        Returns:
            RiskCheckResult con decisión final
        """
        # 1. Verificar condiciones de emergencia
        emergency_active, emergency_reason = self.check_emergency_conditions(current_balance)
        if emergency_active:
            return RiskCheckResult(
                allowed=False,
                reason=f"EMERGENCIA: {emergency_reason}"
            )
        
        # 2. Verificar riesgo de portfolio
        portfolio_check = self.check_portfolio_risk(current_balance, base_risk)
        if not portfolio_check.allowed:
            return portfolio_check
        
        # 3. Verificar correlación
        correlation_check = self.check_correlation_risk(symbol, base_risk, current_balance)
        if not correlation_check.allowed:
            return correlation_check
        
        # 4. Ajustar por volatilidad
        volatility_check = self.check_volatility_risk(symbol, base_risk)
        if volatility_check.adjusted_size:
            # Usar tamaño ajustado para verificaciones finales
            adjusted_risk = volatility_check.adjusted_size
            portfolio_check = self.check_portfolio_risk(current_balance, adjusted_risk)
            if not portfolio_check.allowed:
                return portfolio_check
        
        # 5. Combinar resultados
        final_risk = volatility_check.adjusted_size if volatility_check.adjusted_size else base_risk
        
        protections = []
        if volatility_check.protection_applied:
            protections.append(volatility_check.protection_applied)
        if portfolio_check.protection_applied:
            protections.append(portfolio_check.protection_applied)
        
        return RiskCheckResult(
            allowed=True,
            adjusted_size=final_risk,
            protection_applied=" | ".join(protections) if protections else None
        )
    
    def get_portfolio_metrics(self, current_balance: Decimal) -> PortfolioRiskMetrics:
        """
        Obtener métricas de riesgo del portafolio actual
        """
        active_positions = OrderAudit.objects.filter(
            status__in=['pending', 'active', 'open']
        )
        
        total_risk = Decimal('0.00')
        position_sizes = []
        max_position_risk = 0.0
        
        for position in active_positions:
            if hasattr(position, 'risk_amount') and position.risk_amount:
                pos_risk = position.risk_amount
            else:
                pos_risk = current_balance * Decimal('0.01')
            
            total_risk += pos_risk
            pos_risk_pct = float(pos_risk / current_balance * 100)
            position_sizes.append(pos_risk)
            max_position_risk = max(max_position_risk, pos_risk_pct)
        
        total_exposure_pct = float(total_risk / current_balance * 100) if current_balance > 0 else 0.0
        
        # Calcular exposición correlacionada
        correlated_exposure = Decimal('0.00')
        for group_symbols in self.correlation_groups.values():
            group_positions = active_positions.filter(symbol__in=group_symbols)
            for position in group_positions:
                if hasattr(position, 'risk_amount') and position.risk_amount:
                    correlated_exposure += position.risk_amount
                else:
                    correlated_exposure += current_balance * Decimal('0.01')
        
        correlated_exposure_pct = float(correlated_exposure / current_balance * 100) if current_balance > 0 else 0.0
        
        avg_position_size = Decimal(str(statistics.mean([float(s) for s in position_sizes]))) if position_sizes else Decimal('0.00')
        
        return PortfolioRiskMetrics(
            total_exposure_pct=total_exposure_pct,
            correlated_exposure_pct=correlated_exposure_pct,
            max_position_risk_pct=max_position_risk,
            active_positions_count=active_positions.count(),
            average_position_size=avg_position_size
        )
    
    def reset_emergency_stop(self):
        """Resetear estado de emergencia (usar con precaución)"""
        self._emergency_stop_active = False
        self._emergency_stop_reason = None

