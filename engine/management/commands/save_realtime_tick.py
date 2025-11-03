"""
Comando Django para guardar ticks en tiempo real de Deriv en la base de datos
"""

import os
import sys
import time
import json
import websocket
import threading
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from market.models import Tick
from trading_bot.models import DerivAPIConfig


class Command(BaseCommand):
    help = 'Guarda ticks en tiempo real de Deriv en la base de datos'

    def handle(self, *args, **options):
        self.ws = None
        self.connected = False
        self.tick_count = 0
        
        # Obtener configuración de API desde la BD
        try:
            api_config = DerivAPIConfig.objects.filter(is_active=True).only('api_token', 'is_demo', 'app_id').first()
            if not api_config:
                self.stdout.write(self.style.ERROR('❌ No hay configuración de API activa'))
                return
            
            self.api_token = api_config.api_token
            self.app_id = api_config.app_id or 1089
            self.stdout.write(self.style.SUCCESS(f'✅ Usando token: {self.api_token[:10]}...'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error al obtener configuración: {e}'))
            return
        
        self.stdout.write(self.style.SUCCESS('🚀 Iniciando guardado de ticks en tiempo real...'))
        self.stdout.write(f'📊 Suscribiéndose a FOREX, COMMODITIES, ÍNDICES...')
        self.stdout.write('💾 Guardando ticks en base de datos...')
        self.stdout.write('=' * 60)
        
        # Símbolos a suscribir (excluyendo crypto, OTC, BOOM, CRASH según la cuenta)
        symbols = [
            # Forex - Principales
            'frxEURUSD', 'frxGBPUSD', 'frxUSDJPY', 'frxUSDCHF', 'frxAUDUSD', 'frxUSDCAD',
            'frxNZDUSD', 'frxEURGBP', 'frxEURJPY', 'frxGBPJPY', 'frxAUDJPY', 'frxEURAUD',
            # Commodities
            'frxXAUUSD', 'frxXAGUSD', 'frxXPDUSD', 'frxXPTUSD',
            # Índices sintéticos
            'R_10', 'R_25', 'R_50', 'R_75', 'R_100',
            'RDBULL', 'RDBEAR',
            # Jump indices
            'JD10', 'JD25', 'JD50', 'JD75',
        ]
        
        self.symbols_to_subscribe = symbols
        
        self.ws = websocket.WebSocketApp(
            f"wss://ws.derivws.com/websockets/v3?app_id={self.app_id}",
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )
        
        # Mantener conexión con reintentos
        while True:
            try:
                self.ws.run_forever()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Error en WebSocket: {e}'))
                self.stdout.write(self.style.WARNING('🔄 Reintentando en 10 segundos...'))
                time.sleep(10)
                self.ws = websocket.WebSocketApp(
                    f"wss://ws.derivws.com/websockets/v3?app_id={self.app_id}",
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close,
                    on_open=self.on_open
                )
    
    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            msg_type = data.get('msg_type', '')
            
            if msg_type == 'tick':
                tick_data = data.get('tick', {})
                if tick_data:
                    self.save_tick(tick_data)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error procesando mensaje: {e}'))
    
    def save_tick(self, tick_data):
        try:
            symbol = tick_data.get('symbol', '')
            price = tick_data.get('quote', 0)
            epoch = tick_data.get('epoch', int(time.time()))
            
            if not symbol or price == 0:
                return
            
            # Convertir timestamp
            timestamp = timezone.make_aware(datetime.fromtimestamp(epoch))
            
            # Guardar en base de datos (evitar duplicados)
            tick, created = Tick.objects.get_or_create(
                symbol=symbol,
                timestamp=timestamp,
                defaults={
                    'price': price,
                    'volume': tick_data.get('volume', 0)
                }
            )
            
            if created:
                self.tick_count += 1
                if self.tick_count % 50 == 0:
                    self.stdout.write(self.style.SUCCESS(f'✅ Guardados {self.tick_count} ticks nuevos'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error guardando tick: {e}'))
    
    def on_error(self, ws, error):
        self.stdout.write(self.style.ERROR(f'❌ WebSocket error: {error}'))
        self.connected = False
    
    def on_close(self, ws, close_status_code, close_msg):
        self.stdout.write(self.style.WARNING('❌ WebSocket desconectado'))
        self.connected = False
    
    def on_open(self, ws):
        self.stdout.write(self.style.SUCCESS('✅ WebSocket conectado a Deriv'))
        self.connected = True
        
        # Autenticar
        auth_msg = {"authorize": self.api_token}
        ws.send(json.dumps(auth_msg))
        self.stdout.write(self.style.SUCCESS('🔐 Enviando autorización...'))
        
        # Esperar un momento antes de suscribirse
        time.sleep(1)
        
        # Suscribirse a símbolos
        for symbol in self.symbols_to_subscribe:
            subscribe_msg = {"ticks": symbol}
            ws.send(json.dumps(subscribe_msg))
        self.stdout.write(self.style.SUCCESS(f'📊 Suscrito a {len(self.symbols_to_subscribe)} símbolos'))
