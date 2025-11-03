#!/usr/bin/env python3
"""
Script para monitorear el sistema de trading en tiempo real
"""

import os
import sys
import django
import time
import requests
from datetime import datetime

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from connectors.deriv_client import DerivClient
from market.models import Candle, Zone
from monitoring.models import OrderAudit

def get_system_status():
    """Obtener estado del sistema"""
    try:
        # Verificar conexión con Deriv
        client = DerivClient()
        deriv_connected = client.authenticate()
        
        # Obtener métricas del dashboard
        try:
            response = requests.get('http://127.0.0.1:8000/engine/metrics/', timeout=5)
            if response.status_code == 200:
                metrics = response.json()
            else:
                metrics = {'error': 'Dashboard no disponible'}
        except:
            metrics = {'error': 'Dashboard no disponible'}
        
        # Obtener datos de la base de datos
        candles_count = Candle.objects.count()
        zones_count = Zone.objects.count()
        orders_count = OrderAudit.objects.count()
        
        return {
            'deriv_connected': deriv_connected,
            'metrics': metrics,
            'candles_count': candles_count,
            'zones_count': zones_count,
            'orders_count': orders_count,
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }
    except Exception as e:
        return {'error': str(e)}

def display_status(status):
    """Mostrar estado del sistema"""
    print("\n" + "="*60)
    print(f"📊 MONITOR DEL SISTEMA DE TRADING - {status['timestamp']}")
    print("="*60)
    
    if 'error' in status:
        print(f"❌ Error: {status['error']}")
        return
    
    # Estado de Deriv
    deriv_status = "✅ CONECTADO" if status['deriv_connected'] else "❌ DESCONECTADO"
    print(f"🔗 Deriv WebSocket: {deriv_status}")
    
    # Datos disponibles
    print(f"📈 Velas históricas: {status['candles_count']}")
    print(f"🎯 Zonas detectadas: {status['zones_count']}")
    print(f"📋 Órdenes ejecutadas: {status['orders_count']}")
    
    # Métricas del dashboard
    if 'error' in status['metrics']:
        print(f"⚠️ Dashboard: {status['metrics']['error']}")
    else:
        metrics = status['metrics']
        print(f"💰 P&L: ${metrics.get('pnl', 0):.2f}")
        print(f"📊 Win Rate: {metrics.get('winrate', 0)*100:.1f}%")
        print(f"🎯 Trades activos: {metrics.get('active_trades', 0)}")
        print(f"📈 Total trades: {metrics.get('total_trades', 0)}")

def monitor_loop():
    """Loop de monitoreo"""
    print("🚀 INICIANDO MONITOR DEL SISTEMA DE TRADING")
    print("Presiona Ctrl+C para detener")
    
    try:
        while True:
            status = get_system_status()
            display_status(status)
            
            # Esperar 10 segundos
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("\n🛑 Monitor detenido por el usuario")
    except Exception as e:
        print(f"\n❌ Error en el monitor: {e}")

if __name__ == "__main__":
    monitor_loop()








