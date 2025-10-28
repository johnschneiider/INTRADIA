from __future__ import annotations

import json
import threading
import time
import websocket
from datetime import datetime
from django.utils import timezone
from market.models import Candle, Tick
from connectors.deriv_client import DerivClient
import logging

logger = logging.getLogger(__name__)

class RealtimeTickService:
    def __init__(self):
        self.ws = None
        self.connected = False
        self.subscribed_symbols = set()
        self.tick_callbacks = []
        self.running = False
        
    def add_tick_callback(self, callback):
        """Agregar callback para procesar ticks"""
        self.tick_callbacks.append(callback)
    
    def connect(self):
        """Conectar al WebSocket de Deriv"""
        if self.connected:
            return True
            
        try:
            def on_message(ws, message):
                data = json.loads(message)
                self._process_message(data)
            
            def on_error(ws, error):
                logger.error(f"WebSocket error: {error}")
                self.connected = False
            
            def on_close(ws, close_status_code, close_msg):
                logger.info("WebSocket connection closed")
                self.connected = False
            
            def on_open(ws):
                logger.info("WebSocket connection opened")
                self.connected = True
                # Autenticar
                auth_msg = {
                    "authorize": "rOB3RNqw1EevPzu"  # Token de Deriv
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
            self.ws_thread = threading.Thread(target=self.ws.run_forever)
            self.ws_thread.daemon = True
            self.ws_thread.start()
            
            # Esperar conexión
            time.sleep(2)
            return self.connected
            
        except Exception as e:
            logger.error(f"Error connecting WebSocket: {e}")
            return False
    
    def subscribe_to_symbol(self, symbol):
        """Suscribirse a ticks de un símbolo"""
        if not self.connected:
            if not self.connect():
                return False
        
        if symbol in self.subscribed_symbols:
            return True
            
        try:
            subscribe_msg = {
                "ticks": symbol
            }
            self.ws.send(json.dumps(subscribe_msg))
            self.subscribed_symbols.add(symbol)
            logger.info(f"Subscribed to {symbol}")
            return True
        except Exception as e:
            logger.error(f"Error subscribing to {symbol}: {e}")
            return False
    
    def unsubscribe_from_symbol(self, symbol):
        """Desuscribirse de ticks de un símbolo"""
        if not self.connected or symbol not in self.subscribed_symbols:
            return True
            
        try:
            forget_msg = {
                "forget": symbol
            }
            self.ws.send(json.dumps(forget_msg))
            self.subscribed_symbols.discard(symbol)
            logger.info(f"Unsubscribed from {symbol}")
            return True
        except Exception as e:
            logger.error(f"Error unsubscribing from {symbol}: {e}")
            return False
    
    def _process_message(self, data):
        """Procesar mensajes del WebSocket"""
        msg_type = data.get('msg_type', '')
        
        if msg_type == 'tick':
            tick_data = data.get('tick', {})
            if tick_data:
                self._process_tick(tick_data)
        elif msg_type == 'authorize':
            auth_data = data.get('authorize', {})
            if auth_data.get('error'):
                logger.error(f"Auth error: {auth_data['error']}")
            else:
                logger.info("Authentication successful")
    
    def _process_tick(self, tick_data):
        """Procesar un tick individual"""
        try:
            symbol = tick_data.get('symbol', '')
            price = float(tick_data.get('quote', 0))
            epoch = tick_data.get('epoch', int(time.time()))
            
            # Crear timestamp
            timestamp = datetime.fromtimestamp(epoch, tz=timezone.utc)
            
            # Almacenar tick en base de datos
            tick, created = Tick.objects.get_or_create(
                symbol=symbol,
                timestamp=timestamp,
                defaults={
                    'price': price,
                    'volume': tick_data.get('volume', 0)
                }
            )
            
            if created:
                logger.debug(f"New tick stored: {symbol} @ {price}")
            
            # Llamar callbacks
            for callback in self.tick_callbacks:
                try:
                    callback(symbol, price, timestamp)
                except Exception as e:
                    logger.error(f"Error in tick callback: {e}")
                    
        except Exception as e:
            logger.error(f"Error processing tick: {e}")
    
    def start(self):
        """Iniciar el servicio"""
        if self.running:
            return True
            
        self.running = True
        if self.connect():
            logger.info("RealtimeTickService started")
            return True
        return False
    
    def stop(self):
        """Detener el servicio"""
        self.running = False
        if self.ws:
            self.ws.close()
        self.connected = False
        logger.info("RealtimeTickService stopped")

# Instancia global del servicio
tick_service = RealtimeTickService()


