from django.contrib import admin
from .models import CapitalConfig

@admin.register(CapitalConfig)
class CapitalConfigAdmin(admin.ModelAdmin):
    list_display = ['profit_target', 'max_loss', 'max_trades', 'profit_target_pct', 'max_loss_pct', 'is_active', 'updated_at']
    list_editable = ['is_active']
    list_filter = ['is_active', 'protect_profits', 'created_at']
    search_fields = []
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Metas Diarias (Valores Fijos)', {
            'fields': ('profit_target', 'max_loss', 'max_trades')
        }),
        ('Metas Diarias (Porcentajes)', {
            'fields': ('profit_target_pct', 'max_loss_pct')
        }),
        ('Protección de Ganancias', {
            'fields': ('protect_profits', 'profit_protection_pct')
        }),
        ('Estado', {
            'fields': ('is_active', 'created_at', 'updated_at')
        }),
    )
