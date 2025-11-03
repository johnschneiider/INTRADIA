from django.core.management.base import BaseCommand
from datetime import datetime, timedelta
from decimal import Decimal
import random
from monitoring.models import OrderAudit


class Command(BaseCommand):
    help = 'Crear datos de ejemplo para el dashboard'

    def handle(self, *args, **options):
        self.stdout.write("🎯 Creando operaciones de ejemplo...")
        
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
        
        self.stdout.write("✅ Operaciones de ejemplo creadas:")
        
        # Mostrar estadísticas
        total = OrderAudit.objects.count()
        won = OrderAudit.objects.filter(status='won').count()
        lost = OrderAudit.objects.filter(status='lost').count()
        active = OrderAudit.objects.filter(status='active').count()
        pending = OrderAudit.objects.filter(status='pending').count()
        
        total_pnl = sum(float(order.pnl or 0) for order in OrderAudit.objects.all())
        win_rate = (won / (won + lost)) * 100 if (won + lost) > 0 else 0
        
        self.stdout.write(f"📊 Total operaciones: {total}")
        self.stdout.write(f"✅ Ganadas: {won}")
        self.stdout.write(f"❌ Perdidas: {lost}")
        self.stdout.write(f"🔄 Activas: {active}")
        self.stdout.write(f"⏳ Pendientes: {pending}")
        self.stdout.write(f"💰 P&L Total: ${total_pnl:.2f}")
        self.stdout.write(f"🎯 Tasa de acierto: {win_rate:.1f}%")
        
        self.stdout.write("\n🎉 ¡Dashboard listo para mostrar datos realistas!")








