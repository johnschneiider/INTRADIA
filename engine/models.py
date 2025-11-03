from django.db import models
from decimal import Decimal

# Si el archivo ya existe, agregar al final
# Si no existe, crear desde cero

class CapitalConfig(models.Model):
    """Configuración del Gestor de Capital"""
    
    # Metas diarias (valores fijos)
    profit_target = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        default=Decimal('100.00'),
        help_text="Meta de ganancia diaria en USD"
    )
    max_loss = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('-50.00'),
        help_text="Pérdida máxima diaria en USD"
    )
    max_trades = models.IntegerField(
        default=50,
        help_text="Máximo número de trades por día"
    )
    
    # Metas diarias (porcentajes)
    profit_target_pct = models.FloatField(
        default=5.0,
        help_text="Meta de ganancia diaria como porcentaje del balance inicial"
    )
    max_loss_pct = models.FloatField(
        default=1.0,
        help_text="Pérdida máxima diaria como porcentaje del balance inicial"
    )
    
    # Protección de ganancias
    protect_profits = models.BooleanField(
        default=True,
        help_text="Activar protección de ganancias"
    )
    profit_protection_pct = models.FloatField(
        default=0.5,
        help_text="Porcentaje de ganancia a proteger (0.5 = 50%)"
    )
    
    # === CONFIGURACIÓN RÁPIDA PARA PRUEBAS ===
    disable_max_trades = models.BooleanField(
        default=False,
        help_text="Desactivar límite de trades (útil para pruebas)"
    )
    disable_profit_target = models.BooleanField(
        default=False,
        help_text="Desactivar meta de ganancia (útil para pruebas)"
    )
    stop_loss_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Monto de pérdida para cerrar trading (0 = desactivado)"
    )
    
    # Metadatos
    is_active = models.BooleanField(
        default=True,
        help_text="Configuración activa"
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Configuración de Capital"
        verbose_name_plural = "Configuraciones de Capital"
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"Capital Config - Profit: ${self.profit_target} | Loss: ${self.max_loss} | Trades: {self.max_trades}"
    
    # Estrategias avanzadas de position sizing
    POSITION_SIZING_CHOICES = [
        ('kelly', 'Kelly Criterion (Óptimo)'),
        ('kelly_fractional', 'Kelly Fractional (Conservador)'),
        ('fixed_fractional', 'Fixed Fractional (Porcentaje Fijo)'),
        ('anti_martingale', 'Anti-Martingala (Aumentar tras ganancias)'),
        ('martingale', 'Martingala (Aumentar tras pérdidas)'),
        ('volatility', 'Volatility-Based (Basado en ATR)'),
        ('risk_parity', 'Risk Parity (Riesgo Equitativo)'),
    ]
    
    position_sizing_method = models.CharField(
        max_length=20,
        choices=POSITION_SIZING_CHOICES,
        default='kelly_fractional',
        help_text="Método de cálculo de tamaño de posición"
    )
    
    # Kelly Criterion
    kelly_fraction = models.FloatField(
        default=0.25,
        help_text="Fracción del Kelly óptimo a usar (0.25 = 25%, más conservador)"
    )
    
    # Fixed Fractional
    risk_per_trade_pct = models.FloatField(
        default=1.0,
        help_text="Porcentaje del capital a arriesgar por trade (Fixed Fractional)"
    )
    
    # Anti-Martingala
    anti_martingale_multiplier = models.FloatField(
        default=1.5,
        help_text="Multiplicador después de ganancia (Anti-Martingala)"
    )
    anti_martingale_reset_on_loss = models.BooleanField(
        default=True,
        help_text="Resetear a tamaño base después de pérdida"
    )
    
    # Martingala (Aumentar después de pérdidas)
    enable_martingale = models.BooleanField(
        default=False,
        help_text="Activar sistema de martingala (aumentar monto después de pérdidas)"
    )
    martingale_multiplier = models.FloatField(
        default=2.0,
        help_text="Multiplicador de martingala después de pérdida (2.0 = duplicar)"
    )
    martingale_base_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.10'),
        help_text="Monto base para martingala ($0.10)"
    )
    martingale_max_levels = models.IntegerField(
        default=5,
        help_text="Profundidad máxima de martingala (niveles antes de resetear)"
    )
    martingale_reset_on_win = models.BooleanField(
        default=True,
        help_text="Resetear martingala después de ganancia"
    )
    
    # Volatility-Based
    atr_multiplier = models.FloatField(
        default=2.0,
        help_text="Multiplicador del ATR para stop loss"
    )
    max_risk_per_trade_pct = models.FloatField(
        default=2.0,
        help_text="Máximo riesgo por trade como % del capital"
    )
    
    # Drawdown Protection
    max_drawdown_pct = models.FloatField(
        default=10.0,
        help_text="Drawdown máximo permitido (%)"
    )
    reduce_size_on_drawdown = models.BooleanField(
        default=True,
        help_text="Reducir tamaño de posición durante drawdown"
    )
    
    # Value at Risk
    var_confidence = models.FloatField(
        default=0.95,
        help_text="Nivel de confianza para VaR (0.95 = 95%)"
    )
    
    # Portfolio
    max_concurrent_positions = models.IntegerField(
        default=5,
        help_text="Máximo de posiciones simultáneas"
    )
    
    # Risk Parity
    target_volatility = models.FloatField(
        default=15.0,
        help_text="Volatilidad objetivo para Risk Parity (%)"
    )
    
    # === PROTECCIONES AVANZADAS DE RIESGO ===
    
    # Portfolio Risk Limits
    max_portfolio_risk_pct = models.FloatField(
        default=15.0,
        help_text="Máximo riesgo total del portafolio (%)"
    )
    max_single_position_risk_pct = models.FloatField(
        default=5.0,
        help_text="Máximo riesgo por posición individual (%)"
    )
    max_correlated_exposure_pct = models.FloatField(
        default=10.0,
        help_text="Máxima exposición a símbolos correlacionados (%)"
    )
    max_active_positions = models.IntegerField(
        default=10,
        help_text="Máximo número de posiciones simultáneas"
    )
    
    # Volatility Protection
    enable_volatility_scaling = models.BooleanField(
        default=True,
        help_text="Ajustar tamaño según volatilidad"
    )
    high_volatility_threshold = models.FloatField(
        default=2.0,
        help_text="Umbral de alta volatilidad (múltiplo del promedio)"
    )
    volatility_reduction_pct = models.FloatField(
        default=50.0,
        help_text="Reducción de tamaño en alta volatilidad (%)"
    )
    
    # Time-Based Protection
    enable_time_based_stops = models.BooleanField(
        default=True,
        help_text="Cerrar posiciones estancadas automáticamente"
    )
    max_position_duration_minutes = models.IntegerField(
        default=60,
        help_text="Cerrar posición si no gana después de X minutos"
    )
    close_losing_positions_after_minutes = models.IntegerField(
        default=30,
        help_text="Cerrar posiciones perdedoras después de X minutos"
    )
    
    # Emergency Stop
    enable_emergency_stop = models.BooleanField(
        default=True,
        help_text="Detener trading en caídas súbitas"
    )
    emergency_drawdown_threshold_pct = models.FloatField(
        default=10.0,  # Aumentado de 5.0 a 10.0 para no activar muy temprano
        help_text="Drawdown máximo en 5 min para activar emergencia (%)"
    )
    
    # Trailing Stop Loss
    enable_trailing_stop = models.BooleanField(
        default=True,
        help_text="Protección automática de ganancias (trailing stop)"
    )
    trailing_stop_distance_pct = models.FloatField(
        default=1.0,
        help_text="Distancia del trailing stop (%)"
    )
    min_profit_for_trailing_pct = models.FloatField(
        default=0.5,
        help_text="Ganancia mínima para activar trailing stop (%)"
    )
    
    # === CONFIGURACIONES DE TRADING (Amounts y Límites) ===
    
    # Límites de amount por símbolo (almacenados como JSON)
    symbol_amount_limits = models.JSONField(
        default=dict,
        blank=True,
        help_text="Límites de amount máximo por símbolo (ej: {'RDBULL': 100.0, 'RDBEAR': 100.0})"
    )
    
    # Límite porcentual del balance
    max_amount_pct_balance = models.FloatField(
        default=5.0,
        help_text="Máximo amount como % del balance (5% = muy conservador)"
    )
    
    # Límite absoluto máximo
    max_amount_absolute = models.FloatField(
        default=500.0,
        help_text="Límite absoluto máximo de amount"
    )
    
    # Amount mínimo por trade
    min_amount_per_trade = models.FloatField(
        default=1.0,
        help_text="Amount mínimo permitido por trade"
    )
    
    # Intervalo mínimo entre trades del mismo símbolo (segundos)
    min_trade_interval_seconds = models.IntegerField(
        default=60,
        help_text="Tiempo mínimo entre trades del mismo símbolo (segundos)"
    )
    
    # Duración de contratos por defecto (segundos)
    default_duration_forex = models.IntegerField(
        default=900,
        help_text="Duración por defecto para forex (segundos)"
    )
    default_duration_metals = models.IntegerField(
        default=300,
        help_text="Duración por defecto para metales (segundos)"
    )
    default_duration_indices = models.IntegerField(
        default=30,
        help_text="Duración por defecto para índices (segundos)"
    )
    
    @classmethod
    def get_active(cls):
        """Obtener la configuración activa, crear una por defecto si no existe"""
        config = cls.objects.filter(is_active=True).first()
        if not config:
            config = cls.objects.create()
            # Inicializar límites por defecto
            config.symbol_amount_limits = {
                'RDBULL': 100.0,
                'RDBEAR': 100.0,
                'R_100': 200.0,
                'R_75': 300.0,
                'R_50': 400.0,
                'R_25': 400.0,
                'R_10': 400.0,
            }
            config.save()
        return config
    
    def get_symbol_limit(self, symbol: str) -> float:
        """Obtener límite de amount para un símbolo específico"""
        if not self.symbol_amount_limits:
            return None
        
        # Buscar por prefijo
        for sym_prefix, limit in self.symbol_amount_limits.items():
            if symbol.startswith(sym_prefix):
                return float(limit)
        return None
