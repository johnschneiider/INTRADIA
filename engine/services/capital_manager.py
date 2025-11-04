"""
Gestor de Capital con Metas Diarias
Maneja límites diarios de ganancia/pérdida y detiene el trading automáticamente
"""

from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, time, timedelta
from typing import Optional, Dict, Any, Tuple
from django.utils import timezone
from django.db.models import Sum
from monitoring.models import OrderAudit


@dataclass
class DailyTargets:
    """Metas diarias de trading"""
    profit_target: Decimal  # Meta de ganancia diaria (ej: $100)
    max_loss: Decimal  # Pérdida máxima permitida (ej: -$50)
    max_trades: int  # Máximo número de trades por día (opcional)
    profit_target_pct: Optional[float] = None  # Meta como % del balance inicial
    max_loss_pct: Optional[float] = None  # Pérdida máxima como % del balance


@dataclass
class DailyStats:
    """Estadísticas del día actual"""
    start_balance: Decimal
    current_balance: Decimal
    daily_pnl: Decimal
    trades_count: int
    won_trades: int
    lost_trades: int
    active_trades: int
    profit_target_reached: bool
    max_loss_reached: bool
    should_stop: bool
    reason_to_stop: Optional[str] = None


class CapitalManager:
    """
    Gestor de Capital con sistema de metas diarias
    
    Funcionalidades:
    - Establece metas diarias de ganancia
    - Limita pérdidas diarias
    - Detiene el trading automáticamente al alcanzar metas
    - Reinicia contadores diariamente
    - Opción de protección de ganancias (stop de ganancias)
    """
    
    def __init__(self,
                 profit_target: Decimal = Decimal('100.00'),
                 max_loss: Decimal = Decimal('-50.00'),
                 max_trades: Optional[int] = None,
                 profit_target_pct: Optional[float] = 2.0,  # 2% del balance
                 max_loss_pct: Optional[float] = 1.0,  # 1% del balance máximo
                 protect_profits: bool = True,
                 profit_protection_pct: float = 0.5):  # Proteger 50% de ganancias al alcanzar meta
        """
        Inicializar gestor de capital
        
        Args:
            profit_target: Meta de ganancia diaria absoluta
            max_loss: Pérdida máxima diaria permitida
            max_trades: Máximo número de trades por día (opcional)
            profit_target_pct: Meta como porcentaje del balance inicial
            max_loss_pct: Pérdida máxima como porcentaje del balance
            protect_profits: Si True, activa protección de ganancias
            profit_protection_pct: % de ganancias a proteger cuando se alcanza la meta
        """
        # max_trades siempre ilimitado para operación perpetua
        self.targets = DailyTargets(
            profit_target=profit_target,
            max_loss=max_loss,
            max_trades=999999,  # Siempre ilimitado
            profit_target_pct=profit_target_pct,
            max_loss_pct=max_loss_pct
        )
        self.protect_profits = protect_profits
        self.profit_protection_pct = profit_protection_pct
        
        # Cache de balance inicial del día
        self._daily_start_balance: Optional[Decimal] = None
        self._daily_reset_time: Optional[datetime] = None
    
    def get_start_balance(self, current_balance: Decimal) -> Decimal:
        """Obtener balance inicial del día (resetea a medianoche)"""
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Si es un nuevo día o primera vez, obtener balance inicial
        if (self._daily_reset_time is None or 
            self._daily_reset_time < today_start):
            # Buscar el balance al inicio del día
            first_trade_today = OrderAudit.objects.filter(
                timestamp__gte=today_start
            ).order_by('timestamp').first()
            
            if first_trade_today and first_trade_today.response_payload:
                # Intentar obtener balance del primer trade
                balance_after = first_trade_today.response_payload.get('balance_after')
                if balance_after:
                    self._daily_start_balance = Decimal(str(balance_after))
                else:
                    # Si no hay trades hoy, usar balance actual
                    self._daily_start_balance = current_balance
            else:
                # Si no hay trades hoy, usar balance actual
                self._daily_start_balance = current_balance
            
            self._daily_reset_time = today_start
        
        return self._daily_start_balance
    
    def calculate_daily_pnl(self) -> Decimal:
        """
        Calcular P&L del día actual basado en trades cerrados
        """
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Sumar P&L de trades cerrados hoy
        closed_trades = OrderAudit.objects.filter(
            timestamp__gte=today_start,
            status__in=['won', 'lost'],
            pnl__isnull=False
        )
        
        daily_pnl = closed_trades.aggregate(
            total_pnl=Sum('pnl')
        )['total_pnl'] or Decimal('0.00')
        
        return Decimal(str(daily_pnl))
    
    def get_daily_stats(self, current_balance: Decimal) -> DailyStats:
        """
        Obtener estadísticas completas del día
        
        Args:
            current_balance: Balance actual de la cuenta
            
        Returns:
            DailyStats con toda la información del día
        """
        start_balance = self.get_start_balance(current_balance)
        daily_pnl = self.calculate_daily_pnl()
        
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Contar trades del día
        today_trades = OrderAudit.objects.filter(timestamp__gte=today_start)
        trades_count = today_trades.count()
        won_trades = today_trades.filter(status='won').count()
        lost_trades = today_trades.filter(status='lost').count()
        active_trades = today_trades.filter(status__in=['pending', 'active']).count()
        
        # Calcular metas dinámicas si se usan porcentajes
        profit_target = self.targets.profit_target
        max_loss = self.targets.max_loss
        
        if self.targets.profit_target_pct:
            profit_target = max(
                profit_target,
                start_balance * Decimal(str(self.targets.profit_target_pct / 100))
            )
        
        # Calcular max_loss considerando porcentaje (solo si max_loss_pct está definido)
        # max_loss_pct calcula un límite negativo, así que usamos min() para obtener el más restrictivo
        # Nota: Si stop_loss_amount está activo, max_loss_pct debería ser None
        if self.targets.max_loss_pct is not None:
            pct_loss = -abs(start_balance * Decimal(str(self.targets.max_loss_pct / 100)))
            # Usar min() porque ambos son negativos, queremos el más negativo (más restrictivo)
            max_loss = min(max_loss, pct_loss)
        
        # Verificar si se alcanzaron las metas
        profit_target_reached = daily_pnl >= profit_target
        max_loss_reached = daily_pnl <= max_loss
        # LÍMITE DE TRADES DESACTIVADO: Operación perpetua sin límite
        max_trades_reached = False  # Siempre False para operación ilimitada
        
        # Decidir si debe detenerse
        should_stop = False
        reason_to_stop = None
        
        if profit_target_reached:
            should_stop = True
            reason_to_stop = f"Meta de ganancia alcanzada: ${daily_pnl:.2f} >= ${profit_target:.2f}"
        # Límite de trades eliminado - operación perpetua
        
        # Protección de ganancias: si ya alcanzó la meta pero sigue operando
        # y las pérdidas amenazan las ganancias, detener
        if self.protect_profits and profit_target_reached:
            protection_threshold = profit_target * Decimal(str(self.profit_protection_pct))
            if daily_pnl < protection_threshold:
                should_stop = True
                reason_to_stop = f"Protección de ganancias activada: ${daily_pnl:.2f} < ${protection_threshold:.2f}"
        
        return DailyStats(
            start_balance=start_balance,
            current_balance=current_balance,
            daily_pnl=daily_pnl,
            trades_count=trades_count,
            won_trades=won_trades,
            lost_trades=lost_trades,
            active_trades=active_trades,
            profit_target_reached=profit_target_reached,
            max_loss_reached=max_loss_reached,
            should_stop=should_stop,
            reason_to_stop=reason_to_stop
        )
    
    def can_trade(self, current_balance: Decimal) -> Tuple[bool, Optional[str]]:
        """
        Verificar si se puede realizar un nuevo trade
        
        Args:
            current_balance: Balance actual
            
        Returns:
            Tupla (puede_trade, razon_si_no)
        """
        stats = self.get_daily_stats(current_balance)
        
        if stats.should_stop:
            return False, stats.reason_to_stop
        
        return True, None
    
    def get_status_message(self, current_balance: Decimal) -> str:
        """
        Obtener mensaje de estado del día para logging
        
        Args:
            current_balance: Balance actual
            
        Returns:
            Mensaje formateado con el estado
        """
        stats = self.get_daily_stats(current_balance)
        
        # Calcular metas dinámicas
        profit_target = self.targets.profit_target
        max_loss = self.targets.max_loss
        
        if self.targets.profit_target_pct:
            profit_target = max(
                profit_target,
                stats.start_balance * Decimal(str(self.targets.profit_target_pct / 100))
            )
        
        if self.targets.max_loss_pct:
            max_loss = max(
                max_loss,
                -abs(stats.start_balance * Decimal(str(self.targets.max_loss_pct / 100)))
            )
        
        # Porcentaje de progreso hacia la meta
        if profit_target > 0:
            progress_pct = (stats.daily_pnl / profit_target) * 100
        else:
            progress_pct = 0
        
        status_emoji = "✅" if not stats.should_stop else "🛑"
        
        message = (
            f"{status_emoji} Capital Manager | "
            f"P&L: ${stats.daily_pnl:.2f} | "
            f"Meta: ${profit_target:.2f} ({progress_pct:.1f}%) | "
            f"Límite pérdida: ${max_loss:.2f} | "
            f"Trades: {stats.trades_count}/∞ | "
            f"Win Rate: {(stats.won_trades/stats.trades_count*100):.1f}%" if stats.trades_count > 0 else "Win Rate: 0%"
        )
        
        if stats.should_stop:
            message += f" | 🛑 DETENIDO: {stats.reason_to_stop}"
        
        return message
    
    def should_stop_trading(self, current_balance: Decimal) -> bool:
        """
        Método de conveniencia para verificar si debe detenerse
        
        Args:
            current_balance: Balance actual
            
        Returns:
            True si debe detener el trading
        """
        stats = self.get_daily_stats(current_balance)
        return stats.should_stop
    
    @property
    def max_trades(self) -> int:
        """Propiedad para compatibilidad - siempre retorna ilimitado"""
        return 999999
    
    @max_trades.setter
    def max_trades(self, value: int):
        """Setter para compatibilidad - actualiza targets pero siempre mantiene ilimitado"""
        self.targets.max_trades = 999999  # Siempre ilimitado

