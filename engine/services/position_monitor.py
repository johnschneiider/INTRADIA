"""
Monitor de Posiciones Activas
Aplica trailing stops y cierres basados en tiempo
"""

from __future__ import annotations
from datetime import timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional
from django.utils import timezone
from monitoring.models import OrderAudit
from engine.services.risk_protection import RiskProtectionSystem
from connectors.deriv_client import DerivClient


class PositionMonitor:
    """
    Monitorea y gestiona posiciones activas:
    - Aplica trailing stops
    - Cierra posiciones estancadas
    - Cierra posiciones perdedoras por tiempo
    """
    
    def __init__(self, risk_protection: RiskProtectionSystem):
        self.risk_protection = risk_protection
        self._client = None
    
    def monitor_active_positions(self) -> List[Dict[str, Any]]:
        """
        Monitorear y gestionar todas las posiciones activas
        
        Returns:
            Lista de acciones tomadas (cierre de posiciones, trailing stops, etc.)
        """
        actions_taken = []
        
        # Obtener todas las posiciones activas
        active_positions = OrderAudit.objects.filter(
            status__in=['pending', 'active', 'open']
        )
        
        if not self._client:
            self._client = DerivClient()
        
        for position in active_positions:
            try:
                # Verificar si el contrato ha expirado en Deriv (primera verificación)
                contract_id = self._get_contract_id(position)
                if contract_id:
                    contract_info = self._client.get_open_contract_info(contract_id)
                    # Verificar si hay información útil del contrato (expiró o se vendió)
                    if contract_info and not contract_info.get('error'):
                        # Solo actualizar si el contrato ya expiró/se vendió (tiene status determinable)
                        if 'status' in contract_info and contract_info['status'] in ['won', 'lost']:
                            # El contrato se vendió/cerró, actualizar status
                            self._update_position_status(position, contract_info)
                            actions_taken.append({
                                'action': 'contract_expired',
                                'position_id': position.id,
                                'symbol': position.symbol,
                                'status': contract_info.get('status', 'unknown')
                            })
                            continue
                
                # Verificar si debe cerrarse por tiempo
                should_close, reason = self.risk_protection.should_close_stale_position(position)
                
                if should_close:
                    # Intentar cerrar posición
                    close_result = self._close_position(position, reason)
                    if close_result:
                        actions_taken.append({
                            'action': 'closed_by_time',
                            'position_id': position.id,
                            'symbol': position.symbol,
                            'reason': reason
                        })
                    continue
                
                # Aplicar trailing stop si está habilitado
                if self.risk_protection.enable_trailing_stop:
                    # Obtener precio actual
                    latest_tick = self._get_current_price(position.symbol)
                    if latest_tick:
                        new_stop = self.risk_protection.calculate_trailing_stop(
                            position, 
                            Decimal(str(latest_tick.price))
                        )
                        
                        if new_stop:
                            # En opciones binarias no se puede modificar el stop,
                            # pero podemos registrar la sugerencia
                            actions_taken.append({
                                'action': 'trailing_stop_suggested',
                                'position_id': position.id,
                                'symbol': position.symbol,
                                'suggested_stop': float(new_stop)
                            })
                            
            except Exception as e:
                actions_taken.append({
                    'action': 'error',
                    'position_id': position.id,
                    'error': str(e)
                })
        
        return actions_taken
    
    def _get_contract_id(self, position: OrderAudit) -> Optional[str]:
        """Obtener contract_id de una posición"""
        try:
            # El contract_id se guarda en response_payload cuando se acepta el trade
            if position.response_payload and isinstance(position.response_payload, dict):
                # Puede estar en 'contract_id', 'order_id', 'buy', o directamente en el payload
                contract_id = (
                    position.response_payload.get('contract_id') or
                    position.response_payload.get('order_id') or
                    position.response_payload.get('buy', {}).get('contract_id') if isinstance(position.response_payload.get('buy'), dict) else None
                )
                return contract_id
            return None
        except Exception:
            return None
    
    def _update_position_status(self, position: OrderAudit, contract_info: Dict[str, Any]) -> bool:
        """
        Actualizar el status de una posición cuando el contrato expira
        """
        try:
            status = contract_info.get('status', 'unknown')
            profit = contract_info.get('profit', 0)
            
            # Actualizar campos de la posición
            old_status = position.status
            position.status = status if status in ['won', 'lost'] else 'lost'
            position.pnl = Decimal(str(profit))
            position.exit_price = position.price  # El exit price es el mismo para opciones binarias
            
            # Guardar cambios
            position.save(update_fields=['status', 'pnl', 'exit_price'])
            
            # Actualizar martingala si cambió de pending a won/lost
            # Nota: La actualización de martingala se hace desde el trading loop
            # cuando verifica los trades completados en cada iteración
            
            print(f"✅ {position.symbol} {position.action.upper()} {status.upper()} | P&L: ${profit:.2f}")
            return True
        except Exception as e:
            print(f"❌ Error actualizando posición {position.id}: {e}")
            return False
    
    def _get_current_price(self, symbol: str) -> Optional[Any]:
        """Obtener precio actual del símbolo"""
        try:
            from market.models import Tick
            latest = Tick.objects.filter(symbol=symbol).order_by('-timestamp').first()
            return latest
        except Exception:
            return None
    
    def _close_position(self, position: OrderAudit, reason: str) -> bool:
        """
        Cerrar una posición manualmente
        
        Nota: En opciones binarias de Deriv, las posiciones se cierran automáticamente
        al vencer. Este método es principalmente para logging y futuro soporte de 
        contratos que permitan cierre anticipado.
        """
        # Para opciones binarias, solo podemos registrar la intención
        # Las posiciones se cerrarán automáticamente al vencer
        try:
            # Aquí se podría implementar lógica de cierre anticipado si Deriv lo permite
            # Por ahora, solo registramos la intención
            return False  # No se puede cerrar anticipadamente en opciones binarias estándar
        except Exception:
            return False

