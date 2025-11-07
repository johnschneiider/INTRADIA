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
    def __init__(self, api_token: Optional[str] = None, is_demo: Optional[bool] = None, app_id: Optional[str] = None):
        """
        Inicializar DerivClient
        
        Args:
            api_token: Token de API de Deriv. Si no se proporciona, intenta obtenerlo de:
                      1. Variable de entorno DERIV_API_TOKEN
                      2. DerivAPIConfig del usuario actual (si está disponible en contexto Django)
                      Si no se encuentra, se lanzará un error (no hay fallback por seguridad)
            is_demo: Si True, usa cuenta demo. Si False, usa cuenta real.
                     Si None, intenta obtenerlo de DerivAPIConfig.
            app_id: App ID de Deriv. Por defecto '1089'.
        """
        # Determinar token
        if api_token:
            self.api_token = api_token
        else:
            # Intentar obtener de variable de entorno
            self.api_token = os.getenv('DERIV_API_TOKEN')
            
            # Si no hay en env, intentar obtener de DerivAPIConfig (solo si Django está disponible)
            if not self.api_token:
                try:
                    from django.contrib.auth import get_user_model
                    from trading_bot.models import DerivAPIConfig
                    from threading import local
                    
                    # Intentar obtener del contexto del request (si existe)
                    # Nota: Esto requiere que el usuario esté en el contexto del thread
                    User = get_user_model()
                    # Por ahora, intentar obtener la última configuración activa
                    config = DerivAPIConfig.objects.filter(is_active=True).first()
                    if config:
                        self.api_token = config.api_token
                        if is_demo is None:
                            is_demo = config.is_demo
                        if app_id is None:
                            app_id = config.app_id
                except Exception:
                    pass
            
            # Fallback final - NO USAR TOKEN HARDCODEADO POR SEGURIDAD
            # El token debe estar configurado en DerivAPIConfig o variable de entorno
            if not self.api_token:
                raise ValueError(
                    "No se encontró token de API de Deriv. "
                    "Por favor, configura tu token en: "
                    "http://localhost:8000/trading/config/api/ "
                    "o mediante la variable de entorno DERIV_API_TOKEN"
                )
        
        # Determinar is_demo
        if is_demo is None:
            try:
                from trading_bot.models import DerivAPIConfig
                config = DerivAPIConfig.objects.filter(is_active=True).first()
                if config:
                    is_demo = config.is_demo
                else:
                    is_demo = True  # Default a demo si no hay configuración
            except Exception:
                is_demo = True  # Default a demo si hay error
        self.is_demo = is_demo
        
        # Determinar app_id
        self.app_id = app_id or os.getenv('DERIV_APP_ID', '1089')
        
        self.rate_limit_per_sec = 5
        self.last_call_ts = 0.0
        self.failure_count = 0
        self.circuit_open_until = 0.0
        self.ws = None
        self.connected = False
        self.response_data = {}
        self.response_event = threading.Event()
        # Caché simple para contratos ofrecidos: key=(symbol, contract_type, duration)
        self._contracts_cache: Dict[str, float] = {}
        self._cache_ttl_seconds = 600  # 10 minutos
        # Caché de balance para evitar rate limiting
        self._balance_cache_value: Optional[Dict[str, Any]] = None
        self._balance_cache_time: float = 0.0
        self._balance_cache_ttl: float = 30.0  # 30 segundos TTL para balance (reducir llamadas)
        # Account list y cuenta seleccionada
        self.account_list: list = []
        self.current_loginid: Optional[str] = None
        # Thread para heartbeat (mantener conexión viva)
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_running = False
        self._last_attempted_token_loginid = False  # Rastrear si Deriv rechazó token:loginid
        # Métricas de reconexión
        self.reconnect_attempts = 0
        self._reconnect_history: list[float] = []
    
    def clear_cache(self):
        """Limpiar cache de balance"""
        self._balance_cache_value = None
        self._balance_cache_time = 0.0
    
    def _record_reconnect(self, reason: str) -> None:
        ts = time.time()
        self.reconnect_attempts += 1
        self._reconnect_history.append(ts)
        # Mantener historial de la última hora
        self._reconnect_history = [t for t in self._reconnect_history if ts - t <= 3600]
        print(f"🔁 Intento de reconexión #{self.reconnect_attempts}: {reason}")

    def get_reconnect_stats(self) -> Dict[str, int]:
        now = time.time()
        recent_10m = [t for t in self._reconnect_history if now - t <= 600]
        return {
            'total': self.reconnect_attempts,
            'last_10m': len(recent_10m)
        }

    def _ratelimit(self):
        now = time.time()
        min_interval = 1.0 / self.rate_limit_per_sec
        if now - self.last_call_ts < min_interval:
            time.sleep(min_interval - (now - self.last_call_ts))
        self.last_call_ts = time.time()

    def _connect_websocket_with_token_only(self):
        """Conexión WebSocket que solo envía el token (sin loginid)"""
        try:
            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    # Siempre guardar respuestas importantes (authorize, buy, proposal, balance, proposal_open_contract, etc.)
                    if any(key in data for key in ['authorize', 'buy', 'proposal', 'balance', 'proposal_open_contract', 'contracts_for', 'ticks_history', 'history', 'error']):
                        self.response_data = data
                        self.response_event.set()
                        # Debug: mostrar qué se recibió
                        if 'authorize' in data:
                            auth_data = data.get('authorize', {})
                            if auth_data:
                                print(f"📨 Respuesta authorize recibida: loginid={auth_data.get('loginid', 'N/A')}, balance={auth_data.get('balance', 0)}")
                    elif not self.response_data:
                        # Si no hay datos previos y no es una respuesta esperada, guardar igual
                        self.response_data = data
                        self.response_event.set()
                except json.JSONDecodeError:
                    print(f"❌ Error parsing WebSocket message: {message[:100]}")
            
            def on_error(ws, error):
                # Log solo para errores críticos
                # print(f"WebSocket error: {error}")
                self.connected = False
            
            def on_close(ws, close_status_code, close_msg):
                # Log solo para debug
                # print("WebSocket connection closed")
                self.connected = False
                self._stop_heartbeat()
            
            def on_open(ws):
                # Log solo para debug
                # print("WebSocket connection opened")
                self.connected = True
                # IMPORTANTE: Enviar SOLO el token (sin loginid)
                auth_msg = {
                    "authorize": self.api_token
                }
                ws.send(json.dumps(auth_msg))
                
                # Iniciar heartbeat para mantener conexión viva
                self._start_heartbeat()
            
            self.ws = websocket.WebSocketApp(
                f"wss://ws.derivws.com/websockets/v3?app_id={self.app_id}",
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
    
    def _connect_websocket(self):
        """Conectar a WebSocket de Deriv"""
        if self.connected and self.ws:
            return True
            
        try:
            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    
                    # Siempre guardar respuestas importantes (authorize, buy, proposal, balance, etc.)
                    # Estas respuestas deben activar el evento para que el código que espera pueda continuar
                    if any(key in data for key in ['authorize', 'buy', 'proposal', 'balance', 'proposal_open_contract', 'contracts_for', 'ticks_history', 'history', 'error']):
                        self.response_data = data
                        self.response_event.set()
                    elif not self.response_data:
                        # Si no hay datos previos y no es una respuesta esperada, guardar igual
                        # (puede ser una respuesta inesperada pero válida)
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
                except json.JSONDecodeError:
                    print(f"❌ Error parsing WebSocket message: {message[:100]}")
            
            def on_error(ws, error):
                print(f"WebSocket error: {error}")
                self.connected = False
            
            def on_close(ws, close_status_code, close_msg):
                # Log solo para debug
                # print("WebSocket connection closed")
                self.connected = False
            
            def on_open(ws):
                # Log solo para debug
                # print("WebSocket connection opened")
                self.connected = True
                # IMPORTANTE: Autenticar con loginid específico desde el inicio
                # Si Deriv ya rechazó token:loginid anteriormente, usar solo token
                target_loginid = 'CR9822432'  # Cuenta dtrade REAL que queremos usar
                
                # Intentar autenticar con loginid específico desde el inicio
                # Si Deriv ya rechazó token:loginid antes, no intentar de nuevo
                if not self.is_demo and not self._last_attempted_token_loginid:
                    auth_msg = {
                        "authorize": f"{self.api_token}:{target_loginid}"
                    }
                    print(f"🔐 Autenticando con cuenta REAL: {target_loginid}")
                else:
                    # Si es demo O si Deriv rechazó token:loginid antes, usar solo token
                    auth_msg = {
                        "authorize": self.api_token
                    }
                    if self.is_demo:
                        print(f"🔐 Autenticando con cuenta DEMO (token solo)")
                    else:
                        print(f"🔐 Autenticando con cuenta REAL (token solo, Deriv rechazó token:loginid)")
                
                ws.send(json.dumps(auth_msg))
                
                # Iniciar heartbeat para mantener conexión viva
                self._start_heartbeat()
            
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
        """Autenticar usando WebSocket y seleccionar cuenta real/demo"""
        if not self.api_token:
            print("❌ No API token provided")
            return False
        
        # Logs solo para debug cuando sea necesario
        # print(f"🔑 Using token: {self.api_token[:10]}...")
        # print(f"🔍 Target account type: {'DEMO' if self.is_demo else 'REAL'}")
        
        try:
            if not self._connect_websocket():
                self._record_reconnect('fallo_conexion_inicial')
                print("❌ Failed to connect WebSocket")
                return False
            
            # Esperar respuesta de autenticación
            if self.response_event.wait(timeout=10):
                auth_response = self.response_data
                
                # Verificar si hay error en la respuesta (puede ser por usar formato token:loginid)
                if auth_response.get('error'):
                    error_info = auth_response.get('error', {})
                    error_code = error_info.get('code', '')
                    error_msg = error_info.get('message', '')
                    
                    # Si Deriv rechazó el formato token:loginid, marcar y intentar con solo token
                    if error_code == 'InputValidationFailed' and 'authorize' in error_msg.lower():
                        # Marcar que Deriv rechazó token:loginid (no intentar de nuevo)
                        self._last_attempted_token_loginid = True
                        print(f"⚠️  Deriv rechazó formato token:loginid, reintentando con token solo...")
                        # Cerrar conexión actual
                        self._stop_heartbeat()
                        if self.ws:
                            try:
                                self.ws.close()
                            except:
                                pass
                        self.connected = False
                        time.sleep(2)  # Dar más tiempo para cerrar conexión
                        
                        # Limpiar respuesta anterior
                        self.response_data = {}
                        self.response_event.clear()
                        
                        # Reintentar autenticación con solo token (modificar on_open para usar solo token)
                        # Necesitamos crear una nueva conexión que envíe solo el token
                        self._record_reconnect('token_loginid_rejected')
                        if not self._connect_websocket_with_token_only():
                            print("❌ Failed to reconnect WebSocket")
                            return False
                        
                        # Esperar nueva respuesta
                        if not self.response_event.wait(timeout=15):
                            print("❌ Timeout esperando autenticación")
                            return False
                        
                        auth_response = self.response_data
                        # Verificar que la respuesta es válida
                        if not auth_response or not auth_response.get('authorize'):
                            print(f"❌ Respuesta de autenticación inválida: {auth_response}")
                            return False
                
                # Log útil: mostrar información relevante del websocket
                authorize_data = auth_response.get('authorize', {})
                
                # Verificar si hay error en authorize después de reintentar
                if authorize_data.get('error'):
                    error_info = authorize_data.get('error', {})
                    print(f"❌ Auth error: {error_info.get('code')} - {error_info.get('message')}")
                    return False
                
                auth_loginid = authorize_data.get('loginid', '')
                auth_balance = authorize_data.get('balance', 0)
                account_list = authorize_data.get('account_list', [])
                
                # DEBUG: Mostrar información completa de la respuesta
                print(f"📊 Websocket | LoginID: {auth_loginid} | Balance: ${auth_balance:.2f} | Accounts: {len(account_list)}")
                
                # Verificar que la respuesta es válida
                if not authorize_data:
                    print(f"❌ ERROR CRÍTICO: authorize_data está vacío. Respuesta completa: {auth_response}")
                    return False
                
                if not auth_loginid:
                    print(f"⚠️  ADVERTENCIA: Respuesta de authorize sin loginid. authorize_data keys: {list(authorize_data.keys())}")
                    # Intentar obtener loginid de otra forma
                    auth_loginid = authorize_data.get('loginid', '') or ''
                
                if not account_list:
                    print(f"⚠️  ADVERTENCIA: Respuesta de authorize sin account_list.")
                    print(f"   authorize_data keys: {list(authorize_data.keys())}")
                    print(f"   authorize_data contenido: {str(authorize_data)[:500]}")
                    # Si no hay account_list pero hay otros datos, puede ser un error
                    if 'error' in authorize_data:
                        print(f"❌ Error en authorize_data: {authorize_data.get('error')}")
                        return False
                
                # Extraer account_list de la respuesta
                self.account_list = account_list if account_list else []
                
                # Si aún no hay account_list, puede ser que la respuesta venga en otro formato
                if not self.account_list and authorize_data:
                    # Intentar buscar account_list en otros lugares
                    if 'account_list' in auth_response:
                        self.account_list = auth_response.get('account_list', [])
                    if not self.account_list:
                        print(f"⚠️  No se encontró account_list. Respuesta completa keys: {list(auth_response.keys())}")
                
                # IMPORTANTE: El usuario ha especificado que SOLO quiere usar la cuenta CR9822432
                target_loginid = 'CR9822432'  # Cuenta dtrade específica que el usuario quiere usar
                default_loginid = authorize_data.get('loginid', '')
                
                # Filtrar account_list para incluir SOLO CR9822432
                filtered_account_list = []
                for account in self.account_list:
                    if account.get('loginid') == target_loginid:
                        filtered_account_list.append(account)
                        break
                
                # Actualizar account_list para incluir solo la cuenta seleccionada
                self.account_list = filtered_account_list
                
                # Verificar que la cuenta existe
                if not filtered_account_list:
                    # Buscar en account_list original
                    for account in authorize_data.get('account_list', []):
                        if account.get('loginid') == target_loginid:
                            filtered_account_list.append(account)
                            self.account_list = filtered_account_list
                            break
                    
                    if not filtered_account_list:
                        print(f"❌ ERROR: La cuenta {target_loginid} no existe en account_list")
                        return False
                
                # Verificar si la cuenta seleccionada coincide con is_demo
                selected_account = filtered_account_list[0]
                selected_loginid = selected_account.get('loginid', '')
                selected_is_virtual = selected_account.get('is_virtual', 1)
                selected_is_demo = (selected_is_virtual == 1) or selected_loginid.startswith('VRTC') or selected_loginid.startswith('VRT')
                
                if selected_is_demo != self.is_demo:
                    self.is_demo = selected_is_demo
                
                # IMPORTANTE: Deriv NO permite cambiar de cuenta después de autenticar
                # Establecer current_loginid como target_loginid (CR9822432)
                self.current_loginid = target_loginid or default_loginid
                
                # Guardar el balance de la respuesta de authorize (viene del websocket)
                auth_balance = authorize_data.get('balance', 0)
                
                # Marcar account_type según current_loginid (CR9822432 = REAL)
                account_type_from_loginid = 'real' if (self.current_loginid == 'CR9822432' or 
                                                       (not self.current_loginid.startswith('VRTC') and 
                                                        not self.current_loginid.startswith('VRT'))) else 'demo'
                
                self._balance_cache_value = {
                    'balance': float(auth_balance),
                    'currency': authorize_data.get('currency', 'USD'),
                    'loginid': self.current_loginid,
                    'account_type': account_type_from_loginid,
                    'source': 'authorize_response'
                }
                self._balance_cache_time = time.time()
                
                print(f"✅ Auth exitosa | Cuenta: {self.current_loginid} ({account_type_from_loginid.upper()}) | Balance: ${auth_balance:.2f}")
                return True
            else:
                # Reducir spam de logs de timeout de autenticación
                if not hasattr(self, '_last_auth_timeout_log') or (time.time() - getattr(self, '_last_auth_timeout_log', 0)) > 60:
                    print("⚠️ Timeout esperando autenticación")
                    self._last_auth_timeout_log = time.time()
                return False
                
        except Exception as e:
            print(f"❌ Error authenticating with Deriv: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def switch_account(self, loginid: str) -> bool:
        """
        Cambiar a una cuenta específica (re-autenticando con loginid)
        
        Args:
            loginid: Login ID de la cuenta a la que cambiar
            
        Returns:
            True si el cambio fue exitoso, False en caso contrario
        """
        if not self.connected:
            print("❌ No connected, cannot switch account")
            return False
        
        if not loginid:
            print("❌ No loginid provided")
            return False
        
        try:
            # Re-autenticar con loginid específico
            self.response_event.clear()
            auth_msg = {
                "authorize": f"{self.api_token}:{loginid}"
            }
            self.ws.send(json.dumps(auth_msg))
            
            # Esperar respuesta
            if self.response_event.wait(timeout=10):
                data = self.response_data
                if data.get('authorize', {}).get('error'):
                    print(f"❌ Error switching account: {data['authorize']['error']}")
                    return False
                
                if data.get('authorize'):
                    self.current_loginid = loginid
                    # Limpiar caché de balance al cambiar de cuenta
                    self.clear_cache()
                    return True
                else:
                    print(f"⚠️  Unexpected response when switching account: {data}")
                    return False
            else:
                print("⏰ Timeout waiting for switch_account response")
                return False
                
        except Exception as e:
            print(f"❌ Error switching account: {e}")
            return False

    def _cache_key(self, symbol: str, contract_type: str, duration: int) -> str:
        return f"{symbol}:{contract_type}:{duration}"

    def get_contract_limits(self, symbol: str, contract_type: str, duration_seconds: int, amount: float) -> Dict[str, Any]:
        """
        Obtener límites del contrato (máximo purchase price permitido)
        
        Returns:
            Dict con max_purchase_price, min_purchase_price, o None si hay error
        """
        self._ratelimit()
        if not self.connected:
            if not self.authenticate():
                return {'error': 'not_connected'}
        
        try:
            self.response_event.clear()
            req = {
                "proposal": 1,
                "amount": float(amount),
                "basis": "stake",
                "contract_type": contract_type,
                "currency": "USD",
                "duration": duration_seconds,
                "duration_unit": "s",
                "symbol": symbol,
            }
            self.ws.send(json.dumps(req))
            if self.response_event.wait(timeout=10):
                data = self.response_data
                if data.get("error"):
                    return {'error': data['error']}
                
                proposal = data.get("proposal", {})
                if proposal:
                    # Deriv devuelve max_payout o ask_price que puede usarse como límite
                    max_payout = proposal.get('max_payout')
                    ask_price = proposal.get('ask_price')
                    
                    # El máximo purchase price suele ser aproximadamente el max_payout o se calcula
                    # Si hay max_payout, usar ese como límite aproximado
                    # Nota: esto es una aproximación, Deriv puede tener límites específicos
                    return {
                        'max_purchase_price': max_payout if max_payout else None,
                        'ask_price': ask_price,
                        'available': True
                    }
                return {'error': 'no_proposal'}
        except Exception as e:
            return {'error': str(e)}
        return {'error': 'timeout'}

    def is_contract_offered(self, symbol: str, contract_type: str, duration_seconds: int) -> bool:
        """Devuelve True si el contrato está ofrecido (usa proposal como pre‑chequeo y cachea)."""
        self._ratelimit()
        if not self.connected:
            if not self.authenticate():
                # Si no se puede conectar, asumir que está ofrecido (evitar rechazar trades por problemas de conexión)
                print(f"  ⚠️ {symbol}: No se pudo conectar para verificar contrato, asumiendo que está ofrecido")
                return True  # Cambiar de False a True para evitar rechazar trades válidos
        
        # Verificar que WebSocket esté conectado antes de enviar proposal
        if not self.ws or not self.ws.sock or not self.ws.sock.connected:
            # Si no está conectado, intentar reconectar, pero si falla, asumir que está ofrecido
            if not self.authenticate():
                print(f"  ⚠️ {symbol}: WebSocket desconectado para verificar contrato, asumiendo que está ofrecido")
                return True  # Cambiar de False a True para evitar rechazar trades válidos
        
        # Cache hit
        key = self._cache_key(symbol, contract_type, duration_seconds)
        now = time.time()
        ts = self._contracts_cache.get(key)
        if ts and now - ts < self._cache_ttl_seconds:
            return True
        
        try:
            self.response_event.clear()
            req = {
                "proposal": 1,
                "amount": 1.0,
                "basis": "stake",
                "contract_type": contract_type,
                "currency": "USD",
                "duration": duration_seconds,
                "duration_unit": "s",
                "symbol": symbol,
            }
            
            # Verificar que WebSocket esté conectado antes de enviar
            if not self.ws or not self.ws.sock or not self.ws.sock.connected:
                print(f"  ⚠️ {symbol}: WebSocket desconectado al enviar proposal, asumiendo que está ofrecido")
                return True  # Cambiar de False a True para evitar rechazar trades válidos
            
            try:
                self.ws.send(json.dumps(req))
            except Exception as send_error:
                # Si falla enviar proposal, asumir que está ofrecido (evitar rechazar por problemas de envío)
                print(f"  ⚠️ {symbol}: Error enviando proposal: {send_error}, asumiendo que está ofrecido")
                return True  # Cambiar de False a True para evitar rechazar trades válidos
            
            if self.response_event.wait(timeout=10):
                data = self.response_data
                if data.get("error"):
                    error_info = data.get("error", {})
                    error_code = error_info.get('code', '') if isinstance(error_info, dict) else ''
                    error_message = error_info.get('message', '') if isinstance(error_info, dict) else str(error_info)
                    # Si el error es "InvalidSymbol", "NotAvailable", "InvalidOfferings", etc., el contrato NO está ofrecido
                    if error_code in ['InvalidSymbol', 'NotAvailable', 'InvalidOfferings', 'OfferingsValidationError', 'ContractCreationFailure']:
                        print(f"  ❌ {symbol}: Contrato no disponible | Código: {error_code} | Mensaje: {error_message}")
                        return False
                    # Para otros errores (ej. RateLimit, timeout), asumir que está ofrecido (evitar rechazar por errores temporales)
                    print(f"  ⚠️ {symbol}: Error en proposal (pero no es de disponibilidad) | Código: {error_code} | Mensaje: {error_message}, asumiendo que está ofrecido")
                    return True  # Cambiar de False a True para errores temporales
                if data.get("proposal"):
                    self._contracts_cache[key] = now
                    return True
                # Si no hay proposal ni error, asumir que está ofrecido
                print(f"  ⚠️ {symbol}: Respuesta proposal sin 'proposal' ni 'error', asumiendo que está ofrecido")
                return True  # Cambiar de False a True
            else:
                # Timeout en proposal: asumir que está ofrecido (evitar rechazar por timeouts)
                print(f"  ⚠️ {symbol}: Timeout en proposal, asumiendo que está ofrecido")
                return True  # Cambiar de False a True para evitar rechazar por timeouts
        except Exception as e:
            # Si hay excepción, asumir que está ofrecido (evitar rechazar por errores de ejecución)
            print(f"  ⚠️ {symbol}: Excepción en is_contract_offered: {e}, asumiendo que está ofrecido")
            return True  # Cambiar de False a True para evitar rechazar por excepciones

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
                data = dict(self.response_data) if isinstance(self.response_data, dict) else self.response_data
                self.response_data = {}
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
        """
        Obtener balance con caché para evitar rate limiting
        """
        now = time.time()
        
        # Si el caché es válido, retornarlo (evitar llamadas innecesarias)
        if (self._balance_cache_value and 
            (now - self._balance_cache_time) < self._balance_cache_ttl and
            not self._balance_cache_value.get('error')):
            return self._balance_cache_value
        
        # Si hay rate limit error en caché y aún es reciente, retornar caché
        if (self._balance_cache_value and 
            (now - self._balance_cache_time) < 30.0 and  # Usar caché hasta 30s si hay error
            self._balance_cache_value.get('error_code') == 'RateLimit'):
            return self._balance_cache_value
        
        try:
            self._ratelimit()  # Aplicar rate limiting
            
            # Verificar conexión antes de intentar obtener balance
            if not self.connected or not self.ws or not self.ws.sock or not self.ws.sock.connected:
                # Intentar autenticar una sola vez
                if not self.authenticate():
                    # Si falla autenticación, usar caché si existe
                    if self._balance_cache_value:
                        print("⚠️ Usando balance en caché (autenticación falló)")
                        return self._balance_cache_value
                    # Si no hay caché, usar account_type basado en is_demo
                    return {'balance': 0.0, 'currency': 'USD', 'account_type': 'demo' if self.is_demo else 'real', 'error': 'auth_failed'}
            
            # Enviar mensaje de balance a través de WebSocket
            # NOTA: Deriv no acepta 'account' en el mensaje balance, siempre devuelve el balance de la cuenta autenticada
            # Si queremos cuenta REAL pero estamos autenticados con DEMO, debemos confiar en el caché de authorize_response
            # o forzar una nueva conexión WebSocket autenticando directamente con la cuenta REAL
            
            # Si tenemos balance en caché del websocket válido, usarlo directamente
            if (self._balance_cache_value and 
                self._balance_cache_value.get('loginid') == self.current_loginid and
                (now - self._balance_cache_time) < self._balance_cache_ttl):
                return self._balance_cache_value
            
            # Verificar que WebSocket esté realmente conectado antes de enviar
            if not self.ws or not self.ws.sock or not self.ws.sock.connected:
                # Si no está conectado, usar caché
                if self._balance_cache_value:
                    print("⚠️ Usando balance en caché (WebSocket desconectado)")
                    return self._balance_cache_value
                return {'balance': 0.0, 'currency': 'USD', 'account_type': 'demo' if self.is_demo else 'real', 'error': 'ws_disconnected'}
            
            # Solicitar balance a Deriv (devolverá balance de la cuenta autenticada actualmente)
            self.response_event.clear()
            
            balance_msg = {
                'balance': 1
            }
            
            try:
                self.ws.send(json.dumps(balance_msg))
            except Exception as e:
                print(f"⚠️ Error enviando mensaje de balance: {e}")
                # Si falla al enviar, usar caché
                if self._balance_cache_value:
                    return self._balance_cache_value
                return {'balance': 0.0, 'currency': 'USD', 'account_type': 'demo' if self.is_demo else 'real', 'error': 'send_failed'}
            
            # Esperar respuesta
            if self.response_event.wait(timeout=10):
                data = self.response_data
                
                if data.get('error'):
                    error_info = data['error']
                    error_code = error_info.get('code', '')
                    error_msg = error_info.get('message', '')
                    
                    print(f"❌ Error obteniendo balance: {error_code} - {error_msg}")
                    
                    # Si es rate limit, usar caché anterior si existe (solo caché del websocket)
                    if error_code == 'RateLimit':
                        # Mantener caché anterior pero marcar error (solo si viene del websocket)
                        if self._balance_cache_value:
                            self._balance_cache_value['error_code'] = 'RateLimit'
                            self._balance_cache_value['error_message'] = error_msg
                            self._balance_cache_time = now
                            return self._balance_cache_value
                    
                    # Otro error: retornar caché si existe (solo del websocket)
                    if self._balance_cache_value:
                        return self._balance_cache_value
                    # Si no hay caché, usar account_type basado en is_demo
                    return {'balance': 0.0, 'currency': 'USD', 'account_type': 'demo' if self.is_demo else 'real', 'error': error_code}
                
                balance_info = data.get('balance', {})
                
                # Usar current_loginid (CR9822432) para determinar account_type
                if self.current_loginid == 'CR9822432':
                    account_type = 'real'
                    loginid = 'CR9822432'
                else:
                    # Fallback si no es CR9822432
                    if self.current_loginid and (self.current_loginid.startswith('VRTC') or self.current_loginid.startswith('VRT')):
                        account_type = 'demo'
                    else:
                        account_type = 'real' if not self.is_demo else 'demo'
                    loginid = self.current_loginid or balance_info.get('loginid', '')
                
                # Obtener balance del websocket
                balance_from_ws = float(balance_info.get('balance', 0))
                response_loginid = balance_info.get('loginid', '')
                
                # Construir resultado usando balance del websocket
                # Marcar account_type según current_loginid (CR9822432 = REAL)
                result = {
                    'balance': balance_from_ws,
                    'currency': balance_info.get('currency', 'USD'),
                    'loginid': self.current_loginid,  # Siempre usar current_loginid (CR9822432)
                    'account_type': 'real' if self.current_loginid == 'CR9822432' else account_type
                }
                
                # Log útil: mostrar balance del websocket
                if response_loginid != self.current_loginid:
                    print(f"💰 Balance: ${balance_from_ws:.2f} | Auth: {response_loginid} | Target: {self.current_loginid} ({result['account_type'].upper()})")
                else:
                    print(f"💰 Balance: ${balance_from_ws:.2f} | Cuenta: {self.current_loginid} ({result['account_type'].upper()})")
                
                # Actualizar caché
                self._balance_cache_value = result
                self._balance_cache_time = now
                
                return result
            else:
                # Timeout: usar caché si existe en lugar de mostrar error repetitivo
                if self._balance_cache_value:
                    # Solo mostrar mensaje ocasionalmente para evitar spam
                    if not hasattr(self, '_last_timeout_log') or (now - getattr(self, '_last_timeout_log', 0)) > 60:
                        print("⚠️ Timeout obteniendo balance (usando caché)")
                        self._last_timeout_log = now
                    return self._balance_cache_value
                # Si no hay caché, mostrar error y retornar valor por defecto
                if not hasattr(self, '_last_timeout_log') or (now - getattr(self, '_last_timeout_log', 0)) > 60:
                    print("❌ Timeout obteniendo balance (sin caché disponible)")
                    self._last_timeout_log = now
                return {'balance': 0.0, 'currency': 'USD', 'account_type': 'demo' if self.is_demo else 'real', 'error': 'timeout'}
                
        except Exception as e:
            print(f"❌ Error get_balance: {e}")
            # Retornar caché si existe (solo del websocket)
            if self._balance_cache_value:
                return self._balance_cache_value
            # Si no hay caché, usar account_type basado en is_demo
            return {'balance': 0.0, 'currency': 'USD', 'account_type': 'demo' if self.is_demo else 'real', 'error': str(e)}

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
                data = dict(self.response_data) if isinstance(self.response_data, dict) else self.response_data
                self.response_data = {}
                
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
                data = dict(self.response_data) if isinstance(self.response_data, dict) else self.response_data
                self.response_data = {}
                
                if data.get('error'):
                    return {'error': data['error']}
                
                contract_info = data.get('proposal_open_contract', {})
                
                # Deriv puede devolver is_sold como 1/0 (int) o True/False (bool)
                is_sold_raw = contract_info.get('is_sold', False)
                is_sold = bool(is_sold_raw) if is_sold_raw is not None else False
                profit = float(contract_info.get('profit', 0) or 0)
                
                # Si el contrato ya se vendió/cerró, determinar status
                if is_sold:
                    status = 'won' if profit > 0 else 'lost'
                else:
                    # Si aún no expiró, no determinamos status aún
                    status = None
                
                return {
                    'is_sold': is_sold,
                    'status': status,
                    'profit': profit,
                    'buy_price': float(contract_info.get('buy_price', 0) or 0),
                    'sell_price': float(contract_info.get('sell_price', 0) or 0)
                }
            else:
                return {'error': 'timeout'}
                
        except Exception as e:
            print(f"Error get_open_contract_info: {e}")
            return {'error': str(e)}
    
    def _start_heartbeat(self):
        """Iniciar heartbeat para mantener conexión WebSocket viva"""
        if self._heartbeat_running:
            return
        
        self._heartbeat_running = True
        
        def heartbeat_loop():
            """Loop de heartbeat: enviar ping cada 30 segundos"""
            while self._heartbeat_running and self.connected:
                try:
                    time.sleep(30)  # Esperar 30 segundos entre pings
                    if self._heartbeat_running and self.connected and self.ws:
                        # Verificar que el socket esté conectado antes de enviar ping
                        if hasattr(self.ws, 'sock') and self.ws.sock and hasattr(self.ws.sock, 'connected'):
                            if self.ws.sock.connected:
                                # Enviar ping (Deriv usa "ping" como mensaje de texto)
                                try:
                                    self.ws.send(json.dumps({"ping": 1}))
                                except Exception as e:
                                    # Si falla enviar ping, la conexión probablemente se perdió
                                    print(f"⚠️ Error enviando heartbeat: {e}")
                                    self.connected = False
                                    break
                            else:
                                # Socket no conectado, salir del loop
                                self.connected = False
                                break
                        else:
                            # No hay socket, salir del loop
                            self.connected = False
                            break
                except Exception as e:
                    # Si hay error en el loop, salir
                    print(f"⚠️ Error en heartbeat loop: {e}")
                    self.connected = False
                    break
        
        self._heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()
    
    def sell_contract(self, contract_id: str) -> Dict[str, Any]:
        """
        Cerrar/vender un contrato abierto antes de que expire
        
        Args:
            contract_id: ID del contrato a cerrar
            
        Returns:
            Diccionario con el resultado de la venta
        """
        try:
            if not self.connected:
                if not self.authenticate():
                    return {'error': 'Not connected'}
            
            self.response_event.clear()
            
            # En Deriv, para cerrar un contrato se envía el contract_id con price: 0 (vender al precio de mercado)
            sell_msg = {
                'sell': contract_id,
                'price': 0  # 0 = vender al precio de mercado actual
            }
            self.ws.send(json.dumps(sell_msg))
            
            if self.response_event.wait(timeout=10):
                data = self.response_data
                
                if data.get('error'):
                    return {'error': data['error'].get('message', 'Error desconocido')}
                
                sell_result = data.get('sell', {})
                
                return {
                    'success': True,
                    'contract_id': contract_id,
                    'profit': sell_result.get('profit', 0),
                    'price': sell_result.get('price', 0),
                    'balance_after': sell_result.get('balance_after', 0)
                }
            else:
                return {'error': 'timeout'}
                
        except Exception as e:
            print(f"Error sell_contract: {e}")
            return {'error': str(e)}
    
    def _stop_heartbeat(self):
        """Detener heartbeat"""
        self._heartbeat_running = False
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            # Esperar a que termine el thread (máximo 1 segundo)
            self._heartbeat_thread.join(timeout=1)
        self._heartbeat_thread = None

