#!/usr/bin/env python3
"""
Script simple para probar Yahoo Finance
"""

import yfinance as yf
import pandas as pd
from datetime import datetime

def test_yahoo():
    print("🧪 Probando Yahoo Finance directamente...")
    
    try:
        # Probar con EURUSD
        ticker = yf.Ticker("EURUSD=X")
        data = ticker.history(period="5d", interval="1h")
        
        print(f"✅ Datos obtenidos: {len(data)} filas")
        print(f"📊 Columnas: {list(data.columns)}")
        print(f"📅 Índice: {type(data.index)}")
        print(f"📅 Primera fila índice: {data.index[0]}")
        print(f"📅 Tipo de índice: {type(data.index[0])}")
        
        # Probar conversión de timestamp
        first_timestamp = data.index[0]
        print(f"📅 Timestamp original: {first_timestamp}")
        
        if hasattr(first_timestamp, 'timestamp'):
            ts = int(first_timestamp.timestamp())
            print(f"✅ Timestamp convertido: {ts}")
            print(f"📅 Fecha convertida: {datetime.fromtimestamp(ts)}")
        else:
            print(f"❌ No tiene método timestamp: {type(first_timestamp)}")
            
        # Mostrar una fila de datos
        first_row = data.iloc[0]
        print(f"📊 Primera fila datos:")
        print(f"   Open: {first_row['Open']}")
        print(f"   High: {first_row['High']}")
        print(f"   Low: {first_row['Low']}")
        print(f"   Close: {first_row['Close']}")
        print(f"   Volume: {first_row['Volume']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_yahoo()








