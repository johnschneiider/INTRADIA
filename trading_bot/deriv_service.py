import asyncio
import json
import websockets
from decimal import Decimal
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class DerivAPI:
    """Cliente para interactuar con la API de Deriv mediante WebSocket"""
    
    def __init__(self, api_token, app_id="1089", is_demo=True):
        self.api_token = api_token
        self.app_id = app_id
        self.is_demo = is_demo
        self.ws_url = f"wss://ws.derivws.com/websockets/v3?app_id={app_id}"
        self.ws = None
        self.account_info = None
        self.balance = None
        
    async def connect(self):
        """Conectar al WebSocket de Deriv"""
        try:
            self.ws = await websockets.connect(self.ws_url)
            logger.info(f"Conectado a Deriv WebSocket")
            
            # Autorizar con el token
            await self.authorize()
            return True
        except Exception as e:
            logger.error(f"Error al conectar con Deriv: {e}")
            return False
    
    async def disconnect(self):
        """Desconectar del WebSocket"""
        if self.ws:
            await self.ws.close()
            logger.info("Desconectado de Deriv WebSocket")
    
    async def send_request(self, request):
        """Enviar una petición al WebSocket"""
        if not self.ws:
            raise Exception("No conectado al WebSocket")
        
        await self.ws.send(json.dumps(request))
        response = await self.ws.recv()
        return json.loads(response)
    
    async def authorize(self):
        """Autorizar la conexión con el token de API"""
        request = {
            "authorize": self.api_token
        }
        response = await self.send_request(request)
        
        if 'error' in response:
            raise Exception(f"Error de autorización: {response['error']['message']}")
        
        self.account_info = response.get('authorize', {})
        logger.info(f"Autorizado como {self.account_info.get('email')}")
        return self.account_info
    
    async def get_balance(self):
        """Obtener el balance de la cuenta"""
        request = {"balance": 1, "subscribe": 0}
        response = await self.send_request(request)
        
        if 'error' in response:
            raise Exception(f"Error al obtener balance: {response['error']['message']}")
        
        self.balance = Decimal(response['balance']['balance'])
        return self.balance
    
    async def get_active_symbols(self, market='synthetic_index'):
        """Obtener los símbolos disponibles"""
        request = {
            "active_symbols": "brief",
            "product_type": "basic"
        }
        response = await self.send_request(request)
        
        if 'error' in response:
            raise Exception(f"Error al obtener símbolos: {response['error']['message']}")
        
        return response.get('active_symbols', [])
    
    async def get_tick_history(self, symbol, count=100):
        """Obtener historial de ticks"""
        request = {
            "ticks_history": symbol,
            "end": "latest",
            "count": count,
            "style": "ticks"
        }
        response = await self.send_request(request)
        
        if 'error' in response:
            raise Exception(f"Error al obtener historial: {response['error']['message']}")
        
        return response.get('history', {})
    
    async def buy_contract(self, symbol, contract_type, amount, duration, duration_unit='t'):
        """
        Comprar un contrato
        
        Args:
            symbol: Símbolo a operar (ej: 'R_100')
            contract_type: Tipo de contrato ('CALL', 'PUT', 'DIGITEVEN', 'DIGITODD', etc.)
            amount: Monto de la apuesta
            duration: Duración del contrato
            duration_unit: Unidad de duración ('t'=ticks, 's'=segundos, 'm'=minutos, 'h'=horas)
        """
        # Primero, obtener la propuesta (precio)
        proposal_request = {
            "proposal": 1,
            "amount": float(amount),
            "basis": "stake",
            "contract_type": contract_type,
            "currency": "USD",
            "duration": duration,
            "duration_unit": duration_unit,
            "symbol": symbol
        }
        
        proposal_response = await self.send_request(proposal_request)
        
        if 'error' in proposal_response:
            raise Exception(f"Error en propuesta: {proposal_response['error']['message']}")
        
        proposal_id = proposal_response['proposal']['id']
        
        # Comprar el contrato
        buy_request = {
            "buy": proposal_id,
            "price": float(amount)
        }
        
        buy_response = await self.send_request(buy_request)
        
        if 'error' in buy_response:
            raise Exception(f"Error al comprar: {buy_response['error']['message']}")
        
        return buy_response.get('buy', {})
    
    async def get_contract_status(self, contract_id):
        """Obtener el estado de un contrato"""
        request = {
            "proposal_open_contract": 1,
            "contract_id": contract_id
        }
        
        response = await self.send_request(request)
        
        if 'error' in response:
            raise Exception(f"Error al obtener estado: {response['error']['message']}")
        
        return response.get('proposal_open_contract', {})
    
    async def subscribe_to_ticks(self, symbol, callback):
        """Suscribirse a los ticks en tiempo real"""
        request = {
            "ticks": symbol,
            "subscribe": 1
        }
        
        await self.ws.send(json.dumps(request))
        
        while True:
            try:
                response = await asyncio.wait_for(self.ws.recv(), timeout=60)
                data = json.loads(response)
                
                if 'tick' in data:
                    await callback(data['tick'])
                elif 'error' in data:
                    logger.error(f"Error en suscripción: {data['error']}")
                    break
            except asyncio.TimeoutError:
                logger.warning("Timeout esperando tick")
                break
            except Exception as e:
                logger.error(f"Error en suscripción a ticks: {e}")
                break
    
    async def get_account_statement(self, limit=50):
        """Obtener el estado de cuenta"""
        request = {
            "statement": 1,
            "description": 1,
            "limit": limit
        }
        
        response = await self.send_request(request)
        
        if 'error' in response:
            raise Exception(f"Error al obtener statement: {response['error']['message']}")
        
        return response.get('statement', {}).get('transactions', [])
    
    async def get_profit_table(self, limit=50):
        """Obtener tabla de ganancias/pérdidas"""
        request = {
            "profit_table": 1,
            "description": 1,
            "limit": limit
        }
        
        response = await self.send_request(request)
        
        if 'error' in response:
            raise Exception(f"Error al obtener profit table: {response['error']['message']}")
        
        return response.get('profit_table', {}).get('transactions', [])


