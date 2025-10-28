from django.db import models
from django.utils import timezone


class PolicyState(models.Model):
    MODE_CHOICES = (
        ('rule', 'rule'),
        ('rl', 'rl'),
    )
    mode = models.CharField(max_length=8, choices=MODE_CHOICES, default='rule')
    shadow_enabled = models.BooleanField(default=True)
    last_promoted_at = models.DateTimeField(null=True, blank=True)
    metrics = models.JSONField(default=dict, blank=True)

    def promote_to_rl(self, metrics: dict):
        self.mode = 'rl'
        self.shadow_enabled = False
        self.metrics = metrics
        self.last_promoted_at = timezone.now()
        self.save()

    def __str__(self) -> str:
        return f"PolicyState mode={self.mode} shadow={self.shadow_enabled}"
