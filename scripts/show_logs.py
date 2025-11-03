#!/usr/bin/env python3
"""
Script para mostrar logs del sistema
"""

import os
import sys
import django
from datetime import datetime, timedelta

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from trading_bot.models import BotLog
from monitoring.models import OrderAudit

def show_bot_logs(limit=50):
    """Mostrar logs de bots"""
    print("\n" + "="*80)
    print("📋 LOGS DE BOTS (ÚLTIMOS {})".format(limit))
    print("="*80)
    
    try:
        logs = BotLog.objects.all().order_by('-created_at')[:limit]
        
        if not logs.exists():
            print("⚠️ No hay logs disponibles")
            return
    except Exception as e:
        print(f"⚠️ Error accediendo a logs de bots: {e}")
        print("💡 Asegúrate de haber ejecutado: python manage.py migrate")
        return
    
    for log in logs:
        level_emoji = {
            'info': 'ℹ️',
            'warning': '⚠️',
            'error': '❌',
            'success': '✅'
        }
        emoji = level_emoji.get(log.level, '📝')
        timestamp = log.created_at.strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n{emoji} [{timestamp}] {log.level.upper()}")
        print(f"   Bot: {log.bot.name if log.bot else 'N/A'}")
        print(f"   Mensaje: {log.message}")
        if log.details:
            print(f"   Detalles: {log.details}")

def show_order_logs(limit=30):
    """Mostrar logs de órdenes"""
    print("\n" + "="*80)
    print("📊 LOGS DE ÓRDENES (ÚLTIMAS {})".format(limit))
    print("="*80)
    
    try:
        orders = OrderAudit.objects.all().order_by('-timestamp')[:limit]
        
        if not orders.exists():
            print("⚠️ No hay órdenes registradas")
            return
    except Exception as e:
        print(f"⚠️ Error accediendo a logs de órdenes: {e}")
        return
    
    for order in orders:
        status_emoji = {
            'pending': '⏳',
            'filled': '✅',
            'rejected': '❌',
            'cancelled': '🚫',
            'won': '✅',
            'lost': '❌'
        }
        emoji = status_emoji.get(order.status, '📝')
        timestamp = order.timestamp.strftime('%Y-%m-%d %H:%M:%S') if order.timestamp else 'N/A'
        print(f"\n{emoji} [{timestamp}] {order.symbol} - {order.action.upper() if hasattr(order, 'action') else 'N/A'}")
        print(f"   Estado: {order.status}")
        if hasattr(order, 'price') and order.price:
            print(f"   Precio: {order.price}")
        if hasattr(order, 'reason') and order.reason:
            print(f"   Razón: {order.reason}")

def show_recent_activity(hours=24):
    """Mostrar actividad reciente de las últimas N horas"""
    print("\n" + "="*80)
    print("🕐 ACTIVIDAD RECIENTE (ÚLTIMAS {} HORAS)".format(hours))
    print("="*80)
    
    cutoff = datetime.now() - timedelta(hours=hours)
    
    try:
        bot_logs_count = BotLog.objects.filter(created_at__gte=cutoff).count()
        bot_logs_available = True
    except Exception:
        bot_logs_count = 0
        bot_logs_available = False
    
    try:
        orders_count = OrderAudit.objects.filter(timestamp__gte=cutoff).count()
    except Exception as e:
        orders_count = 0
        print(f"⚠️ Error obteniendo órdenes: {e}")
        return
    
    print(f"\n📋 Logs de bots: {bot_logs_count}" + (" (tabla no disponible)" if not bot_logs_available else ""))
    print(f"📊 Órdenes: {orders_count}")
    
    if bot_logs_available and bot_logs_count > 0:
        try:
            print("\n🔍 Últimos logs de bots:")
            recent_logs = BotLog.objects.filter(created_at__gte=cutoff).order_by('-created_at')[:10]
            for log in recent_logs:
                print(f"   • [{log.created_at.strftime('%H:%M:%S')}] {log.level}: {log.message[:60]}...")
        except Exception:
            pass

def show_server_info():
    """Mostrar información sobre los servidores"""
    print("\n" + "="*80)
    print("🖥️  INFORMACIÓN DE SERVIDORES")
    print("="*80)
    
    print("\n📍 Logs disponibles:")
    print("   1. Logs de órdenes (OrderAudit) - Base de datos")
    print("   2. Logs de bots (BotLog) - Base de datos (requiere migraciones)")
    print("   3. Logs de consola - Salida directa en terminales")
    
    print("\n💡 Nota:")
    print("   • Los logs de Django/Daphne se muestran en la terminal donde ejecutaste el servidor")
    print("   • Para ver logs en tiempo real, revisa las terminales donde están corriendo los procesos")
    print("   • Los logs de base de datos están disponibles aquí si las migraciones están aplicadas")
    
    print("\n🔄 Procesos Python activos:")
    try:
        import subprocess
        result = subprocess.run(['powershell', '-Command', 
            'Get-Process | Where-Object {$_.ProcessName -eq "python"} | Format-Table ProcessName, Id, StartTime -AutoSize'],
            capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if len(lines) > 3:  # Si hay procesos
                for line in lines[3:]:  # Saltar encabezados
                    if line.strip():
                        print(f"   {line}")
            else:
                print("   ⚠️ No se encontraron procesos Python activos")
        else:
            print("   ⚠️ No se pudo obtener información de procesos")
    except Exception as e:
        print(f"   ⚠️ Error: {e}")

def main():
    """Función principal"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Mostrar logs del sistema')
    parser.add_argument('--bot-logs', type=int, default=50, help='Número de logs de bots a mostrar')
    parser.add_argument('--order-logs', type=int, default=30, help='Número de órdenes a mostrar')
    parser.add_argument('--recent-hours', type=int, default=24, help='Horas para actividad reciente')
    parser.add_argument('--type', choices=['bot', 'order', 'recent', 'all', 'server'], default='all',
                       help='Tipo de logs a mostrar')
    
    args = parser.parse_args()
    
    if args.type == 'server':
        show_server_info()
    else:
        if args.type in ['bot', 'all']:
            show_bot_logs(args.bot_logs)
        
        if args.type in ['order', 'all']:
            show_order_logs(args.order_logs)
        
        if args.type in ['recent', 'all']:
            show_recent_activity(args.recent_hours)
        
        if args.type == 'all':
            show_server_info()
    
    print("\n" + "="*80)
    print("✅ Fin de logs")
    print("="*80 + "\n")

if __name__ == "__main__":
    main()

