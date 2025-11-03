"""
Script para verificar el estado del trading y por qué se detuvo
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from engine.models import CapitalConfig
from monitoring.models import OrderAudit
from django.utils import timezone
from datetime import datetime
from decimal import Decimal

print("=" * 80)
print("🔍 ESTADO ACTUAL DEL TRADING")
print("=" * 80)

config = CapitalConfig.get_active()

print(f"\n📋 CONFIGURACIÓN DE CONTROLES RÁPIDOS:")
print(f"   • Desactivar límite de trades: {config.disable_max_trades}")
print(f"   • Desactivar meta de ganancia: {config.disable_profit_target}")
print(f"   • Stop Loss por monto: ${config.stop_loss_amount:.2f}")

print(f"\n📊 CONFIGURACIÓN BASE:")
print(f"   • Meta de ganancia: ${config.profit_target:.2f}")
print(f"   • Pérdida máxima: ${config.max_loss:.2f}")
print(f"   • Máximo trades: {config.max_trades}")

# Calcular P&L del día
today = timezone.localdate()
start_of_day = timezone.make_aware(datetime(today.year, today.month, today.day, 0, 0, 0))

trades = OrderAudit.objects.filter(
    timestamp__gte=start_of_day,
    status__in=['won', 'lost'],
    pnl__isnull=False
)

total_pnl = sum(t.pnl for t in trades if t.pnl is not None)
trades_count = trades.count()
won_count = trades.filter(status='won').count()
lost_count = trades.filter(status='lost').count()

print(f"\n💰 P&L DEL DÍA ACTUAL:")
print(f"   • P&L acumulado: ${total_pnl:.2f}")
print(f"   • Total trades: {trades_count}")
print(f"   • Ganados: {won_count}")
print(f"   • Perdidos: {lost_count}")

# Calcular límites efectivos
effective_max_trades = 999999 if config.disable_max_trades else config.max_trades
effective_profit_target = Decimal('999999.00') if config.disable_profit_target else config.profit_target
effective_max_loss = -abs(config.stop_loss_amount) if config.stop_loss_amount > 0 else config.max_loss

print(f"\n⚙️ LÍMITES EFECTIVOS (aplicados):")
print(f"   • Máximo trades efectivo: {effective_max_trades}")
print(f"   • Meta de ganancia efectiva: ${effective_profit_target:.2f}")
print(f"   • Pérdida máxima efectiva: ${effective_max_loss:.2f}")

# Verificar condiciones de parada
print(f"\n🚦 VERIFICACIÓN DE CONDICIONES:")
print(f"   • Trades >= Límite: {trades_count >= effective_max_trades} ({trades_count} >= {effective_max_trades})")
print(f"   • P&L >= Meta: {total_pnl >= effective_profit_target} (${total_pnl:.2f} >= ${effective_profit_target:.2f})")
print(f"   • P&L <= Pérdida Máx: {total_pnl <= effective_max_loss} (${total_pnl:.2f} <= ${effective_max_loss:.2f})")

if total_pnl <= effective_max_loss:
    print(f"\n❌ RAZÓN DE DETENCIÓN:")
    if config.stop_loss_amount > 0:
        print(f"   El stop loss por monto de ${config.stop_loss_amount:.2f} fue alcanzado")
        print(f"   P&L actual: ${total_pnl:.2f} <= Stop Loss: ${effective_max_loss:.2f}")
    else:
        print(f"   La pérdida máxima diaria fue alcanzada")
        print(f"   P&L actual: ${total_pnl:.2f} <= Pérdida Máx: ${effective_max_loss:.2f}")
elif total_pnl >= effective_profit_target and not config.disable_profit_target:
    print(f"\n✅ META ALCANZADA:")
    print(f"   P&L actual: ${total_pnl:.2f} >= Meta: ${effective_profit_target:.2f}")
elif trades_count >= effective_max_trades:
    print(f"\n🛑 LÍMITE DE TRADES ALCANZADO:")
    print(f"   Trades: {trades_count} >= Límite: {effective_max_trades}")
else:
    print(f"\n✅ TRADING ACTIVO:")
    print(f"   No se han alcanzado los límites de detención")

print("\n" + "=" * 80)

