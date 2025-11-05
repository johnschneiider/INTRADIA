"""
Bucle principal para trading basado en ticks en tiempo real
Con integración completa de gestión avanzada de capital y protección de riesgo
"""

from __future__ import annotations
import json
import time
from typing import Optional, Dict, Any
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from market.models import Tick

from engine.services.tick_based_strategy import TickBasedStrategy, TrendSignal
from engine.services.statistical_strategy import StatisticalStrategy, StatisticalSignal
from engine.services.ema200_extrema_strategy import EMA200ExtremaStrategy, EMAExtremaSignal
from engine.services.momentum_reversal_strategy import MomentumReversalStrategy, MomentumReversalSignal
from engine.services.execution_gateway import place_order_through_gateway
from engine.services.advanced_capital_manager import AdvancedCapitalManager
from engine.services.risk_protection import RiskProtectionSystem
from engine.services.adaptive_filter_manager import AdaptiveFilterManager
from monitoring.models import OrderAudit
from connectors.deriv_client import DerivClient


class TickTradingLoop:
    """Bucle de trading basado en ticks con gestión avanzada de capital y protección de riesgo"""
    
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
        # Segunda estrategia (EMA + extremos) configurada a EMA100 como solicitaste
        self.strategy_ema = EMA200ExtremaStrategy(lookback_ticks=200, extrema_window=60, ema_period=100)
        # Tercera estrategia (Tick-Based) para comparar y medir
        self.strategy_ticks = TickBasedStrategy(
            ticks_to_analyze=40,
            trend_threshold_pct=55.0,      # más laxo
            force_threshold_pct=0.0006     # más laxo
        )
        # Cuarta estrategia (Reversión por Fatiga y Ruptura)
        self.strategy_reversal = MomentumReversalStrategy(
            fatigue_threshold=5,
            momentum_extreme_threshold=0.05,
            consolidation_breakout_atr_ratio=2.0,
            short_timeframe=15,
            long_timeframe=60
        )
        
        # Inicializar sistemas de gestión de capital y protección (se cargarán desde BD al procesar)
        self.capital_manager = None
        self.risk_protection = None
        self.adaptive_filter_manager = AdaptiveFilterManager()
        self._client = None
        
        # Cache de balance para evitar rate limiting
        from engine.services.balance_cache import BalanceCache
        self._balance_cache = BalanceCache(ttl_seconds=10)
        # Prioridades por símbolo (0..1) inyectadas por el loop
        self.symbol_priorities: Dict[str, float] = {}
        # Flag de modo recuperación (priorizar alta confianza y reducir tamaño)
        self.recovery_mode: bool = False
        # Pacing: última ejecución aceptada
        self._last_executed_time = None
    
    def _initialize_capital_systems(self):
        """Inicializar sistemas de capital y riesgo desde configuración"""
        try:
            from engine.models import CapitalConfig
            capital_config = CapitalConfig.get_active()  # Renombrar para evitar conflicto
            
            # Obtener balance actual (con cache)
            if not self._client:
                # Intentar obtener configuración del usuario
                try:
                    from trading_bot.models import DerivAPIConfig
                    api_config = DerivAPIConfig.objects.filter(is_active=True).only('api_token', 'is_demo', 'app_id').first()
                    if api_config:
                        self._client = DerivClient(
                            api_token=api_config.api_token,
                            is_demo=api_config.is_demo,
                            app_id=api_config.app_id
                        )
                    else:
                        self._client = DerivClient()
                except Exception:
                    self._client = DerivClient()
            try:
                balance_info = self._client.get_balance()
                if isinstance(balance_info, dict):
                    current_balance = Decimal(str(balance_info.get('balance', 0)))
                else:
                    current_balance = Decimal(str(balance_info)) if balance_info else Decimal('0')
            except Exception:
                current_balance = Decimal('0')  # Si hay error, asumir $0 (más seguro)
            
            # Aplicar controles rápidos (max_trades siempre ilimitado)
            # Siempre usar 999999 para operación perpetua
            effective_max_trades = 999999  # Siempre ilimitado
            
            # Advanced Capital Manager
            self.capital_manager = AdvancedCapitalManager(
                profit_target=capital_config.profit_target,
                max_loss=capital_config.max_loss,
                max_trades=effective_max_trades,  # Siempre ilimitado
                profit_target_pct=capital_config.profit_target_pct,
                max_loss_pct=capital_config.max_loss_pct,
                position_sizing_method=getattr(capital_config, 'position_sizing_method', 'kelly_fractional'),
                kelly_fraction=getattr(capital_config, 'kelly_fraction', 0.25),
                risk_per_trade_pct=getattr(capital_config, 'risk_per_trade_pct', 1.0),
                anti_martingale_multiplier=getattr(capital_config, 'anti_martingale_multiplier', 1.5),
                anti_martingale_reset_on_loss=getattr(capital_config, 'anti_martingale_reset_on_loss', True),
                enable_martingale=getattr(capital_config, 'enable_martingale', False),
                martingale_multiplier=getattr(capital_config, 'martingale_multiplier', 2.0),
                martingale_base_amount=getattr(capital_config, 'martingale_base_amount', Decimal('0.10')),
                martingale_max_levels=getattr(capital_config, 'martingale_max_levels', 5),
                martingale_reset_on_win=getattr(capital_config, 'martingale_reset_on_win', True),
                atr_multiplier=getattr(capital_config, 'atr_multiplier', 2.0),
                max_risk_per_trade_pct=getattr(capital_config, 'max_risk_per_trade_pct', 2.0),
                max_drawdown_pct=getattr(capital_config, 'max_drawdown_pct', 10.0),
                reduce_size_on_drawdown=getattr(capital_config, 'reduce_size_on_drawdown', True),
                var_confidence=getattr(capital_config, 'var_confidence', 0.95),
                max_concurrent_positions=getattr(capital_config, 'max_concurrent_positions', 5),
                target_volatility=getattr(capital_config, 'target_volatility', 15.0),
            )
            
            # Risk Protection System
            self.risk_protection = RiskProtectionSystem(
                max_portfolio_risk_pct=getattr(capital_config, 'max_portfolio_risk_pct', 15.0),
                max_single_position_risk_pct=getattr(capital_config, 'max_single_position_risk_pct', 5.0),
                max_correlated_exposure_pct=getattr(capital_config, 'max_correlated_exposure_pct', 10.0),
                max_active_positions=getattr(capital_config, 'max_active_positions', 10),
                high_volatility_threshold=getattr(capital_config, 'high_volatility_threshold', 2.0),
                volatility_reduction_pct=getattr(capital_config, 'volatility_reduction_pct', 50.0),
                max_position_duration_minutes=getattr(capital_config, 'max_position_duration_minutes', 60),
                close_losing_positions_after_minutes=getattr(capital_config, 'close_losing_positions_after_minutes', 30),
                emergency_drawdown_threshold_pct=getattr(capital_config, 'emergency_drawdown_threshold_pct', 10.0),
                enable_trailing_stop=getattr(capital_config, 'enable_trailing_stop', True),
                trailing_stop_distance_pct=getattr(capital_config, 'trailing_stop_distance_pct', 1.0),
                min_profit_for_trailing_pct=getattr(capital_config, 'min_profit_for_trailing_pct', 0.5),
            )
            
            # Guardar flag de enable_emergency_stop para usar en check_emergency_conditions
            self._enable_emergency_stop = getattr(capital_config, 'enable_emergency_stop', True)
            
            return True
        except Exception as e:
            import traceback
            print(f"[ERROR] Error inicializando sistemas de capital: {e}")
            traceback.print_exc()
            return False
    
    def process_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Procesar símbolo y ejecutar operación si hay señal
        CON PROTECCIÓN AVANZADA DE RIESGO INTEGRADA
        
        Args:
            symbol: Símbolo a procesar
            
        Returns:
            Diccionario con resultado de la operación
        """
        try:
            # Inicializar sistemas de capital si no están inicializados
            if not self.capital_manager or not self.risk_protection:
                if not self._initialize_capital_systems():
                    return {
                        'status': 'error',
                        'reason': 'capital_system_init_failed'
                    }
            
            # Obtener balance actual (obtener dict completo para account_type)
            if not self._client:
                # Intentar obtener configuración del usuario
                try:
                    from trading_bot.models import DerivAPIConfig
                    api_config = DerivAPIConfig.objects.filter(is_active=True).only('api_token', 'is_demo', 'app_id').first()
                    if api_config:
                        self._client = DerivClient(
                            api_token=api_config.api_token,
                            is_demo=api_config.is_demo,
                            app_id=api_config.app_id
                        )
                    else:
                        self._client = DerivClient()
                except Exception:
                    self._client = DerivClient()
            try:
                # Obtener balance_info completo directamente (no usar cache que solo devuelve Decimal)
                balance_info = self._client.get_balance()
                # Extraer balance y account_type
                if isinstance(balance_info, dict):
                    current_balance = Decimal(str(balance_info.get('balance', 0)))
                    account_type = balance_info.get('account_type', 'demo')
                    loginid = balance_info.get('loginid', '')
                    # Si no viene account_type, determinarlo por loginid
                    if not account_type or account_type == 'demo':
                        if loginid and (loginid.startswith('VRTC') or loginid.startswith('VRT')):
                            account_type = 'demo'
                        elif loginid:
                            account_type = 'real'
                else:
                    current_balance = Decimal(str(balance_info)) if balance_info else Decimal('0')
                    account_type = 'demo'
            except Exception as e:
                # Si hay error obteniendo balance, usar caché si existe o retornar error silencioso
                # para evitar spam de errores
                if not hasattr(self, '_last_balance_error_log'):
                    self._last_balance_error_log = 0
                
                if (time.time() - self._last_balance_error_log) > 60:
                    # Solo mostrar error cada 60 segundos para evitar spam
                    print(f"⚠️ Error obteniendo balance: {str(e)[:50]}...")
                    self._last_balance_error_log = time.time()
                
                # Intentar usar balance del caché si existe
                if hasattr(self._client, '_balance_cache_value') and self._client._balance_cache_value:
                    cache_balance = self._client._balance_cache_value.get('balance', 0)
                    if cache_balance:
                        current_balance = Decimal(str(cache_balance))
                        account_type = self._client._balance_cache_value.get('account_type', 'demo')
                    else:
                        current_balance = Decimal('0')
                        account_type = 'demo'
                else:
                    current_balance = Decimal('0')  # Si hay error, asumir $0 (más seguro)
                    account_type = 'demo'
            
            # VALIDACIÓN CRÍTICA: Rechazar operaciones si balance es $0.00 o muy bajo
            MIN_BALANCE_TO_TRADE = Decimal('1.00')  # Mínimo $1.00 para operar
            if current_balance < MIN_BALANCE_TO_TRADE:
                return {
                    'status': 'rejected',
                    'reason': f'insufficient_balance',
                    'balance': float(current_balance),
                    'message': f'Balance insuficiente: ${current_balance:.2f} (mínimo requerido: ${MIN_BALANCE_TO_TRADE:.2f})'
                }
            
            # VALIDACIÓN: Advertir si es cuenta demo y balance es alto (típico de demo)
            if account_type == 'demo' and current_balance >= Decimal('10000'):
                # Esto es típico de cuenta demo, pero permitimos operar si el usuario quiere
                pass  # Por ahora permitimos, pero podríamos rechazar aquí si se desea
            
            # 0. SISTEMA ADAPTATIVO: Obtener parámetros ajustados según métricas
            adaptive_params = self.adaptive_filter_manager.get_adjusted_parameters(current_balance)
            
            # Actualizar umbrales de la estrategia con parámetros adaptativos
            if isinstance(self.strategy, StatisticalStrategy):
                self.strategy.update_adaptive_parameters(adaptive_params)
            
            # Verificar si debe pausarse el trading (modo pausa selectiva)
            metrics = self.adaptive_filter_manager.calculate_metrics(current_balance)
            
            # ACTUALIZAR PRIORIDADES DE SÍMBOLOS: Análisis de últimos 20 trades
            symbol_performance = self.adaptive_filter_manager.calculate_symbol_performance(lookback=20)
            
            # Actualizar symbol_priorities con los scores calculados
            for symbol, perf in symbol_performance.items():
                self.symbol_priorities[symbol] = perf['score']
            
            # NUEVA LÓGICA: Si winrate de últimos 20 trades < 52%, usar solo top 5 símbolos
            allowed_symbols = None  # None = todos los símbolos permitidos
            if metrics.win_rate_recent < 0.52 and len(symbol_performance) > 0:
                # Obtener top 5 símbolos por desempeño
                top_symbols = self.adaptive_filter_manager.get_top_symbols_by_performance(lookback=20, top_n=5)
                allowed_symbols = [s[0] for s in top_symbols]
                print(f"📊 Winrate últimos 20 trades: {metrics.win_rate_recent:.1%} < 52%. Usando solo top 5 símbolos: {allowed_symbols}")
            
            # CONTROL DE PÉRDIDAS: Si winrate < 52%, solo permitir top 5 símbolos
            if allowed_symbols is not None and symbol not in allowed_symbols:
                symbol_score = self.symbol_priorities.get(symbol, 0)
                top_symbols_str = ', '.join(allowed_symbols[:3]) + ('...' if len(allowed_symbols) > 3 else '')
                return {
                    'status': 'rejected',
                    'reason': 'low_winrate_filter',
                    'message': f'⏸️ Winrate {metrics.win_rate_recent:.1%} < 52%. Solo top 5 símbolos permitidos. {symbol} (score: {symbol_score:.2f}) no está en la lista.'
                }
            
            # Verificar pausa solo en casos extremos (drawdown > 15% o racha >= 5)
            pause_info = self.adaptive_filter_manager.should_pause_trading(metrics, best_symbol=None)
            
            if pause_info['should_pause']:
                # Solo en casos extremos: pausa completa
                return {
                    'status': 'rejected',
                    'reason': 'adaptive_pause',
                    'message': f'Trading pausado: Drawdown {metrics.drawdown_pct:.1%} o racha perdedora {metrics.losing_streak}'
                }
            
            # MODO CONSERVADOR LIGERO si hay racha perdedora o drawdown elevados
            conservative_mode = False
            try:
                if getattr(metrics, 'losing_streak', 0) >= 3:
                    conservative_mode = True
                if getattr(metrics, 'drawdown_pct', 0.0) >= 0.05:
                    conservative_mode = True
            except Exception:
                conservative_mode = False
            
            # 1. VERIFICACIÓN DE CAPITAL MANAGER (metas diarias, drawdown, etc.)
            # max_trades siempre ilimitado - operación perpetua
            # No es necesario verificar ni actualizar, siempre es ilimitado
            
            can_trade, capital_reason = self.capital_manager.can_trade(current_balance)
            if not can_trade:
                # En modo recuperación, no bloquear; seguir con filtros más estrictos
                if getattr(self, 'recovery_mode', False):
                    pass
                else:
                    print(f"  ❌ {symbol}: Capital manager rechazó: {capital_reason}")
                    return {
                        'status': 'rejected',
                        'reason': f'capital_manager: {capital_reason}'
                    }
            
            # 2. VERIFICACIÓN DE EMERGENCIA (caídas súbitas)
            if self._enable_emergency_stop:
                emergency_active, emergency_reason = self.risk_protection.check_emergency_conditions(current_balance)
                if emergency_active:
                    return {
                        'status': 'rejected',
                        'reason': f'EMERGENCY: {emergency_reason}'
                    }
            
            # Excluir explícitamente BOOM/CRASH (no ofrecidos en esta cuenta en modo binario)
            if symbol.startswith('BOOM') or symbol.startswith('CRASH'):
                return {
                    'status': 'no_signal',
                    'reason': 'asset_not_offered'
                }

            # Verificar si han pasado suficientes segundos desde la última entrada
            now = timezone.now()
            last_trade = self.last_trade_time.get(symbol)
            
            # Intervalo dinámico por símbolo según prioridad (mejor score => menor intervalo)
            score = self.symbol_priorities.get(symbol, 0.5)
            if score >= 0.65:
                sym_interval = timedelta(seconds=15)
            elif score <= 0.45:
                sym_interval = timedelta(seconds=90)
            else:
                sym_interval = timedelta(seconds=30)

            if last_trade and (now - last_trade) < sym_interval:
                return {
                    'status': 'waiting',
                    'reason': 'interval_limit',
                    'next_allowed': (last_trade + sym_interval).isoformat()
                }
            
            # Analizar símbolo con todas las estrategias
            signal_primary = self.strategy.analyze_symbol(symbol)
            signal_secondary = self.strategy_ema.analyze_symbol(symbol)
            signal_ticks = self.strategy_ticks.analyze_symbol(symbol)
            signal_reversal = self.strategy_reversal.analyze_symbol(symbol)
            
            # Elegir la mejor por confianza si todas existen; si solo una existe, usar esa
            signal = None
            strategy_origin = 'unknown'
            
            if signal_primary and hasattr(signal_primary, 'confidence'):
                signal = signal_primary
                strategy_origin = 'statistical_hybrid'
            
            if signal_secondary and hasattr(signal_secondary, 'confidence'):
                if (signal is None) or (getattr(signal_secondary, 'confidence', 0) > getattr(signal, 'confidence', 0)):
                    signal = signal_secondary
                    strategy_origin = 'ema200_extrema'
            
            # Integrar señal Tick-Based usando proxy de confianza
            if signal_ticks and hasattr(signal_ticks, 'force_pct'):
                try:
                    proxy_conf = max(0.0, min(1.0, float(signal_ticks.force_pct) / 100.0))
                except Exception:
                    proxy_conf = 0.0
                setattr(signal_ticks, 'confidence', proxy_conf)
                if (signal is None) or (proxy_conf > getattr(signal, 'confidence', 0)):
                    signal = signal_ticks
                    strategy_origin = 'tick_based'
            
            # Integrar señal de Reversión (cuarta estrategia)
            if signal_reversal and hasattr(signal_reversal, 'confidence'):
                if (signal is None) or (getattr(signal_reversal, 'confidence', 0) > getattr(signal, 'confidence', 0)):
                    signal = signal_reversal
                    strategy_origin = 'momentum_reversal'
            
            # Marcar origen de estrategia seleccionado (para trazabilidad)
            if signal is not None:
                setattr(signal, 'strategy_origin', strategy_origin)
            
            if not signal:
                # No hay señal - omitir silenciosamente (no registrar)
                return {
                    'status': 'skipped',
                    'reason': 'no_clear_trend',
                    'message': f'Símbolo {symbol} sin señal clara, omitido'
                }
            
            # LOG: Señal generada - mostrar para debugging
            if hasattr(signal, 'force_pct') and signal.force_pct > 0:
                print(f"📡 {symbol}: Señal generada ({signal.direction}), fuerza: {signal.force_pct:.6f}%, confianza: {getattr(signal, 'confidence', 'N/A')}")
            
            # Verificar si debe entrar (validación genérica basada en confianza)
            should_enter = False
            if hasattr(self.strategy, 'should_enter_trade'):
                try:
                    should_enter = self.strategy.should_enter_trade(signal)
                except Exception:
                    # Si la estrategia no puede validar, usar validación genérica
                    should_enter = False
            
            # Validación genérica para señales con confidence
            if not should_enter and hasattr(signal, 'confidence'):
                # Umbral mínimo de confianza (ajustable según estrategia)
                min_confidence = 0.50  # Base
                if strategy_origin == 'momentum_reversal':
                    min_confidence = 0.50  # La estrategia de reversión ya filtra en analyze_symbol
                elif strategy_origin == 'ema200_extrema':
                    min_confidence = 0.60
                elif strategy_origin == 'tick_based':
                    min_confidence = 0.40  # Más laxo para ticks
                else:
                    min_confidence = 0.50
                
                if signal.confidence >= min_confidence:
                    should_enter = True
            
            if not should_enter:
                # Insuficiente confianza - mostrar razón para debugging
                confidence = getattr(signal, 'confidence', 'N/A')
                force_pct = getattr(signal, 'force_pct', 'N/A')
                print(f"  ⚠️ {symbol}: Confianza insuficiente (conf: {confidence}, fuerza: {force_pct})")
                
                if hasattr(signal, 'force_pct'):
                    reason_data = {'force_pct': signal.force_pct}
                elif hasattr(signal, 'confidence'):
                    reason_data = {'confidence': signal.confidence}
                else:
                    reason_data = {}
                
                return {
                    'status': 'skipped',
                    'reason': 'insufficient_confidence',
                    'message': f'Símbolo {symbol} con confianza insuficiente, omitido',
                    **reason_data
                }
            
            # Endurecimiento ligero en modo conservador o recuperación: exigir confianza algo mayor
            try:
                if (conservative_mode or getattr(self, 'recovery_mode', False)) and hasattr(signal, 'confidence') and signal.confidence is not None:
                    # Base normal 0.62; en recuperación 0.58
                    if getattr(self, 'recovery_mode', False):
                        min_conf = 0.58
                    else:
                        min_conf = 0.62
                    # Pacing: si no hubo ejecutados en 10 minutos, relajar -0.04 temporal
                    try:
                        if self._last_executed_time is None or (timezone.now() - self._last_executed_time).total_seconds() > 600:
                            min_conf = max(0.54, min_conf - 0.04)
                    except Exception:
                        pass
                    if float(signal.confidence) < min_conf:
                        print(f"  ⚠️ {symbol}: Filtro conservador activo (conf: {signal.confidence:.2f} < {min_conf:.2f})")
                        return {
                            'status': 'skipped',
                            'reason': 'conservative_confidence',
                            'message': f'Confianza {signal.confidence:.2f} < mínimo {min_conf:.2f} (filtro adaptativo)'
                        }
            except Exception:
                pass

            # Control de volatilidad (ATR) por clase de activo para evitar extremos
            try:
                atr_ratio_chk = getattr(signal, 'atr_ratio', None)
                if atr_ratio_chk is not None:
                    if symbol.startswith('frx'):
                        low, high = (0.00015, 0.0220)
                    else:
                        low, high = (0.0015, 0.0550)
                    # En recuperación ya no estrechamos más; usamos rangos ampliados
                    if not (low <= float(atr_ratio_chk) <= high):
                        # Si la confianza es muy alta, permitir pero reducimos stake posteriormente
                        high_conf_allow = hasattr(signal, 'confidence') and float(getattr(signal, 'confidence', 0)) >= 0.75
                        if high_conf_allow:
                            pass
                        else:
                            return {
                                'status': 'skipped',
                                'reason': 'volatility_out_of_range',
                                'message': f'ATR% fuera de rango ({atr_ratio_chk:.4f} no está entre {low:.4f} y {high:.4f})'
                            }
            except Exception:
                pass
            
            # Sin límite de trades simultáneos: permitir múltiples entradas si cumplen condiciones

            # 3. CALCULAR TAMAÑO DE POSICIÓN USANDO ADVANCED CAPITAL MANAGER
            # Obtener precio actual y ATR
            latest_tick = Tick.objects.filter(symbol=symbol).order_by('-timestamp').first()
            entry_price = Decimal(str(latest_tick.price)) if latest_tick else Decimal('1.0')
            atr_value = Decimal(str(getattr(signal, 'atr_ratio', 0.0) * float(entry_price))) if hasattr(signal, 'atr_ratio') else None
            
            # Calcular tamaño óptimo de posición
            position_size_result = self.capital_manager.get_recommended_position_size(
                current_balance=current_balance,
                symbol=symbol,
                entry_price=entry_price,
                stop_loss_price=None,  # Para opciones binarias no hay stop loss tradicional
                atr_value=atr_value
            )
            
            # Convertir riesgo a monto de contrato (simplificado: 1 contrato = $1)
            # En opciones binarias, el monto es el stake
            base_risk = position_size_result.risk_amount

            # 4. APLICAR AJUSTES SEGÚN ESTRATEGIA
            # MARTINGALA DESACTIVADA: forzar martingale_active=False
            martingale_active = False
            if martingale_active:
                final_risk = base_risk
                protection_applied = None
            else:
                # Modo normal: aplicar multiplicador adaptativo y protecciones
                position_multiplier = adaptive_params.position_size_multiplier
                adjusted_base_risk = base_risk * Decimal(str(position_multiplier))
                
                if position_multiplier < 1.0:
                    print(f"  ⚠️ {symbol}: Tamaño de posición reducido en {(1-position_multiplier)*100:.0f}% (Drawdown: {metrics.drawdown_pct:.1%})")
                
                # 5. VALIDAR CON SISTEMA DE PROTECCIÓN DE RIESGO
                risk_check = self.risk_protection.validate_new_position(
                    symbol=symbol,
                    base_risk=adjusted_base_risk,
                    current_balance=current_balance
                )
                
                if not risk_check.allowed:
                    return {
                        'status': 'rejected',
                        'reason': f'risk_protection: {risk_check.reason}',
                        'protection_applied': risk_check.protection_applied
                    }
                
                # Usar tamaño ajustado si fue modificado por protecciones
                final_risk = risk_check.adjusted_size if risk_check.adjusted_size else adjusted_base_risk
                protection_applied = risk_check.protection_applied
            
            # Monto dinámico basado en desempeño de últimos 20 trades del activo específico
            # Obtener score de desempeño del símbolo (últimos 20 trades)
            symbol_perf = self.adaptive_filter_manager.calculate_symbol_performance(lookback=20)
            
            if symbol in symbol_perf:
                # Usar score del activo específico (0-1) -> $0.35 - $1.00
                score = symbol_perf[symbol]['score']
                amount = 0.35 + (0.65 * float(score))
                print(f"  💰 {symbol}: Score últimos 20 trades = {score:.3f} → Monto = ${amount:.2f}")
            else:
                # Si no hay suficientes trades del activo, usar score promedio o mínimo
                # Calcular promedio de scores de todos los símbolos con datos
                if symbol_perf:
                    avg_score = sum(p['score'] for p in symbol_perf.values()) / len(symbol_perf)
                    amount = 0.35 + (0.65 * float(avg_score))
                    print(f"  ⚠️ {symbol}: Sin datos suficientes, usando score promedio = {avg_score:.3f} → Monto = ${amount:.2f}")
                else:
                    # Si no hay ningún dato, usar mínimo
                    amount = 0.35
                    print(f"  ⚠️ {symbol}: Sin datos históricos, usando monto mínimo = ${amount:.2f}")
            
            amount = round(amount, 2)

            # En recuperación: bajar un 20% adicional el tamaño, respetando $0.35
            if getattr(self, 'recovery_mode', False):
                amount = max(0.35, round(amount * 0.8, 2))

            # Si ATR fuera de rango pero se permitió por alta confianza, reducir stake extra 30%
            try:
                atr_ratio_chk = getattr(signal, 'atr_ratio', None)
                if atr_ratio_chk is not None:
                    if symbol.startswith('frx'):
                        low, high = (0.00015, 0.0220)
                    else:
                        low, high = (0.0015, 0.0550)
                    if not (low <= float(atr_ratio_chk) <= high) and float(getattr(signal, 'confidence', 0)) >= 0.75:
                        # Aplicar reducción adicional en drawdown, manteniendo rango $0.35-$1.00
                        amount = max(0.35, round(amount * 0.8, 2))
            except Exception:
                pass
            
            # Obtener parámetros de la operación - DURACIÓN DINÁMICA ADAPTATIVA
            # Base por clase de activo + factor por volatilidad (ATR ratio)
            atr_ratio = getattr(signal, 'atr_ratio', 0.0)
            if symbol.startswith('frx'):
                # Forex: usar 1 minuto (60 segundos) para opciones binarias
                base = 60
                atr_baseline = 0.0006
                allowed = [60]  # 1 minuto para forex en binarias
            else:
                # Símbolos sintéticos y otros: usar 30 segundos
                base = 30
                atr_baseline = 0.0030
                allowed = [30, 60, 120, 180, 300, 600, 900]

            factor = 1.0
            if atr_baseline > 0:
                factor = max(0.5, min(2.0, (atr_ratio / atr_baseline) if atr_ratio > 0 else 1.0))
            raw_duration = int(round(base * factor))
            # Elegir bucket permitido más cercano
            duration = min(allowed, key=lambda d: abs(d - raw_duration))
            
            # Obtener parámetros de trade (genérico para todas las estrategias)
            try:
                if hasattr(self.strategy, 'get_trade_params'):
                    trade_params = self.strategy.get_trade_params(signal, duration=duration)
                else:
                    # Extraer parámetros directamente de la señal
                    entry_price = getattr(signal, 'entry_price', None)
                    if entry_price is None:
                        # Obtener último precio del símbolo
                        last_tick = Tick.objects.filter(symbol=symbol).order_by('-timestamp').first()
                        if last_tick:
                            entry_price = Decimal(str(last_tick.price))
                        else:
                            entry_price = Decimal('0')
                    
                    trade_params = {
                        'direction': signal.direction,
                        'entry_price': float(entry_price),
                        'duration': duration,
                        'basis': 'stake',
                        'amount': 1.0
                    }
                    # Agregar campos adicionales si existen
                    if hasattr(signal, 'confidence'):
                        trade_params['confidence'] = signal.confidence
                    if hasattr(signal, 'signal_type'):
                        trade_params['signal_type'] = signal.signal_type
            except Exception as e:
                # Fallback: construir parámetros básicos
                entry_price = getattr(signal, 'entry_price', None)
                if entry_price is None:
                    last_tick = Tick.objects.filter(symbol=symbol).order_by('-timestamp').first()
                    entry_price = Decimal(str(last_tick.price)) if last_tick else Decimal('0')
                
                trade_params = {
                    'direction': signal.direction,
                    'entry_price': float(entry_price),
                    'duration': duration,
                    'basis': 'stake',
                    'amount': 1.0
                }
            
            # Convertir dirección a lado (buy/sell)
            side = 'buy' if signal.direction == 'CALL' else 'sell'
            
            # Asegurar mínimo operativo local $0.35 (Deriv puede pedir >$0.35 y se reintenta con el mínimo exigido)
            amount = max(0.35, amount)
            
            amount = round(amount, 2)  # Deriv requiere máximo 2 decimales
            
            # VALIDACIÓN FINAL: Verificar que el amount no exceda el balance disponible
            # Para opciones binarias, el amount es el stake que se arriesga
            if float(current_balance) < amount:
                return {
                    'status': 'rejected',
                    'reason': 'insufficient_balance_for_trade',
                    'balance': float(current_balance),
                    'requested_amount': amount,
                    'account_type': account_type,
                    'message': f'Balance insuficiente: ${current_balance:.2f} < ${amount:.2f} (monto solicitado)'
                }
            
            # Ejecutar orden
            result = self.place_binary_option(
                symbol=symbol,
                side=side,
                amount=amount,
                duration=duration,
                martingale_active=martingale_active
            )
            
            # Actualizar estado del capital manager después de trade
            if result.get('accepted'):
                # El trade se registró como pending, la actualización de martingala
                # se hará cuando el contrato expire y se actualice el status
                self._last_executed_time = timezone.now()
            
            # Guardar información de riesgo en el resultado para logging
            if result.get('accepted'):
                result['risk_amount'] = float(final_risk)
                result['position_sizing_method'] = position_size_result.method_used
                # Asegurar que el monto real usado esté en el resultado
                if 'amount' not in result:
                    result['amount'] = amount  # Monto final usado (después de ajustes)
                
                # Actualizar balance cacheado si viene en la respuesta
                if 'balance_after' in result:
                    try:
                        self._balance_cache.update(Decimal(str(result['balance_after'])))
                        
                        # También actualizar el caché del DerivClient compartido
                        # PRESERVAR account_type del resultado en lugar de hardcodear 'demo'
                        if '_shared_deriv_client' in globals():
                            try:
                                # Preservar account_type del resultado o del caché actual
                                current_account_type = result.get('account_type')
                                if not current_account_type and _shared_deriv_client._balance_cache_value:
                                    current_account_type = _shared_deriv_client._balance_cache_value.get('account_type', 'demo')
                                if not current_account_type:
                                    current_account_type = 'demo'  # Último recurso
                                
                                _shared_deriv_client._balance_cache_value = {
                                    'balance': float(result['balance_after']),
                                    'currency': 'USD',
                                    'account_type': current_account_type  # ← USAR EL QUE VINO
                                }
                                _shared_deriv_client._balance_cache_time = time.time()
                            except Exception:
                                pass
                    except Exception:
                        pass
            
            # Registrar operación SOLO si no es un símbolo omitido
            # Si el resultado indica 'not_available', 'rate_limit' o 'skip_record', NO registrar
            skip_reasons = ['not_available', 'rate_limit']
            if result.get('skip_record') or result.get('reason') in skip_reasons:
                # Símbolo no disponible, rate limit, o no da ganancias - omitir silenciosamente
                reason = result.get('reason', 'not_available')
                if reason == 'rate_limit':
                    return {
                        'status': 'skipped',
                        'reason': 'rate_limit',
                        'message': f'Rate limit alcanzado para {symbol}, omitido temporalmente'
                    }
                return {
                    'status': 'skipped',
                    'reason': result.get('reason', 'not_available'),
                    'message': f'Símbolo {symbol} no disponible, omitido'
                }
            
            # IMPORTANTE: Pasar el monto final usado (después de ajustes) a record_trade
            # El monto real está en result['amount'] (después de ajustes en place_binary_option)
            final_amount_used = None
            if result.get('accepted'):
                # Prioridad 1: result['amount'] (monto REAL usado después de todos los ajustes)
                final_amount_used = result.get('amount')
                if not final_amount_used:
                    # Fallback: usar amount (pero esto es el monto ANTES de ajustes, no ideal)
                    final_amount_used = amount
                    print(f"⚠️ WARNING: result['amount'] no disponible para {symbol}, usando amount pre-ajustes: {amount}")
            else:
                final_amount_used = 0.0
            
            self.record_trade(symbol, signal, result, position_size_info={
                'risk_amount': float(final_risk),
                'amount': final_amount_used,  # Monto REAL usado (después de ajustes)
                'method': position_size_result.method_used,
                'confidence': position_size_result.confidence
            })
            
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
                # Campos específicos según estrategia
                if hasattr(signal, 'signal_type'):
                    signal_info['signal_type'] = signal.signal_type
                if hasattr(signal, 'z_score'):
                    signal_info['z_score'] = signal.z_score
                if isinstance(signal, EMAExtremaSignal):
                    signal_info['signal_type'] = 'ema200_extrema'
                    signal_info['ema200'] = str(signal.ema200)
                    signal_info['recent_high'] = str(signal.recent_high)
                    signal_info['recent_low'] = str(signal.recent_low)
            if hasattr(signal, 'upward_ticks_pct'):
                signal_info['upward_pct'] = signal.upward_ticks_pct
            
            return {
                'status': 'executed' if result.get('accepted') else 'rejected',
                'signal': signal_info,
                'result': result,
                'position_size': {
                    'amount': amount,
                    'risk_amount': float(final_risk),
                    'method': position_size_result.method_used,
                    'confidence': position_size_result.confidence,
                    'protections_applied': protection_applied
                }
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def place_binary_option(self, symbol: str, side: str, amount: float, duration: int, martingale_active: bool = False) -> Dict[str, Any]:
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
        
        # Reusar un solo cliente a nivel de módulo para evitar reconexiones constantes
        global _shared_deriv_client
        try:
            _shared_deriv_client
        except NameError:
            # Intentar obtener configuración del usuario
            try:
                from trading_bot.models import DerivAPIConfig
                api_config = DerivAPIConfig.objects.filter(is_active=True).only('api_token', 'is_demo', 'app_id').first()
                if api_config:
                    _shared_deriv_client = DerivClient(
                        api_token=api_config.api_token,
                        is_demo=api_config.is_demo,
                        app_id=api_config.app_id
                    )
                else:
                    _shared_deriv_client = DerivClient()
            except Exception:
                _shared_deriv_client = DerivClient()
        client = _shared_deriv_client
        
        try:
            # PASO 1: CONECTAR Y AUTENTICAR
            print(f"  🔐 {symbol}: Verificando conexión...")
            if not client.connected or not client.ws or not client.ws.sock or not client.ws.sock.connected:
                print(f"  🔐 {symbol}: Conectando y autenticando...")
                if not client.authenticate():
                    return {
                        'accepted': False,
                        'reason': 'auth_failed',
                        'error_message': 'No se pudo autenticar con Deriv'
                    }
            
            # PASO 2: VALIDAR Y AJUSTAR AMOUNT
            amount = round(float(amount), 2)
            
            # Aplicar límites desde configuración
            try:
                from engine.models import CapitalConfig
                config = CapitalConfig.get_active()
                
                # Mínimo
                if martingale_active:
                    # En martingala respetamos mínimos de $0.10
                    min_allowed = float(getattr(config, 'martingale_base_amount', 0.10))
                    if amount < min_allowed:
                        amount = min_allowed
                        amount = round(amount, 2)
                else:
                    # Permitir mínimos desde $0.35 para la asignación dinámica
                    if amount < config.min_amount_per_trade:
                        amount = max(float(amount), 0.35)
                        amount = round(amount, 2)
                
                # Máximo
                if amount > config.max_amount_absolute:
                    amount = config.max_amount_absolute
                    amount = round(amount, 2)
                
                # Específico del símbolo
                max_by_symbol = config.get_symbol_limit(symbol)
                if max_by_symbol and amount > max_by_symbol:
                    amount = min(amount, max_by_symbol)
                    amount = round(amount, 2)
            except Exception:
                # Valores por defecto
                if amount < 1.0:
                    amount = 1.0
                if amount > 500.0:
                    amount = 500.0
                amount = round(amount, 2)
            
            # PASO 3: OBTENER ASK PRICE DEL PROPOSAL (REQUERIDO PARA 'price' EN BUY)
            contract_type = 'CALL' if side == 'buy' else 'PUT'
            ask_price = None
            
            try:
                client.response_event.clear()
                proposal_req = {
                    "proposal": 1,
                    "amount": float(amount),
                    "basis": "stake",
                    "contract_type": contract_type,
                    "currency": "USD",
                    "duration": duration,
                    "duration_unit": "s",
                    "symbol": symbol,
                }
                
                # Verificar conexión antes de enviar proposal
                if not client.ws or not client.ws.sock or not client.ws.sock.connected:
                    if not client.authenticate():
                        return {'accepted': False, 'reason': 'ws_disconnected', 'error_message': 'WebSocket desconectado'}
                
                client.ws.send(json.dumps(proposal_req))
                print(f"  📊 {symbol}: Enviado proposal para obtener ask_price...")
                
                if client.response_event.wait(timeout=5):
                    proposal_data = client.response_data
                    
                    # Manejar errores en proposal
                    if proposal_data.get("error"):
                        error_info = proposal_data.get("error", {})
                        error_code = error_info.get('code', '') if isinstance(error_info, dict) else ''
                        error_message = error_info.get('message', '') if isinstance(error_info, dict) else str(error_info)
                        
                        # Si el error es de disponibilidad, intentar reintento por mínimo requerido si aplica
                        if error_code in ['InvalidSymbol', 'NotAvailable', 'InvalidOfferings', 'PermissionDenied', 'OfferingsValidationError', 'ContractCreationFailure']:
                            # Reintento único si el mensaje trae "at least X" (mínimo de stake)
                            min_required = None
                            try:
                                import re
                                m = re.search(r"at least\s*([0-9]+(?:\.[0-9]+)?)", error_message)
                                if m:
                                    min_required = float(m.group(1))
                            except Exception:
                                min_required = None
                            
                            if min_required is not None:
                                retry_amount = max(float(amount), float(min_required))
                                retry_amount = round(retry_amount, 2)
                                print(f"  🔁 {symbol}: Reintentando con mínimo requerido ${retry_amount:.2f} (anterior ${float(amount):.2f})")
                                amount = retry_amount
                                # Reintenta proposal UNA vez con el nuevo amount
                                try:
                                    client.response_event.clear()
                                    proposal_req['amount'] = float(amount)
                                    client.ws.send(json.dumps(proposal_req))
                                    if client.response_event.wait(timeout=5):
                                        proposal_data = client.response_data
                                        if proposal_data.get("error"):
                                            # Si vuelve a fallar, omitir
                                            return {
                                                'accepted': False,
                                                'reason': 'not_available',
                                                'error_code': error_code,
                                                'error_message': error_message,
                                                'skip_record': True
                                            }
                                        else:
                                            proposal = proposal_data.get("proposal", {})
                                            ask_price = proposal.get('ask_price', float(amount))
                                            ask_price = round(float(ask_price), 2)
                                            print(f"  💰 {symbol}: Ask price (reintento) ${ask_price:.2f}")
                                    else:
                                        # Timeout reintento: usar amount como price
                                        ask_price = float(amount)
                                except Exception:
                                    ask_price = float(amount)
                            else:
                                print(f"  ⏭️ {symbol}: Símbolo no disponible, omitiendo silenciosamente | {error_code}: {error_message}")
                                return {
                                    'accepted': False,
                                    'reason': 'not_available',  # Código especial para omitir
                                    'error_code': error_code,
                                    'error_message': error_message,
                                    'skip_record': True  # No registrar en BD
                                }
                        # Para otros errores, intentar igual con amount como price
                        ask_price = float(amount)
                        print(f"  ⚠️ {symbol}: Error en proposal ({error_code}) pero continuando con amount como price")
                    elif proposal_data.get("proposal"):
                        proposal = proposal_data["proposal"]
                        ask_price = proposal.get('ask_price', 0)
                        
                        if ask_price and ask_price > 0:
                            ask_price = round(ask_price, 2)
                            print(f"  💰 {symbol}: Ask price obtenido: ${ask_price:.2f}")
                        else:
                            # Si no hay ask_price, usar amount (para stake basis)
                            ask_price = float(amount)
                            print(f"  ⚠️ {symbol}: No ask_price en proposal, usando amount: ${ask_price:.2f}")
                    else:
                        # Respuesta inesperada
                        ask_price = float(amount)
                        print(f"  ⚠️ {symbol}: Respuesta proposal inesperada, usando amount: ${ask_price:.2f}")
                else:
                    # Timeout en proposal
                    ask_price = float(amount)
                    print(f"  ⚠️ {symbol}: Timeout en proposal, usando amount como price: ${ask_price:.2f}")
            except Exception as e:
                # Si falla proposal, usar amount
                ask_price = float(amount)
                print(f"  ⚠️ {symbol}: Error obteniendo proposal: {e}, usando amount: ${ask_price:.2f}")
            
            # PASO 4: CONSTRUIR MENSAJE BUY (FORMATO CORRECTO DE DERIV)
            buy_msg = {
                'buy': 1,
                'price': ask_price,  # Usar ask_price del proposal
                'parameters': {
                    'contract_type': contract_type,
                    'symbol': symbol,
                    'amount': amount,
                    'duration': duration,
                    'duration_unit': 's',
                    'basis': 'stake',
                    'currency': 'USD'
                }
            }
            
            print(f"  📋 {symbol}: Mensaje buy preparado | {side.upper()} | Amount: ${amount:.2f} | Price: ${ask_price:.2f} | Duration: {duration}s")
            
            # PASO 5: VERIFICAR CONEXIÓN FINAL
            if not client.ws or not client.ws.sock or not client.ws.sock.connected:
                print(f"  🔄 {symbol}: Reconectando antes de enviar orden...")
                if not client.authenticate():
                    return {
                        'accepted': False,
                        'reason': 'ws_disconnected',
                        'error_message': 'WebSocket desconectado y falló reconexión'
                    }
            
            # PASO 6: ENVIAR ORDEN
            try:
                client.response_event.clear()
                client.ws.send(json.dumps(buy_msg))
                print(f"  📤 {symbol}: Orden enviada a Deriv | {side.upper()} | ${amount:.2f} | ${ask_price:.2f} | {duration}s")
            except Exception as send_error:
                error_msg = f"Error enviando orden: {send_error}"
                print(f"  ❌ {symbol}: {error_msg}")
                return {
                    'accepted': False,
                    'reason': 'send_error',
                    'error_message': error_msg
                }
            
            # PASO 7: ESPERAR RESPUESTA
            if client.response_event.wait(timeout=15):  # Aumentado a 15s
                data = client.response_data
                
                # PASO 8: MANEJAR ERRORES
                if data.get('error'):
                    error_info = data['error']
                    error_code = error_info.get('code', 'unknown') if isinstance(error_info, dict) else 'unknown'
                    error_message = error_info.get('message', str(error_info)) if isinstance(error_info, dict) else str(error_info)
                    
                    # Si el error es de disponibilidad, OMITIR (no rechazar, no registrar)
                    if error_code in ['InvalidSymbol', 'NotAvailable', 'InvalidOfferings', 'PermissionDenied', 'OfferingsValidationError', 'ContractCreationFailure']:
                        print(f"  ⏭️ {symbol}: Símbolo no disponible, omitiendo silenciosamente | {error_code}: {error_message}")
                        return {
                            'accepted': False,
                            'reason': 'not_available',  # Código especial para omitir
                            'error_code': error_code,
                            'error_message': error_message,
                            'error_data': error_info,
                            'skip_record': True  # No registrar en BD
                        }
                    
                    # Si el error es RateLimit, OMITIR (no rechazar, esperar y reintentar después)
                    if error_code == 'RateLimit':
                        print(f"  ⏸️ {symbol}: Rate limit alcanzado, omitiendo temporalmente | Esperar antes de reintentar")
                        return {
                            'accepted': False,
                            'reason': 'rate_limit',  # Código especial para omitir temporalmente
                            'error_code': error_code,
                            'error_message': error_message,
                            'error_data': error_info,
                            'skip_record': True  # No registrar en BD (error temporal)
                        }
                    
                    # Para otros errores (balance insuficiente, etc.), SÍ registrar como rejected
                    print(f"  ❌ {symbol}: Deriv rechazó la orden | Código: {error_code} | Mensaje: {error_message}")
                    
                    return {
                        'accepted': False,
                        'reason': f"ws_error: {error_code}",
                        'error_code': error_code,
                        'error_message': error_message,
                        'error_data': error_info
                    }
                
                # PASO 9: MANEJAR RESPUESTA EXITOSA
                result = data.get('buy', {})
                if result:
                    final_amount_used = buy_msg['parameters']['amount']
                    contract_id = result.get('contract_id')
                    balance_after = result.get('balance_after', 0)
                    
                    print(f"  ✅ {symbol} {side.upper()} ACEPTADO | Contract ID: {contract_id} | Balance después: ${balance_after:.2f}")
                    
                    return {
                        'accepted': True,
                        'order_id': contract_id,
                        'buy_price': result.get('buy_price'),
                        'payout': result.get('payout'),
                        'balance_after': balance_after,
                        'amount': final_amount_used
                    }
                else:
                    # Respuesta sin 'buy' ni 'error'
                    print(f"  ⚠️ {symbol}: Respuesta sin 'buy' ni 'error': {data}")
                    return {
                        'accepted': False,
                        'reason': 'no_response',
                        'response_data': data
                    }
            else:
                # Timeout esperando respuesta
                error_msg = f"Timeout esperando respuesta de Deriv (15s)"
                print(f"  ❌ {symbol}: {error_msg}")
                return {
                    'accepted': False,
                    'reason': 'timeout',
                    'error_message': error_msg
                }
                
        except Exception as e:
            print(f"  ❌ {symbol}: EXCEPCIÓN: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                'accepted': False,
                'reason': 'exception',
                'error_message': str(e)
            }
    
    def record_trade(self, symbol: str, signal, result: Dict[str, Any], position_size_info: Optional[Dict[str, Any]] = None):
        """
        Registrar operación en OrderAudit
        
        Args:
            symbol: Símbolo
            signal: Señal de trading (TrendSignal o StatisticalSignal)
            result: Resultado de la operación
            position_size_info: Información de tamaño de posición calculado
        """
        try:
            # Construir payload según el tipo de señal
            request_payload = {
                'direction': signal.direction,
                'entry_price': signal.entry_price
            }
            
            # Agregar campos específicos según el tipo de señal
            # Primero verificar si es EMAExtremaSignal (estrategia 2)
            from engine.services.ema200_extrema_strategy import EMAExtremaSignal
            if isinstance(signal, EMAExtremaSignal):
                # EMA200ExtremaStrategy (estrategia 2)
                request_payload.update({
                    'confidence': signal.confidence,
                    'ema200': str(signal.ema200),
                    'recent_high': str(signal.recent_high),
                    'recent_low': str(signal.recent_low),
                    'atr_ratio': signal.atr_ratio,
                    'strategy': 'ema200_extrema'
                })
            elif hasattr(signal, 'force_pct'):
                # TrendSignal (estrategia antigua)
                request_payload.update({
                    'force_pct': signal.force_pct,
                    'upward_pct': signal.upward_ticks_pct,
                    'strategy': 'tick_based'
                })
            elif hasattr(signal, 'confidence'):
                # StatisticalSignal (estrategia 1)
                request_payload.update({
                    'confidence': signal.confidence,
                    'signal_type': signal.signal_type,
                    'z_score': signal.z_score,
                    'mean_price': signal.mean_price,
                    'current_position': signal.current_position,
                    'strategy': 'statistical_hybrid'
                })
            
            # Adjuntar estrategia si viene marcada por el caller
            try:
                origin = getattr(signal, 'strategy_origin', None)
                if origin and isinstance(origin, str):
                    request_payload['strategy'] = origin
                    
                    # Guardar campos adicionales según la estrategia
                    if origin == 'momentum_reversal' and isinstance(signal, MomentumReversalSignal):
                        request_payload['fatigue_count'] = signal.fatigue_count
                        request_payload['momentum_extreme'] = signal.momentum_extreme
                        request_payload['divergence_score'] = signal.divergence_score
                        request_payload['signal_type'] = signal.signal_type
            except Exception:
                pass

            # Agregar información de posición sizing
            if position_size_info:
                request_payload['position_sizing'] = position_size_info

            # Asegurar que SIEMPRE haya una confianza presente en el payload
            calculated_confidence = None
            try:
                # 1) Preferir confianza de la señal estadística
                if hasattr(signal, 'confidence') and signal.confidence is not None:
                    calculated_confidence = float(signal.confidence)
                # 2) Luego, confianza calculada por el position sizing (si existe)
                elif position_size_info and position_size_info.get('confidence') is not None:
                    calculated_confidence = float(position_size_info.get('confidence'))
                # 3) Derivar proxy para estrategia tick-based usando force_pct (0-100 → 0-1)
                elif hasattr(signal, 'force_pct') and signal.force_pct is not None:
                    try:
                        fp = float(signal.force_pct)
                        calculated_confidence = max(0.0, min(1.0, fp / 100.0))
                    except Exception:
                        calculated_confidence = None
            except Exception:
                calculated_confidence = None

            # 4) Fallback conservador
            if calculated_confidence is None:
                calculated_confidence = 0.5

            # Guardar confianza como parte del payload principal y dentro de position_sizing
            request_payload['confidence'] = calculated_confidence
            if position_size_info:
                if request_payload.get('position_sizing') is None:
                    request_payload['position_sizing'] = {}
                if request_payload['position_sizing'].get('confidence') is None:
                    request_payload['position_sizing']['confidence'] = calculated_confidence
            
            # Agregar información de riesgo al response payload
            response_payload = result.copy()
            
            # Guardar información de error detallada en response_payload si el trade fue rechazado
            if not result.get('accepted'):
                if result.get('error_code'):
                    response_payload['error_code'] = result.get('error_code')
                if result.get('error_message'):
                    response_payload['error_message'] = result.get('error_message')
                if result.get('error_data'):
                    response_payload['error_data'] = result.get('error_data')
            
            # IMPORTANTE: Guardar el monto REAL usado en response_payload
            if result.get('accepted'):
                # El monto real está en result['amount'] (después de ajustes)
                response_payload['amount'] = result.get('amount')
            
            if position_size_info:
                response_payload['risk_amount'] = position_size_info.get('risk_amount')
                response_payload['position_sizing_method'] = position_size_info.get('method')
            
            # Obtener el monto real usado (después de todos los ajustes)
            # Orden de prioridad:
            # 1. position_size_info['amount'] (monto REAL usado, pasado desde process_symbol)
            # 2. result['amount'] (monto final usado desde place_binary_option)
            # 3. position_size_info['risk_amount'] (monto calculado antes de ajustes)
            # 4. request_payload['position_sizing'] (fallback)
            from decimal import Decimal
            actual_amount = None
            
            # Prioridad 1: position_size_info['amount'] (el más confiable, viene del caller)
            if position_size_info and position_size_info.get('amount'):
                actual_amount = position_size_info.get('amount')
            
            # Prioridad 2: result['amount'] (monto final usado desde place_binary_option)
            if not actual_amount and result.get('accepted'):
                actual_amount = result.get('amount')
            
            # Prioridad 3: position_size_info['risk_amount'] (monto calculado antes de ajustes)
            if not actual_amount and position_size_info:
                actual_amount = position_size_info.get('risk_amount')
            
            # Prioridad 4: request_payload['position_sizing'] (fallback)
            if not actual_amount:
                if request_payload.get('position_sizing'):
                    actual_amount = request_payload['position_sizing'].get('amount') or request_payload['position_sizing'].get('risk_amount')
            
            # Si aún no tenemos monto y el trade fue aceptado, usar 1.0 como mínimo (fallback)
            if not actual_amount:
                if result.get('accepted'):
                    actual_amount = 1.0
                    print(f"⚠️ WARNING: No se encontró monto para trade {symbol}, usando fallback 1.0")
                else:
                    actual_amount = 0.0
            
            # Convertir a Decimal para guardar en size
            size_value = Decimal(str(actual_amount))
            
            # Debug: verificar que el monto se guarde correctamente
            if result.get('accepted'):
                print(f"💾 Guardando trade {symbol}: monto={size_value}, status={result.get('status', 'pending')}")
            
            # Preparar error_message con información completa
            error_message_final = ''
            if not result.get('accepted'):
                error_message_parts = []
                if result.get('error_code'):
                    error_message_parts.append(f"Código: {result.get('error_code')}")
                if result.get('error_message'):
                    error_message_parts.append(f"Mensaje: {result.get('error_message')}")
                elif result.get('error_data'):
                    error_data = result.get('error_data', {})
                    if isinstance(error_data, dict):
                        if error_data.get('message'):
                            error_message_parts.append(f"Mensaje: {error_data.get('message')}")
                        elif error_data.get('code'):
                            error_message_parts.append(f"Código: {error_data.get('code')}")
                if not error_message_parts:
                    error_message_parts.append(str(result))
                
                error_message_final = ' | '.join(error_message_parts)
            
            order = OrderAudit.objects.create(
                timestamp=timezone.now(),
                symbol=symbol,
                action=signal.direction.lower(),  # 'call' o 'put'
                size=size_value,  # Monto REAL usado
                price=signal.entry_price,
                status='pending' if result.get('accepted') else 'rejected',
                request_payload=request_payload,
                response_payload=response_payload,  # Ya incluye error_code y error_data si existen
                accepted=result.get('accepted', False),
                reason=result.get('reason', 'unknown') if not result.get('accepted') else '',
                error_message=error_message_final  # Mensaje completo con código y mensaje
            )
            
            # Guardar risk_amount si está disponible (para uso por risk_protection)
            if position_size_info and hasattr(order, 'risk_amount'):
                try:
                    order.risk_amount = Decimal(str(position_size_info.get('risk_amount', 0)))
                    order.save(update_fields=['risk_amount'])
                except Exception:
                    pass  # Si el campo no existe, ignorar
                    
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


