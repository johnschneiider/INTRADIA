from __future__ import annotations

import os
import time
import json
import websocket
import threading
from dataclasses import dataclass
from typing import Callable, Dict, Any, Optional

from tenacity import retry, stop_after_attempt, wait_exponential_jitter


@dataclass
class OrderRequest:
    symbol: str
    side: str  # 'buy' or 'sell'
    size: float
    type: str  # 'limit' or 'market'
    price: Optional[float]
    stop: Optional[float]
    take_profit: Optional[float]
    client_id: Optional[str]


class DerivClient:
    def __init__(self):
        # Token real de Deriv
        self.api_token = os.getenv('DERIV_API_TOKEN', 'G7Eq2rRQnE81Vot')
        self.rate_limit_per_sec = 5
        self.last_call_ts = 0.0
        self.failure_count = 0
        self.circuit_open_until = 0.0
        self.ws = None
        self.connected = False
        self.response_data = {}
        self.response_event = threading.Event()

    def _ratelimit(self):
        now = time.time()
        min_interval = 1.0 / self.rate_limit_per_sec
        if now - self.last_call_ts < min_interval:
            time.sleep(min_interval - (now - self.last_call_ts))
        self.last_call_ts = time.time()

    def _connect_websocket(self):
        """Conectar a WebSocket de Deriv"""
        if self.connected and self.ws:
            return True
            
        try:
            def on_message(ws, message):
                data = json.loads(message)
                self.response_data = data
                self.response_event.set()
                
                # Procesar ticks en tiempo real
                msg_type = data.get('msg_type', '')
                if msg_type == 'tick':
                    tick_data = data.get('tick', {})
                    if tick_data:
                        # Aquí podrías procesar ticks en tiempo real
                        # Por ejemplo, actualizar precios, detectar señales, etc.
                        pass
            
            def on_error(ws, error):
                print(f"WebSocket error: {error}")
                self.connected = False
            
            def on_close(ws, close_status_code, close_msg):
                print("WebSocket connection closed")
                self.connected = False
            
            def on_open(ws):
                print("WebSocket connection opened")
                self.connected = True
                # Autenticar
                auth_msg = {
                    "authorize": self.api_token
                }
                ws.send(json.dumps(auth_msg))
            
            self.ws = websocket.WebSocketApp(
                "wss://ws.derivws.com/websockets/v3?app_id=1089",
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open
            )
            
            # Ejecutar en hilo separado
            wst = threading.Thread(target=self.ws.run_forever)
            wst.daemon = True
            wst.start()
            
            # Esperar conexión
            time.sleep(2)
            return self.connected
            
        except Exception as e:
            print(f"Error connecting WebSocket: {e}")
            return False

    def authenticate(self):
        """Autenticar usando WebSocket"""
        if not self.api_token:
            print("❌ No API token provided")
            return False
        
        print(f"🔑 Using token: {self.api_token[:10]}...")
        
        try:
            if not self._connect_websocket():
                print("❌ Failed to connect WebSocket")
                return False
            
            print("✅ WebSocket connected, waiting for auth response...")
            
            # Esperar respuesta de autenticación
            if self.response_event.wait(timeout=10):
                auth_response = self.response_data
                print(f"📨 Auth response: {auth_response}")
                
                if auth_response.get('authorize', {}).get('error'):
                    print(f"❌ Auth error: {auth_response['authorize']['error']}")
                    return False
                
                print("✅ Authentication successful")
                return True
            else:
                print("⏰ Timeout waiting for authentication")
                return False
                
        except Exception as e:
            print(f"❌ Error authenticating with Deriv: {e}")
            return False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=0.2, max=2))
    def get_candles(self, symbol: str, timeframe: str, count: int):
        """Obtener velas históricas reales usando WebSocket de Deriv"""
        self._ratelimit()
        
        if not self.connected:
            if not self.authenticate():
                return []
        
        try:
            # Usar WebSocket para obtener datos históricos
            self.response_event.clear()
            
            ticks_msg = {
                "ticks_history": symbol,
                "granularity": self._convert_timeframe(timeframe),
                "count": count,
                "end": int(time.time())
            }
            
            self.ws.send(json.dumps(ticks_msg))
            
            # Esperar respuesta
            if self.response_event.wait(timeout=30):
                data = self.response_data
                if data.get('error'):
                    print(f"Error WebSocket: {data['error']}")
                    return []
                
                history = data.get('ticks_history', {})
                ticks = history.get('ticks', [])
                
                if ticks:
                    print(f"✅ Obtenidas {len(ticks)} velas reales para {symbol} {timeframe}")
                    return self._parse_ticks_to_candles(ticks, timeframe)
                else:
                    print(f"⚠️ No hay datos históricos para {symbol} {timeframe}")
                    return []
            else:
                print("⏰ Timeout esperando datos históricos")
                return []
                
        except Exception as e:
            print(f"❌ Error get_candles: {e}")
            return []
    
    def _convert_timeframe(self, timeframe: str) -> int:
        """Convierte timeframe string a granularidad de Deriv"""
        timeframe_map = {
            '1m': 60,
            '5m': 300,
            '15m': 900,
            '30m': 1800,
            '1h': 3600,
            '4h': 14400,
            '1d': 86400
        }
        return timeframe_map.get(timeframe, 300)  # Default 5m
    
    def _parse_ticks_to_candles(self, ticks, timeframe: str):
        """Convierte ticks de Deriv a formato OHLCV"""
        if not ticks:
            return []
        
        candles = []
        granularity = self._convert_timeframe(timeframe)
        
        # Agrupar ticks por período de tiempo
        current_period = None
        current_candle = None
        
        for tick in ticks:
            tick_time = tick.get('epoch', 0)
            tick_price = float(tick.get('quote', 0))
            
            # Calcular el inicio del período
            period_start = (tick_time // granularity) * granularity
            
            if current_period != period_start:
                # Guardar candle anterior si existe
                if current_candle:
                    candles.append(current_candle)
                
                # Crear nuevo candle
                current_candle = {
                    'timestamp': period_start,
                    'open': tick_price,
                    'high': tick_price,
                    'low': tick_price,
                    'close': tick_price,
                    'volume': 1000
                }
                current_period = period_start
            else:
                # Actualizar candle actual
                if current_candle:
                    current_candle['high'] = max(current_candle['high'], tick_price)
                    current_candle['low'] = min(current_candle['low'], tick_price)
                    current_candle['close'] = tick_price
                    current_candle['volume'] += 1000
        
        # Agregar último candle
        if current_candle:
            candles.append(current_candle)
        
        return candles

    def subscribe_ticks(self, symbol: str, callback: Callable[[Dict[str, Any]], None]):
        # Stub: no-op
        return

    @retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=0.2, max=2))
    def place_order(self, req: OrderRequest) -> Dict[str, Any]:
        self._ratelimit()
        # Circuit breaker sencillo
        now = time.time()
        if now < self.circuit_open_until:
            return {'accepted': False, 'reason': 'circuit_open'}
        
        # Conectar si no está conectado
        if not self.connected:
            if not self.authenticate():
                return {'accepted': False, 'reason': 'auth_failed'}
        
        try:
            # Determinar tipo de contrato según símbolo
            is_binary_option = req.symbol.startswith('R_') or req.symbol.startswith('CRASH') or req.symbol.startswith('BOOM')
            
            # Construir mensaje de compra/venta para WebSocket
            action = 'buy' if req.side == 'buy' else 'sell'
            
            if is_binary_option:
                # OPCIÓN BINARIA - Requiere duration, contract_type y currency
                buy_msg = {
                    'buy': 1,
                    'price': 10,  # Precio de entrada
                    'parameters': {
                        'contract_type': 'CALL',  # CALL o PUT (se determina por side)
                        'symbol': req.symbol,
                        'amount': req.size,
                        'duration': req.size if hasattr(req, 'duration') else 60,  # Duración en segundos
                        'duration_unit': 's',  # Segundos
                        'basis': 'stake',
                        'currency': 'USD'
                    }
                }
                # Determinar si es CALL o PUT según side
                if hasattr(req, 'side'):
                    if req.side == 'sell':
                        buy_msg['parameters']['contract_type'] = 'PUT'
                    else:
                        buy_msg['parameters']['contract_type'] = 'CALL'
            else:
                # CFD - mercado continuo
                buy_msg = {
                    'buy': 1,
                    'price': req.price or 100,
                    'parameters': {
                        'symbol': req.symbol,
                        'amount': req.size,
                        'basis': 'stake'
                    }
                }
                # Añadir stop loss y take profit solo para CFDs
                if req.stop:
                    buy_msg['parameters']['stop_loss'] = req.stop
                if req.take_profit:
                    buy_msg['parameters']['take_profit'] = req.take_profit
            
            # Enviar orden a través de WebSocket
            self.response_event.clear()
            self.ws.send(json.dumps(buy_msg))
            
            # Esperar respuesta
            if self.response_event.wait(timeout=10):
                data = self.response_data
                
                if data.get('error'):
                    self.failure_count += 1
                    error_msg = data.get('error', {}).get('message', 'Unknown error')
                    return {'accepted': False, 'reason': f'ws_error: {error_msg}'}
                
                result = data.get('buy', {})
                if result:
                    self.failure_count = 0
                    return {
                        'accepted': True,
                        'order_id': result.get('contract_id'),
                        'price': result.get('price'),
                        'payout': result.get('payout'),
                        'buy_price': result.get('buy_price')
                    }
                else:
                    return {'accepted': False, 'reason': 'no_response'}
            else:
                return {'accepted': False, 'reason': 'timeout'}
                
        except Exception as e:
            self.failure_count += 1
            if self.failure_count >= 5:
                self.circuit_open_until = time.time() + 60
            return {'accepted': False, 'reason': str(e)}

    def get_balance(self) -> Dict[str, Any]:
        try:
            # Conectar si no está conectado
            if not self.connected:
                if not self.authenticate():
                    return {'balance': 1000.0, 'currency': 'USD', 'account_type': 'demo'}
            
            # Enviar mensaje de balance a través de WebSocket
            self.response_event.clear()
            
            balance_msg = {
                'balance': 1
            }
            self.ws.send(json.dumps(balance_msg))
            
            # Esperar respuesta
            if self.response_event.wait(timeout=10):
                data = self.response_data
                
                if data.get('error'):
                    print(f"Error getting balance: {data['error']}")
                    return {'balance': 1000.0, 'currency': 'USD', 'account_type': 'demo'}
                
                balance_info = data.get('balance', {})
                return {
                    'balance': float(balance_info.get('balance', 1000)),
                    'currency': balance_info.get('currency', 'USD'),
                    'loginid': balance_info.get('loginid', ''),
                    'account_type': balance_info.get('account_type', 'demo')
                }
            else:
                print("Timeout getting balance")
                return {'balance': 1000.0, 'currency': 'USD', 'account_type': 'demo'}
                
        except Exception as e:
            print(f"Error get_balance: {e}")
            return {'balance': 1000.0, 'currency': 'USD', 'error': str(e)}

    def cancel_order(self, order_id: str) -> bool:
        return True

    def list_open_positions(self):
        return []
    
    def get_contract_status(self, contract_id: str) -> Dict[str, Any]:
        """
        Consultar el estado de un contrato
        
        Args:
            contract_id: ID del contrato
            
        Returns:
            Diccionario con el estado del contrato
        """
        try:
            if not self.connected:
                if not self.authenticate():
                    return {'error': 'Not connected'}
            
            # Enviar consulta de contrato
            self.response_event.clear()
            
            contract_msg = {
                'contracts_for': 1,
                'contract_id': contract_id
            }
            self.ws.send(json.dumps(contract_msg))
            
            # Esperar respuesta
            if self.response_event.wait(timeout=10):
                data = self.response_data
                
                if data.get('error'):
                    return {'error': data['error']}
                
                # La respuesta de contracts_for devuelve info del contrato
                # Si el contrato expiró, necesitamos usar 'proposal_open_contract'
                # Vamos a intentar obtener el estado directamente
                return data
            else:
                return {'error': 'timeout'}
                
        except Exception as e:
            print(f"Error get_contract_status: {e}")
            return {'error': str(e)}
    
    def get_open_contract_info(self, contract_id: str) -> Dict[str, Any]:
        """
        Obtener información de un contrato abierto
        
        Args:
            contract_id: ID del contrato
            
        Returns:
            Diccionario con información del contrato
        """
        try:
            if not self.connected:
                if not self.authenticate():
                    return {'error': 'Not connected'}
            
            self.response_event.clear()
            
            contract_msg = {
                'proposal_open_contract': 1,
                'contract_id': contract_id
            }
            self.ws.send(json.dumps(contract_msg))
            
            if self.response_event.wait(timeout=10):
                data = self.response_data
                
                if data.get('error'):
                    return {'error': data['error']}
                
                contract_info = data.get('proposal_open_contract', {})
                
                return {
                    'is_sold': contract_info.get('is_sold', False),
                    'status': 'won' if contract_info.get('profit', 0) > 0 else 'lost',
                    'profit': contract_info.get('profit', 0),
                    'buy_price': contract_info.get('buy_price', 0),
                    'sell_price': contract_info.get('sell_price', 0)
                }
            else:
                return {'error': 'timeout'}
                
        except Exception as e:
            print(f"Error get_open_contract_info: {e}")
            return {'error': str(e)}

