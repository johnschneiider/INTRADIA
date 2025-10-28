from django.db import models
from django.utils import timezone


class OrderAudit(models.Model):
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    request_payload = models.JSONField(default=dict)
    response_payload = models.JSONField(default=dict)
    request_hash = models.CharField(max_length=64, db_index=True)
    response_hash = models.CharField(max_length=64, blank=True)
    accepted = models.BooleanField(default=False)
    reason = models.CharField(max_length=128, blank=True)
    
    # Campos adicionales para el dashboard
    symbol = models.CharField(max_length=32, blank=True, db_index=True)
    action = models.CharField(max_length=16, blank=True)  # buy/sell
    size = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)  # entry price
    stop_loss = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    take_profit = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    exit_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    pnl = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    status = models.CharField(max_length=16, default='pending', db_index=True)  # won/lost/active/pending
    latency_ms = models.FloatField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"OrderAudit {self.symbol} {self.action} {self.status} {self.timestamp.isoformat()}"
