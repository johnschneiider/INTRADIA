#!/usr/bin/env python
"""
Script para crear datos de prueba para el dashboard
Simula operaciones ganadas, perdidas y activas
"""
import os
import django
from datetime import datetime, timedelta
from decimal import Decimal
import random

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from monitoring.models import OrderAudit


def create_sample_trades():
    """Crear operaciones de ejemplo para el dashboard"""
    print("🎯 Creando operaciones de ejemplo...")
    
    symbols = ['EURUSD', 'GBPUSD', 'USDJPY']
    actions = ['buy', 'sell']
    statuses = ['won', 'lost', 'active', 'pending']
    
    # Limpiar datos existentes
    OrderAudit.objects.all().delete()
    
    # Crear operaciones de ejemplo
    for i in range(50):
        symbol = random.choice(symbols)
        action = random.choice(actions)
        status = random.choice(statuses)
        
        # Precios base según símbolo
        if 'EUR' in symbol:
            base_price = 1.0500
        elif 'GBP' in symbol:
            base_price = 1.2500
        else:
            base_price = 110.0
        
        # Generar precios realistas
        entry_price = base_price * random.uniform(0.98, 1.02)
        stop_loss = entry_price * random.uniform(0.995, 0.999) if action == 'buy' else entry_price * random.uniform(1.001, 1.005)
        take_profit = entry_price * random.uniform(1.002, 1.008) if action == 'buy' else entry_price * random.uniform(0.992, 0.998)
        
        # P&L según estado
        if status == 'won':
            pnl = random.uniform(10, 100)
            exit_price = take_profit
        elif status == 'lost':
            pnl = random.uniform(-100, -10)
            exit_price = stop_loss
        else:
            pnl = 0
            exit_price = None
        
        # Timestamp aleatorio en los últimos 30 días
        timestamp = datetime.now() - timedelta(days=random.randint(0, 30), hours=random.randint(0, 23))
        
        OrderAudit.objects.create(
            symbol=symbol,
            action=action,
            size=random.uniform(0.1, 1.0),
            price=Decimal(str(round(entry_price, 4))),
            stop_loss=Decimal(str(round(stop_loss, 4))),
            take_profit=Decimal(str(round(take_profit, 4))),
            exit_price=Decimal(str(round(exit_price, 4))) if exit_price else None,
            pnl=Decimal(str(round(pnl, 2))),
            status=status,
            timestamp=timestamp,
            latency_ms=random.uniform(50, 300),
            request_hash=f"hash_{i}",
            response_hash=f"response_{i}",
            accepted=True,
        )
    
    print("✅ Operaciones de ejemplo creadas:")
    
    # Mostrar estadísticas
    total = OrderAudit.objects.count()
    won = OrderAudit.objects.filter(status='won').count()
    lost = OrderAudit.objects.filter(status='lost').count()
    active = OrderAudit.objects.filter(status='active').count()
    pending = OrderAudit.objects.filter(status='pending').count()
    
    total_pnl = sum(float(order.pnl or 0) for order in OrderAudit.objects.all())
    win_rate = (won / (won + lost)) * 100 if (won + lost) > 0 else 0
    
    print(f"📊 Total operaciones: {total}")
    print(f"✅ Ganadas: {won}")
    print(f"❌ Perdidas: {lost}")
    print(f"🔄 Activas: {active}")
    print(f"⏳ Pendientes: {pending}")
    print(f"💰 P&L Total: ${total_pnl:.2f}")
    print(f"🎯 Tasa de acierto: {win_rate:.1f}%")
    
    print("\n🎉 ¡Dashboard listo para mostrar datos realistas!")


if __name__ == '__main__':
    create_sample_trades()











