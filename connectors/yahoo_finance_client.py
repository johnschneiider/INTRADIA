#!/usr/bin/env python3
"""
Cliente para obtener datos históricos de Yahoo Finance
Fuente alternativa para backtesting cuando Deriv no proporciona datos históricos
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)

class YahooFinanceClient:
    """Cliente para obtener datos históricos de Yahoo Finance"""
    
    def __init__(self):
        self.rate_limit_per_sec = 2  # Yahoo Finance tiene límites
        self.last_call_ts = 0.0
        
    def _ratelimit(self):
        """Rate limiting para evitar bloqueos"""
        now = time.time()
        min_interval = 1.0 / self.rate_limit_per_sec
        if now - self.last_call_ts < min_interval:
            time.sleep(min_interval - (now - self.last_call_ts))
        self.last_call_ts = time.time()
    
    def _convert_timeframe(self, timeframe: str) -> str:
        """Convierte timeframe interno a formato de Yahoo Finance"""
        timeframe_map = {
            '1m': '1m',
            '5m': '5m', 
            '15m': '15m',
            '1h': '1h',
            '4h': '4h',
            '1d': '1d',
            '1w': '1wk',
            '1M': '1mo'
        }
        return timeframe_map.get(timeframe, '1h')
    
    def _convert_symbol(self, symbol: str) -> str:
        """Convierte símbolo de Deriv a símbolo de Yahoo Finance"""
        # Mapeo de símbolos de Deriv a Yahoo Finance
        symbol_map = {
            'R_10': '^TNX',      # 10-Year Treasury
            'R_25': '^TNX',      # Usar mismo para R_25
            'R_50': '^TNX',      # Usar mismo para R_50
            'R_75': '^TNX',      # Usar mismo para R_75
            'R_100': '^TNX',     # Usar mismo para R_100
            'CRASH1000': '^VIX', # Volatility Index
            'BOOM1000': '^VIX',  # Usar VIX para BOOM también
            'CRASH500': '^VIX',  # Usar VIX
            'BOOM500': '^VIX',   # Usar VIX
            # Para forex usar símbolos reales
            'EURUSD': 'EURUSD=X',
            'GBPUSD': 'GBPUSD=X', 
            'USDJPY': 'USDJPY=X',
            'AUDUSD': 'AUDUSD=X',
            'USDCAD': 'USDCAD=X',
            'USDCHF': 'USDCHF=X',
            'NZDUSD': 'NZDUSD=X',
            'EURGBP': 'EURGBP=X',
            # Commodities
            'GOLD': 'GC=F',
            'SILVER': 'SI=F',
            'OIL': 'CL=F',
            'COPPER': 'HG=F',
            # Índices
            'US500': '^GSPC',
            'UK100': '^FTSE',
            'DE30': '^GDAXI',
            'FR40': '^FCHI',
            'AU200': '^AXJO',
            'JP225': '^N225',
            'ES35': '^IBEX',
            'IT40': '^FTMIB'
        }
        
        return symbol_map.get(symbol, symbol)
    
    def get_candles(self, symbol: str, timeframe: str, count: int = 200) -> List[Dict[str, Any]]:
        """Obtener velas históricas (alias para get_historical_data)"""
        # Calcular periodo basado en count
        if timeframe in ['1m', '5m', '15m']:
            period = "7d"  # 7 días para timeframes cortos
        elif timeframe == '1h':
            period = "3mo"  # 3 meses para 1h
        elif timeframe == '1d':
            period = "1y"  # 1 año para diario
        
        return self.get_historical_data(symbol, timeframe, period)
    
    def get_historical_data(self, symbol: str, timeframe: str, period: str = "1mo") -> List[Dict[str, Any]]:
        """
        Obtener datos históricos de Yahoo Finance
        
        Args:
            symbol: Símbolo del activo
            timeframe: Timeframe (1m, 5m, 15m, 1h, 1d, etc.)
            period: Período de datos (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
        
        Returns:
            Lista de diccionarios con datos OHLCV
        """
        self._ratelimit()
        
        try:
            # Convertir símbolo y timeframe
            yahoo_symbol = self._convert_symbol(symbol)
            yahoo_timeframe = self._convert_timeframe(timeframe)
            
            logger.info(f"📊 Obteniendo datos de Yahoo Finance: {yahoo_symbol} {yahoo_timeframe}")
            
            # Crear objeto ticker
            ticker = yf.Ticker(yahoo_symbol)
            
            # Obtener datos históricos
            if timeframe in ['1m', '5m', '15m']:
                # Para timeframes menores a 1 día, usar máximo 7 días
                period = "7d"
            
            data = ticker.history(period=period, interval=yahoo_timeframe)
            
            if data.empty:
                logger.warning(f"⚠️ No hay datos disponibles para {yahoo_symbol}")
                return []
            
            # Convertir a formato estándar
            candles = []
            for timestamp, row in data.iterrows():
                # Convertir timestamp a formato correcto (manejar timezone)
                if hasattr(timestamp, 'timestamp'):
                    # Convertir a UTC si tiene timezone
                    if timestamp.tzinfo is not None:
                        ts = int(timestamp.tz_convert('UTC').timestamp())
                    else:
                        ts = int(timestamp.timestamp())
                else:
                    # Si es string, convertir primero
                    ts = int(pd.to_datetime(timestamp).timestamp())
                
                candle = {
                    'timestamp': ts,
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': float(row['Volume']) if 'Volume' in row else 0.0
                }
                candles.append(candle)
            
            logger.info(f"✅ Obtenidos {len(candles)} velas de Yahoo Finance para {symbol}")
            return candles
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo datos de Yahoo Finance para {symbol}: {e}")
            return []
    
    def get_multiple_symbols(self, symbols: List[str], timeframe: str = "1h", period: str = "1mo") -> Dict[str, List[Dict[str, Any]]]:
        """
        Obtener datos históricos para múltiples símbolos
        
        Args:
            symbols: Lista de símbolos
            timeframe: Timeframe
            period: Período de datos
        
        Returns:
            Diccionario con símbolo como clave y datos como valor
        """
        results = {}
        
        for symbol in symbols:
            logger.info(f"📊 Procesando {symbol}...")
            data = self.get_historical_data(symbol, timeframe, period)
            results[symbol] = data
            
            # Rate limiting entre símbolos
            time.sleep(1)
        
        return results
    
    def test_connection(self) -> bool:
        """Probar conexión con Yahoo Finance"""
        try:
            logger.info("🔍 Probando conexión con Yahoo Finance...")
            
            # Probar con un símbolo simple
            ticker = yf.Ticker("AAPL")
            data = ticker.history(period="5d")
            
            if not data.empty:
                logger.info("✅ Conexión con Yahoo Finance exitosa")
                return True
            else:
                logger.warning("⚠️ Conexión con Yahoo Finance falló - sin datos")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error probando conexión con Yahoo Finance: {e}")
            return False

# Función de utilidad para usar en el sistema
def get_historical_data_for_backtesting(symbol: str, timeframe: str, period: str = "3mo") -> List[Dict[str, Any]]:
    """
    Función de utilidad para obtener datos históricos para backtesting
    
    Args:
        symbol: Símbolo del activo
        timeframe: Timeframe
        period: Período de datos
    
    Returns:
        Lista de velas históricas
    """
    client = YahooFinanceClient()
    return client.get_historical_data(symbol, timeframe, period)

if __name__ == "__main__":
    # Prueba del cliente
    client = YahooFinanceClient()
    
    print("🧪 PROBANDO YAHOO FINANCE CLIENT")
    print("=" * 50)
    
    # Probar conexión
    if client.test_connection():
        print("✅ Conexión exitosa")
        
        # Probar datos históricos
        symbols_to_test = ['EURUSD', 'GBPUSD', 'USDJPY', 'R_10', 'CRASH1000']
        
        for symbol in symbols_to_test:
            print(f"\n📊 Probando {symbol}...")
            data = client.get_historical_data(symbol, '1h', '1mo')
            
            if data:
                print(f"✅ {symbol}: {len(data)} velas obtenidas")
                print(f"   Primera vela: {data[0]}")
                print(f"   Última vela: {data[-1]}")
            else:
                print(f"❌ {symbol}: Sin datos")
            
            time.sleep(2)
    else:
        print("❌ No se pudo conectar a Yahoo Finance")
