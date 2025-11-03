from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class DerivAPIConfig(models.Model):
    """Configuración de la API de Deriv para cada usuario"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='deriv_config')
    api_token = models.CharField(max_length=255, help_text="Token de API de Deriv")
    app_id = models.CharField(max_length=50, default="1089", help_text="App ID de Deriv")
    is_demo = models.BooleanField(default=True, help_text="¿Usar cuenta demo?")
    
    # NOTA: Los campos scope_* fueron removidos por migración 0003
    # No deben usarse en el modelo porque no existen en la BD
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración API Deriv"
        verbose_name_plural = "Configuraciones API Deriv"

    def __str__(self):
        return f"{self.user.username} - {'Demo' if self.is_demo else 'Real'}"


class TradingStrategy(models.Model):
    """Estrategias de trading predefinidas"""
    STRATEGY_TYPES = [
        ('martingale', 'Martingala'),
        ('fibonacci', 'Fibonacci'),
        ('fixed', 'Monto Fijo'),
        ('percentage', 'Porcentaje del Balance'),
        ('trend_following', 'Seguimiento de Tendencia'),
        ('mean_reversion', 'Reversión a la Media'),
        ('breakout', 'Ruptura de Niveles'),
        ('custom', 'Personalizada'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='strategies')
    name = models.CharField(max_length=100)
    strategy_type = models.CharField(max_length=50, choices=STRATEGY_TYPES)
    description = models.TextField(blank=True)
    
    # Configuración general
    initial_stake = models.DecimalField(max_digits=10, decimal_places=2, default=1.0)
    max_stake = models.DecimalField(max_digits=10, decimal_places=2, default=100.0)
    stop_loss = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    take_profit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Configuración específica (JSON)
    config = models.JSONField(default=dict, help_text="Configuración específica de la estrategia")
    
    # Estadísticas
    total_trades = models.IntegerField(default=0)
    winning_trades = models.IntegerField(default=0)
    losing_trades = models.IntegerField(default=0)
    total_profit = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Estrategia de Trading"
        verbose_name_plural = "Estrategias de Trading"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.get_strategy_type_display()})"

    def win_rate(self):
        if self.total_trades == 0:
            return 0
        return (self.winning_trades / self.total_trades) * 100


class TradingBot(models.Model):
    """Bot de trading automatizado"""
    STATUS_CHOICES = [
        ('stopped', 'Detenido'),
        ('running', 'Ejecutando'),
        ('paused', 'Pausado'),
        ('error', 'Error'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bots')
    name = models.CharField(max_length=100)
    strategy = models.ForeignKey(TradingStrategy, on_delete=models.SET_NULL, null=True)
    
    # Configuración del bot
    symbol = models.CharField(max_length=50, default="R_100", help_text="Símbolo a operar (ej: R_100, EURUSD)")
    contract_type = models.CharField(max_length=50, default="CALL", help_text="Tipo de contrato")
    duration = models.IntegerField(default=1, help_text="Duración en minutos")
    duration_unit = models.CharField(max_length=10, default="m", help_text="Unidad de duración (s, m, h)")
    
    # Control de riesgo
    max_daily_loss = models.DecimalField(max_digits=10, decimal_places=2, default=50.0)
    max_daily_trades = models.IntegerField(default=100)
    daily_profit_target = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Estado
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='stopped')
    is_active = models.BooleanField(default=True)
    
    # Estadísticas del día
    today_trades = models.IntegerField(default=0)
    today_profit = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    today_wins = models.IntegerField(default=0)
    today_losses = models.IntegerField(default=0)
    last_trade_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    started_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Bot de Trading"
        verbose_name_plural = "Bots de Trading"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.symbol} ({self.get_status_display()})"

    def start(self):
        self.status = 'running'
        self.started_at = timezone.now()
        self.save()

    def stop(self):
        self.status = 'stopped'
        self.stopped_at = timezone.now()
        self.save()

    def pause(self):
        self.status = 'paused'
        self.save()

    def reset_daily_stats(self):
        self.today_trades = 0
        self.today_profit = 0.0
        self.today_wins = 0
        self.today_losses = 0
        self.save()


class Trade(models.Model):
    """Registro de operaciones individuales"""
    TRADE_STATUS = [
        ('pending', 'Pendiente'),
        ('open', 'Abierta'),
        ('won', 'Ganada'),
        ('lost', 'Perdida'),
        ('cancelled', 'Cancelada'),
    ]

    bot = models.ForeignKey(TradingBot, on_delete=models.CASCADE, related_name='trades')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trades')
    
    # Información del trade
    contract_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    symbol = models.CharField(max_length=50)
    contract_type = models.CharField(max_length=50)
    
    # Precios
    entry_price = models.DecimalField(max_digits=15, decimal_places=5)
    exit_price = models.DecimalField(max_digits=15, decimal_places=5, null=True, blank=True)
    stake = models.DecimalField(max_digits=10, decimal_places=2)
    payout = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    profit = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    
    # Duración
    duration = models.IntegerField()
    duration_unit = models.CharField(max_length=10)
    
    # Estado
    status = models.CharField(max_length=20, choices=TRADE_STATUS, default='pending')
    
    # Timestamps
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    
    # Información adicional
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Trade"
        verbose_name_plural = "Trades"
        ordering = ['-opened_at']

    def __str__(self):
        return f"{self.symbol} - {self.contract_type} - {self.status}"

    def mark_as_won(self, exit_price, payout):
        self.status = 'won'
        self.exit_price = exit_price
        self.payout = payout
        self.profit = payout - self.stake
        self.closed_at = timezone.now()
        self.save()
        
        # Actualizar estadísticas del bot
        self.bot.today_wins += 1
        self.bot.today_trades += 1
        self.bot.today_profit += self.profit
        self.bot.last_trade_at = timezone.now()
        self.bot.save()

    def mark_as_lost(self, exit_price):
        self.status = 'lost'
        self.exit_price = exit_price
        self.payout = 0
        self.profit = -self.stake
        self.closed_at = timezone.now()
        self.save()
        
        # Actualizar estadísticas del bot
        self.bot.today_losses += 1
        self.bot.today_trades += 1
        self.bot.today_profit += self.profit
        self.bot.last_trade_at = timezone.now()
        self.bot.save()


class BotLog(models.Model):
    """Registro de eventos y logs del bot"""
    LOG_LEVELS = [
        ('info', 'Info'),
        ('warning', 'Advertencia'),
        ('error', 'Error'),
        ('success', 'Éxito'),
    ]

    bot = models.ForeignKey(TradingBot, on_delete=models.CASCADE, related_name='logs')
    level = models.CharField(max_length=20, choices=LOG_LEVELS)
    message = models.TextField()
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Log del Bot"
        verbose_name_plural = "Logs de Bots"
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.level.upper()}] {self.bot.name} - {self.message[:50]}"