class TradingEngine:
    """Motor de trading que ejecuta las estrategias"""
    
    def __init__(self, deriv_api, bot):
        self.api = deriv_api
        self.bot = bot
        self.is_running = False
        self.current_trade = None
        
    async def start(self):
        """Iniciar el motor de trading"""
        self.is_running = True
        logger.info(f"Motor de trading iniciado para bot {self.bot.name}")
        
        try:
            # Conectar a Deriv
            connected = await self.api.connect()
            if not connected:
                raise Exception("No se pudo conectar a Deriv")
            
            # Obtener balance inicial
            balance = await self.api.get_balance()
            logger.info(f"Balance inicial: {balance}")
            
            # Ejecutar estrategia
            await self.execute_strategy()
            
        except Exception as e:
            logger.error(f"Error en motor de trading: {e}")
            self.bot.status = 'error'
            self.bot.save()
        finally:
            await self.api.disconnect()
    
    async def stop(self):
        """Detener el motor de trading"""
        self.is_running = False
        logger.info(f"Motor de trading detenido para bot {self.bot.name}")
    
    async def execute_strategy(self):
        """Ejecutar la estrategia de trading"""
        strategy = self.bot.strategy
        
        while self.is_running:
            # Verificar límites diarios
            if self.bot.today_trades >= self.bot.max_daily_trades:
                logger.info("Límite diario de trades alcanzado")
                break
            
            if self.bot.today_profit <= -self.bot.max_daily_loss:
                logger.info("Límite diario de pérdidas alcanzado")
                break
            
            if self.bot.daily_profit_target and self.bot.today_profit >= self.bot.daily_profit_target:
                logger.info("Objetivo diario de ganancias alcanzado")
                break
            
            # Determinar el monto de la apuesta según la estrategia
            stake = self.calculate_stake(strategy)
            
            # Ejecutar trade
            await self.execute_trade(stake)
            
            # Esperar antes del siguiente trade
            await asyncio.sleep(5)
    
    def calculate_stake(self, strategy):
        """Calcular el monto de la apuesta según la estrategia"""
        if strategy.strategy_type == 'fixed':
            return strategy.initial_stake
        
        elif strategy.strategy_type == 'martingale':
            # Si la última operación fue perdida, duplicar
            last_trade = self.bot.trades.order_by('-opened_at').first()
            if last_trade and last_trade.status == 'lost':
                new_stake = last_trade.stake * 2
                return min(new_stake, strategy.max_stake)
            return strategy.initial_stake
        
        elif strategy.strategy_type == 'percentage':
            # Porcentaje del balance actual
            percentage = strategy.config.get('percentage', 2) / 100
            return self.api.balance * Decimal(str(percentage))
        
        else:
            return strategy.initial_stake
    
    async def execute_trade(self, stake):
        """Ejecutar un trade individual"""
        try:
            # Comprar contrato
            contract = await self.api.buy_contract(
                symbol=self.bot.symbol,
                contract_type=self.bot.contract_type,
                amount=float(stake),
                duration=self.bot.duration,
                duration_unit=self.bot.duration_unit
            )
            
            logger.info(f"Contrato comprado: {contract.get('contract_id')}")
            
            # Crear registro del trade
            from .models import Trade
            trade = Trade.objects.create(
                bot=self.bot,
                user=self.bot.user,
                contract_id=contract.get('contract_id'),
                symbol=self.bot.symbol,
                contract_type=self.bot.contract_type,
                entry_price=Decimal(str(contract.get('buy_price', 0))),
                stake=stake,
                duration=self.bot.duration,
                duration_unit=self.bot.duration_unit,
                status='open'
            )
            
            # Esperar a que termine el contrato
            await self.monitor_contract(trade, contract['contract_id'])
            
        except Exception as e:
            logger.error(f"Error ejecutando trade: {e}")
    
    async def monitor_contract(self, trade, contract_id):
        """Monitorear un contrato hasta que termine"""
        while self.is_running:
            try:
                status = await self.api.get_contract_status(contract_id)
                
                if status.get('is_sold') or status.get('status') == 'sold':
                    # Contrato cerrado
                    profit = Decimal(str(status.get('profit', 0)))
                    exit_price = Decimal(str(status.get('exit_tick', 0)))
                    
                    if profit > 0:
                        payout = trade.stake + profit
                        trade.mark_as_won(exit_price, payout)
                        logger.info(f"Trade ganado: +{profit}")
                    else:
                        trade.mark_as_lost(exit_price)
                        logger.info(f"Trade perdido: {profit}")
                    
                    break
                
                # Esperar antes de verificar de nuevo
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Error monitoreando contrato: {e}")
                break


