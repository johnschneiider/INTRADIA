"""
Cache de Balance para evitar Rate Limiting
"""

from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional
from django.utils import timezone


class BalanceCache:
    """Cache simple para balance con TTL"""
    
    def __init__(self, ttl_seconds: int = 10):
        self._cached_balance: Optional[Decimal] = None
        self._cache_time: Optional[datetime] = None
        self.ttl_seconds = ttl_seconds
    
    def get(self, fetch_func):
        """
        Obtener balance con cache
        
        Args:
            fetch_func: Función que retorna el balance (puede lanzar excepciones)
        
        Returns:
            Decimal: Balance actual
        """
        now = timezone.now()
        
        # Si el cache es válido, usarlo
        if (self._cached_balance is not None and 
            self._cache_time and 
            (now - self._cache_time).total_seconds() < self.ttl_seconds):
            return self._cached_balance
        
        # Intentar obtener nuevo balance
        try:
            balance_data = fetch_func()
            
            # Manejar diferentes formatos de respuesta
            if isinstance(balance_data, dict):
                if 'balance' in balance_data:
                    balance = Decimal(str(balance_data['balance']))
                elif 'code' in balance_data:
                    # Error (rate limit, etc.) - usar cache si existe
                    if self._cached_balance is not None:
                        return self._cached_balance
                    else:
                        # Fallback: intentar desde último trade
                        from monitoring.models import OrderAudit
                        last_trade = OrderAudit.objects.filter(
                            accepted=True
                        ).order_by('-timestamp').first()
                        if last_trade and last_trade.response_payload:
                            balance_after = last_trade.response_payload.get('balance_after')
                            if balance_after:
                                balance = Decimal(str(balance_after))
                            else:
                                raise ValueError("No balance available")
                        else:
                            raise ValueError("No balance available")
                else:
                    # Formato desconocido
                    raise ValueError(f"Unknown balance format: {balance_data}")
            else:
                balance = Decimal(str(balance_data))
            
            # Actualizar cache
            self._cached_balance = balance
            self._cache_time = now
            
            return balance
            
        except Exception as e:
            # Si hay error y tenemos cache, usar cache
            if self._cached_balance is not None:
                return self._cached_balance
            
            # Si no hay cache, re-lanzar error o usar fallback
            raise
    
    def update(self, balance: Decimal):
        """Actualizar cache manualmente"""
        self._cached_balance = balance
        self._cache_time = timezone.now()
    
    def clear(self):
        """Limpiar cache"""
        self._cached_balance = None
        self._cache_time = None

