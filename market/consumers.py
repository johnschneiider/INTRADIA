import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from monitoring.models import OrderAudit
from django.utils import timezone
from datetime import datetime, timedelta


class TradingConsumer(AsyncWebsocketConsumer):
    """Consumer para actualizaciones de trading en tiempo real"""
    
    async def connect(self):
        print(f"🔌 Cliente intentando conectar a WebSocket")
        await self.accept()
        print(f"✅ Cliente conectado exitosamente")
        
        # Suscribirse al grupo para recibir notificaciones
        await self.channel_layer.group_add(
            'trading_updates',
            self.channel_name
        )
        print(f"📡 Suscrito al grupo 'trading_updates'")
        
        await self.send_initial_data()
    
    async def disconnect(self, close_code):
        # Desuscribirse del grupo
        await self.channel_layer.group_discard(
            'trading_updates',
            self.channel_name
        )
        print(f"❌ Cliente desconectado. Código: {close_code}")
    
    async def receive(self, text_data):
        """Recibir mensajes del cliente"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'request_update':
                await self.send_update()
            elif message_type == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))
        except Exception as e:
            print(f"Error recibiendo mensaje: {e}")
    
    @database_sync_to_async
    def get_active_orders(self):
        """Obtener órdenes activas con tiempo transcurrido"""
        now = timezone.now()
        active_orders = OrderAudit.objects.filter(status='active')
        result = []
        for order in active_orders:
            elapsed = (now - order.timestamp).total_seconds()
            result.append({
                'id': order.id,
                'symbol': order.symbol,
                'action': order.action,
                'entry_price': float(order.price or 0),
                'stop_loss': float(order.stop_loss or 0),
                'take_profit': float(order.take_profit or 0),
                'timestamp': order.timestamp.isoformat(),
                'elapsed_seconds': int(elapsed)
            })
        return result
    
    @database_sync_to_async
    def get_recent_closed_orders(self, limit=10):
        """Obtener órdenes cerradas recientes"""
        orders = OrderAudit.objects.filter(
            status__in=['won', 'lost']
        ).order_by('-timestamp')[:limit]
        
        result = []
        for order in orders:
            elapsed = (timezone.now() - order.timestamp).total_seconds()
            result.append({
                'id': order.id,
                'symbol': order.symbol,
                'action': order.action,
                'entry_price': float(order.price or 0),
                'exit_price': float(order.exit_price or 0),
                'pnl': float(order.pnl or 0),
                'status': order.status,
                'timestamp': order.timestamp.isoformat(),
                'elapsed_seconds': int(elapsed)
            })
        return result
    
    @database_sync_to_async
    def get_metrics(self):
        """Obtener métricas generales"""
        from django.utils import timezone
        from datetime import timedelta
        
        # Calcular métricas solo de las últimas 24 horas para win rate real en tiempo real
        since = timezone.now() - timedelta(hours=24)
        recent_orders = OrderAudit.objects.filter(timestamp__gte=since)
        
        total = recent_orders.count()
        won = recent_orders.filter(status='won').count()
        lost = recent_orders.filter(status='lost').count()
        active = recent_orders.filter(status__in=['pending', 'active']).count()
        
        # P&L total de las últimas 24 horas
        total_pnl = sum(float(o.pnl or 0) for o in recent_orders)
        
        # Win rate: porcentaje de operaciones ganadas sobre total finalizadas
        win_rate = (won / (won + lost)) * 100 if (won + lost) > 0 else 0
        
        return {
            'total_trades': total,
            'won_trades': won,
            'lost_trades': lost,
            'active_trades': active,
            'total_pnl': total_pnl,
            'win_rate': win_rate
        }
    
    @database_sync_to_async
    def get_latest_tick(self, symbol):
        """Obtener último tick de un símbolo"""
        from market.models import Tick
        try:
            tick = Tick.objects.filter(symbol=symbol).order_by('-timestamp').first()
            if tick:
                return {
                    'symbol': tick.symbol,
                    'price': float(tick.price),
                    'timestamp': tick.timestamp.isoformat()
                }
        except:
            pass
        return None
    
    async def send_initial_data(self):
        """Enviar datos iniciales al conectar"""
        await self.send_update()
    
    async def send_update(self):
        """Enviar actualización completa"""
        try:
            active_orders = await self.get_active_orders()
            recent_closed = await self.get_recent_closed_orders()
            metrics = await self.get_metrics()
            
            # Obtener últimos ticks de símbolos principales - TODOS los instrumentos activos
            symbols_to_check = [
                # Forex
                'frxEURUSD', 'frxGBPUSD', 'frxUSDJPY', 'frxUSDCHF', 'frxAUDUSD',
                # Commodities
                'frxXAUUSD', 'frxXAGUSD',
                # Índices sintéticos
                'R_10', 'R_25', 'R_50', 'BOOM1000', 'CRASH1000',
                # Crypto
                'cryBTCUSD', 'cryETHUSD',
            ]
            latest_ticks = {}
            for symbol in symbols_to_check:
                tick = await self.get_latest_tick(symbol)
                if tick:
                    latest_ticks[symbol] = tick
            
            message = {
                'type': 'trading_update',
                'data': {
                    'active_orders': active_orders,
                    'recent_closed': recent_closed,
                    'metrics': metrics,
                    'latest_ticks': latest_ticks,
                    'timestamp': timezone.now().isoformat()
                }
            }
            
            await self.send(text_data=json.dumps(message))
        except Exception as e:
            print(f"Error enviando update: {e}")
    
    async def trading_update(self, event):
        """Recibir broadcast del grupo trading_updates"""
        print(f"📡 Broadcast recibido: {event}")
        # Enviar actualización completa al cliente
        await self.send_update()

