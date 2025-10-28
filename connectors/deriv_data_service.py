from __future__ import annotations

import requests
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any
from django.utils import timezone

from market.models import Candle, Timeframe


class DerivDataService:
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.base_url = "https://api.deriv.com"
        self.headers = {"Authorization": api_token}
    
    def get_historical_candles(self, symbol: str, timeframe: str, count: int = 100) -> List[Dict[str, Any]]:
        """
        Obtiene velas históricas de Deriv API
        """
        try:
            # Mapear timeframes a formato Deriv
            tf_map = {
                '1m': '1min',
                '5m': '5min', 
                '15m': '15min',
                '1h': '1hour',
                '1d': '1day',
                '1w': '1week'
            }
            
            deriv_tf = tf_map.get(timeframe, timeframe)
            
            # Endpoint de Deriv para datos históricos
            url = f"{self.base_url}/v1/ticks_history"
            params = {
                'symbol': symbol,
                'granularity': deriv_tf,
                'count': count,
                'end': int(timezone.now().timestamp())
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return self._parse_candles(data.get('history', {}).get('ticks', []))
            else:
                print(f"Error Deriv API: {response.status_code} - {response.text}")
                return []
                
        except Exception as e:
            print(f"Error obteniendo datos históricos: {e}")
            return []
    
    def _parse_candles(self, ticks: List[Dict]) -> List[Dict[str, Any]]:
        """Convierte ticks de Deriv a formato OHLCV"""
        candles = []
        for tick in ticks:
            candles.append({
                'timestamp': datetime.fromtimestamp(tick['epoch']),
                'open': Decimal(str(tick['quote'])),
                'high': Decimal(str(tick['quote'])),
                'low': Decimal(str(tick['quote'])),
                'close': Decimal(str(tick['quote'])),
                'volume': Decimal('1000')  # Deriv no siempre da volumen
            })
        return candles
    
    def store_candles(self, symbol: str, timeframe: str, candles: List[Dict[str, Any]]):
        """Almacena velas en la base de datos"""
        tf_enum = getattr(Timeframe, timeframe.upper().replace('M', 'M').replace('H', 'H').replace('D', 'D').replace('W', 'W'), None)
        if not tf_enum:
            print(f"Timeframe {timeframe} no válido")
            return
        
        stored_count = 0
        for candle_data in candles:
            candle, created = Candle.objects.get_or_create(
                symbol=symbol,
                timeframe=tf_enum,
                timestamp=candle_data['timestamp'],
                defaults={
                    'open': candle_data['open'],
                    'high': candle_data['high'],
                    'low': candle_data['low'],
                    'close': candle_data['close'],
                    'volume': candle_data['volume']
                }
            )
            if created:
                stored_count += 1
        
        print(f"✅ Almacenadas {stored_count} velas nuevas para {symbol} {timeframe}")
        return stored_count
