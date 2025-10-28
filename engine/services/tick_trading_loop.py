"""
Bucle principal para trading basado en ticks en tiempo real
"""

from __future__ import annotations
import json
from typing import Optional, Dict, Any
from datetime import timedelta

from django.utils import timezone
from market.models import Tick

from engine.services.tick_based_strategy import TickBasedStrategy, TrendSignal
from engine.services.statistical_strategy import StatisticalStrategy, StatisticalSignal
from engine.services.execution_gateway import place_order_through_gateway
from monitoring.models import OrderAudit


class TickTradingLoop:
    """Bucle de trading basado en ticks"""
    
    def __init__(self, use_statistical=True):
        # NUEVA ESTRATEGIA ESTADÍSTICA HÍBRIDA
        if use_statistical:
            self.strategy = StatisticalStrategy(
                ticks_to_analyze=50,
                lookback_periods=20,  # Calcular media/desviación de últimos 20 ticks
                z_score_threshold=2.0,  # 2 desviaciones estándar para reversión
                momentum_threshold=0.02  # 0.02% para confirmar momentum
            )
        else:
            # Estrategia antigua (tick-based)
            self.strategy = TickBasedStrategy(
                ticks_to_analyze=50,
                trend_threshold_pct=60.0,
                force_threshold_pct=0.0008
            )
        
        # Seguimiento de últimas entradas para evitar spam
        self.last_trade_time = {}
        self.min_trade_interval = timedelta(seconds=60)  # Mínimo 60 segundos entre entradas del mismo símbolo
        self.use_statistical = use_statistical
    
    def process_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Procesar símbolo y ejecutar operación si hay señal
        
        Args:
            symbol: Símbolo a procesar
            
        Returns:
            Diccionario con resultado de la operación
        """
        try:
            # Verificar si han pasado suficientes segundos desde la última entrada
            now = timezone.now()
            last_trade = self.last_trade_time.get(symbol)
            
            if last_trade and (now - last_trade) < self.min_trade_interval:
                return {
                    'status': 'waiting',
                    'reason': 'interval_limit',
                    'next_allowed': (last_trade + self.min_trade_interval).isoformat()
                }
            
            # Analizar símbolo
            signal = self.strategy.analyze_symbol(symbol)
            
            if not signal:
                return {
                    'status': 'no_signal',
                    'reason': 'no_clear_trend'
                }
            
            # Verificar si debe entrar
            if not self.strategy.should_enter_trade(signal):
                if hasattr(signal, 'force_pct'):
                    reason_data = {'force_pct': signal.force_pct}
                elif hasattr(signal, 'confidence'):
                    reason_data = {'confidence': signal.confidence}
                else:
                    reason_data = {}
                
                return {
                    'status': 'no_signal',
                    'reason': 'insufficient_confidence',
                    **reason_data
                }
            
            # Obtener parámetros de la operación - DURACIÓN OPTIMIZADA
            # Duración fija de 30s para operaciones de alta frecuencia
            duration = 30
            
            trade_params = self.strategy.get_trade_params(signal, duration=duration)
            
            # Convertir dirección a lado (buy/sell)
            side = 'buy' if signal.direction == 'CALL' else 'sell'
            
            # Monto fijo para simplicidad
            amount = 1.0
            
            # Ejecutar orden
            result = self.place_binary_option(
                symbol=symbol,
                side=side,
                amount=amount,
                duration=duration
            )
            
            # Registrar operación
            self.record_trade(symbol, signal, result)
            
            # Actualizar tiempo de última entrada
            self.last_trade_time[symbol] = now
            
            # Extraer información según el tipo de señal
            signal_info = {
                'direction': signal.direction
            }
            
            if hasattr(signal, 'strength'):
                signal_info['strength'] = signal.strength
            if hasattr(signal, 'force_pct'):
                signal_info['force_pct'] = signal.force_pct
            if hasattr(signal, 'confidence'):
                signal_info['confidence'] = signal.confidence
                signal_info['signal_type'] = signal.signal_type
                signal_info['z_score'] = signal.z_score
            if hasattr(signal, 'upward_ticks_pct'):
                signal_info['upward_pct'] = signal.upward_ticks_pct
            
            return {
                'status': 'executed' if result.get('accepted') else 'rejected',
                'signal': signal_info,
                'result': result
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def place_binary_option(self, symbol: str, side: str, amount: float, duration: int) -> Dict[str, Any]:
        """
        Colocar orden de opción binaria en Deriv
        
        Args:
            symbol: Símbolo
            side: 'buy' (CALL) o 'sell' (PUT)
            amount: Monto
            duration: Duración en segundos
            
        Returns:
            Resultado de la operación
        """
        from connectors.deriv_client import DerivClient
        from connectors.deriv_client import OrderRequest
        
        client = DerivClient()
        
        try:
            # Construir orden - CORREGIDO con campos requeridos
            buy_msg = {
                'buy': 1,
                'price': 10,
                'parameters': {
                    'contract_type': 'CALL' if side == 'buy' else 'PUT',
                    'symbol': symbol,
                    'amount': amount,
                    'duration': duration,  # Duración en segundos
                    'duration_unit': 's',  # Segundos
                    'basis': 'stake',
                    'currency': 'USD'
                }
            }
            
            # Conectar si es necesario
            if not client.connected:
                if not client.authenticate():
                    return {'accepted': False, 'reason': 'auth_failed'}
            
            # Enviar orden
            client.response_event.clear()
            client.ws.send(json.dumps(buy_msg))
            
            # Esperar respuesta
            if client.response_event.wait(timeout=10):
                data = client.response_data
                
                if data.get('error'):
                    print(f"  ❌ {symbol}: Error - {data['error']}")
                    return {
                        'accepted': False,
                        'reason': f"ws_error: {data['error']}"
                    }
                
                result = data.get('buy', {})
                if result:
                    print(f"  ✅ {symbol} {side.upper()} - Contract: {result.get('contract_id')} - Balance: ${result.get('balance_after', 0)}")
                    return {
                        'accepted': True,
                        'order_id': result.get('contract_id'),
                        'buy_price': result.get('buy_price'),
                        'payout': result.get('payout'),
                        'balance_after': result.get('balance_after')
                    }
                else:
                    return {'accepted': False, 'reason': 'no_response'}
            else:
                print(f"  ❌ {symbol}: Timeout")
                return {'accepted': False, 'reason': 'timeout'}
                
        except Exception as e:
            print(f"  ❌ EXCEPCIÓN: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'accepted': False, 'reason': str(e)}
    
    def record_trade(self, symbol: str, signal, result: Dict[str, Any]):
        """
        Registrar operación en OrderAudit
        
        Args:
            symbol: Símbolo
            signal: Señal de trading (TrendSignal o StatisticalSignal)
            result: Resultado de la operación
        """
        try:
            # Construir payload según el tipo de señal
            request_payload = {
                'direction': signal.direction,
                'entry_price': signal.entry_price
            }
            
            # Agregar campos específicos según el tipo de señal
            if hasattr(signal, 'force_pct'):
                # TrendSignal (estrategia antigua)
                request_payload.update({
                    'force_pct': signal.force_pct,
                    'upward_pct': signal.upward_ticks_pct,
                    'strategy': 'tick_based'
                })
            elif hasattr(signal, 'confidence'):
                # StatisticalSignal (nueva estrategia)
                request_payload.update({
                    'confidence': signal.confidence,
                    'signal_type': signal.signal_type,
                    'z_score': signal.z_score,
                    'mean_price': signal.mean_price,
                    'current_position': signal.current_position,
                    'strategy': 'statistical_hybrid'
                })
            
            OrderAudit.objects.create(
                timestamp=timezone.now(),
                symbol=symbol,
                action=signal.direction.lower(),  # 'call' o 'put'
                size=1.0,
                price=signal.entry_price,
                status='pending' if result.get('accepted') else 'rejected',
                request_payload=request_payload,
                response_payload=result,
                accepted=result.get('accepted', False),
                reason='insufficient_confidence' if not result.get('accepted') else ''
            )
        except Exception as e:
            print(f"Error recording trade: {e}")


def process_tick_based_trading(symbol: str, use_statistical: bool = True) -> Optional[Dict[str, Any]]:
    """
    Función principal para procesar trading basado en ticks
    
    Args:
        symbol: Símbolo a procesar
        use_statistical: Usar estrategia estadística híbrida (True) o tick-based (False)
        
    Returns:
        Resultado de la operación
    """
    loop = TickTradingLoop(use_statistical=use_statistical)
    return loop.process_symbol(symbol)


