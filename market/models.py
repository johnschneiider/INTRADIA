from django.db import models


class Timeframe(models.TextChoices):
    M1 = '1m', '1m'
    M5 = '5m', '5m'
    M15 = '15m', '15m'
    H1 = '1h', '1h'
    D1 = '1d', '1d'
    W1 = '1w', '1w'


class ZonePeriod(models.TextChoices):
    DAY = 'DAY', 'DAY'
    WEEK = 'WEEK', 'WEEK'


class Candle(models.Model):
    symbol = models.CharField(max_length=32, db_index=True)
    timeframe = models.CharField(max_length=8, choices=Timeframe.choices, db_index=True)
    timestamp = models.DateTimeField(db_index=True)
    open = models.DecimalField(max_digits=20, decimal_places=8)
    high = models.DecimalField(max_digits=20, decimal_places=8)
    low = models.DecimalField(max_digits=20, decimal_places=8)
    close = models.DecimalField(max_digits=20, decimal_places=8)
    volume = models.DecimalField(max_digits=24, decimal_places=8, default=0)

    class Meta:
        unique_together = ('symbol', 'timeframe', 'timestamp')
        indexes = [
            models.Index(fields=['symbol', 'timeframe', 'timestamp']),
        ]

    def __str__(self) -> str:
        return f"{self.symbol} {self.timeframe} {self.timestamp.isoformat()}"


class Zone(models.Model):
    symbol = models.CharField(max_length=32, db_index=True)
    zone_period = models.CharField(max_length=8, choices=ZonePeriod.choices, db_index=True)
    zone_low = models.DecimalField(max_digits=20, decimal_places=8)
    zone_high = models.DecimalField(max_digits=20, decimal_places=8)
    timestamp = models.DateTimeField(help_text='Periodo al que corresponde la zona', db_index=True)
    zone_height = models.DecimalField(max_digits=20, decimal_places=8)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['symbol', 'zone_period', 'timestamp']),
        ]

    def __str__(self) -> str:
        return f"Zone {self.zone_period} {self.symbol} [{self.zone_low}, {self.zone_high}] @ {self.timestamp.date()}"


class LiquiditySweep(models.Model):
    symbol = models.CharField(max_length=32, db_index=True)
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name='sweeps')
    sweep_time = models.DateTimeField(db_index=True)
    direction = models.CharField(max_length=8, choices=(('long', 'long'), ('short', 'short')))
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['symbol', 'sweep_time']),
        ]

    def __str__(self) -> str:
        return f"Sweep {self.direction} {self.symbol} at {self.sweep_time.isoformat()}"


class Tick(models.Model):
    symbol = models.CharField(max_length=32, db_index=True)
    timestamp = models.DateTimeField(db_index=True)
    price = models.DecimalField(max_digits=20, decimal_places=8)
    volume = models.DecimalField(max_digits=24, decimal_places=8, default=0)

    class Meta:
        unique_together = ('symbol', 'timestamp')
        indexes = [
            models.Index(fields=['symbol', 'timestamp']),
        ]

    def __str__(self) -> str:
        return f"{self.symbol} {self.price} @ {self.timestamp.isoformat()}"
