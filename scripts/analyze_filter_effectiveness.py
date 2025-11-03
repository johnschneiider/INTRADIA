"""
Script para analizar la efectividad de filtros e indicadores
Compara win rate con y sin diferentes condiciones
"""
import os
import sys
import django
from collections import defaultdict
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from monitoring.models import OrderAudit
from datetime import timedelta
from django.utils import timezone
from statistics import mean

print("=" * 80)
print("📊 ANÁLISIS DE EFECTIVIDAD DE FILTROS E INDICADORES")
print("=" * 80)

# Analizar últimos 7 días
since = timezone.now() - timedelta(days=7)
orders = OrderAudit.objects.filter(
    timestamp__gte=since,
    accepted=True
).order_by('-timestamp')

print(f"\n📋 TOTAL DE ÓRDENES ANALIZADAS: {orders.count()} (últimos 7 días)")

if orders.count() < 20:
    print("⚠️ No hay suficientes órdenes para análisis estadístico significativo")
    print("💡 Se necesitan al menos 20 órdenes para un análisis confiable")
    exit()

# Analizar trades ganadores vs perdedores
total_trades = orders.filter(status__in=['won', 'lost']).count()
won_trades = orders.filter(status='won').count()
lost_trades = orders.filter(status='lost').count()

if total_trades == 0:
    print("⚠️ No hay trades finalizados (won/lost) para analizar")
    exit()

win_rate_overall = (won_trades / total_trades * 100) if total_trades > 0 else 0
avg_pnl = mean([float(o.pnl) for o in orders.filter(status__in=['won', 'lost']) if o.pnl is not None]) if orders.filter(status__in=['won', 'lost'], pnl__isnull=False).exists() else 0

print(f"\n📈 ESTADÍSTICAS GENERALES:")
print(f"   • Total trades finalizados: {total_trades}")
print(f"   • Ganadores: {won_trades} ({won_trades/total_trades*100:.1f}%)")
print(f"   • Perdedores: {lost_trades} ({lost_trades/total_trades*100:.1f}%)")
print(f"   • Win Rate Global: {win_rate_overall:.1f}%")
print(f"   • P&L Promedio: ${avg_pnl:.2f}")

# Analizar por símbolo
symbol_stats = defaultdict(lambda: {'won': 0, 'lost': 0, 'total': 0})
for order in orders.filter(status__in=['won', 'lost']):
    symbol_stats[order.symbol]['total'] += 1
    if order.status == 'won':
        symbol_stats[order.symbol]['won'] += 1
    else:
        symbol_stats[order.symbol]['lost'] += 1

print(f"\n📊 WIN RATE POR SÍMBOLO:")
for symbol in sorted(symbol_stats.keys(), key=lambda x: symbol_stats[x]['total'], reverse=True)[:10]:
    stats = symbol_stats[symbol]
    if stats['total'] >= 3:  # Solo mostrar si hay al menos 3 trades
        wr = (stats['won'] / stats['total'] * 100) if stats['total'] > 0 else 0
        print(f"   • {symbol}: {wr:.1f}% ({stats['won']}/{stats['total']})")

# Analizar por tipo de señal (si está disponible)
signal_type_stats = defaultdict(lambda: {'won': 0, 'lost': 0, 'total': 0})
for order in orders.filter(status__in=['won', 'lost']):
    # Intentar extraer tipo de señal del request_payload
    if order.request_payload:
        signal_type = order.request_payload.get('signal_type', 'unknown')
        signal_type_stats[signal_type]['total'] += 1
        if order.status == 'won':
            signal_type_stats[signal_type]['won'] += 1
        else:
            signal_type_stats[signal_type]['lost'] += 1

if signal_type_stats:
    print(f"\n📊 WIN RATE POR TIPO DE SEÑAL:")
    for sig_type in sorted(signal_type_stats.keys(), key=lambda x: signal_type_stats[x]['total'], reverse=True):
        stats = signal_type_stats[sig_type]
        if stats['total'] >= 3:
            wr = (stats['won'] / stats['total'] * 100) if stats['total'] > 0 else 0
            print(f"   • {sig_type}: {wr:.1f}% ({stats['won']}/{stats['total']})")

# Analizar por dirección (CALL vs PUT)
direction_stats = defaultdict(lambda: {'won': 0, 'lost': 0, 'total': 0})
for order in orders.filter(status__in=['won', 'lost']):
    direction = order.action.upper() if hasattr(order, 'action') else 'UNKNOWN'
    direction_stats[direction]['total'] += 1
    if order.status == 'won':
        direction_stats[direction]['won'] += 1
    else:
        direction_stats[direction]['lost'] += 1

print(f"\n📊 WIN RATE POR DIRECCIÓN:")
for direction in sorted(direction_stats.keys(), key=lambda x: direction_stats[x]['total'], reverse=True):
    stats = direction_stats[direction]
    if stats['total'] >= 3:
        wr = (stats['won'] / stats['total'] * 100) if stats['total'] > 0 else 0
        print(f"   • {direction}: {wr:.1f}% ({stats['won']}/{stats['total']})")

# Analizar si hay información de confianza en los trades
confidence_ranges = {
    'Alta (>0.7)': {'won': 0, 'lost': 0, 'total': 0},
    'Media (0.4-0.7)': {'won': 0, 'lost': 0, 'total': 0},
    'Baja (<0.4)': {'won': 0, 'lost': 0, 'total': 0},
}

for order in orders.filter(status__in=['won', 'lost']):
    if order.request_payload:
        confidence = order.request_payload.get('confidence', 0)
        if confidence > 0.7:
            cat = 'Alta (>0.7)'
        elif confidence > 0.4:
            cat = 'Media (0.4-0.7)'
        else:
            cat = 'Baja (<0.4)'
        
        confidence_ranges[cat]['total'] += 1
        if order.status == 'won':
            confidence_ranges[cat]['won'] += 1
        else:
            confidence_ranges[cat]['lost'] += 1

if any(stats['total'] > 0 for stats in confidence_ranges.values()):
    print(f"\n📊 WIN RATE POR NIVEL DE CONFIANZA:")
    for cat, stats in sorted(confidence_ranges.items(), key=lambda x: x[1]['total'], reverse=True):
        if stats['total'] >= 3:
            wr = (stats['won'] / stats['total'] * 100) if stats['total'] > 0 else 0
            print(f"   • {cat}: {wr:.1f}% ({stats['won']}/{stats['total']})")

# Analizar tendencia principal (si está disponible)
trend_stats = defaultdict(lambda: {'won': 0, 'lost': 0, 'total': 0})
for order in orders.filter(status__in=['won', 'lost']):
    if order.request_payload:
        main_trend = order.request_payload.get('main_trend', 'unknown')
        direction = order.action.upper() if hasattr(order, 'action') else 'UNKNOWN'
        
        # Verificar si operó a favor o contra la tendencia
        if main_trend and main_trend != 'unknown':
            aligned = (main_trend == direction)
            trend_key = f"{main_trend}_ALINEADO" if aligned else f"{main_trend}_CONTRA"
            trend_stats[trend_key]['total'] += 1
            if order.status == 'won':
                trend_stats[trend_key]['won'] += 1
            else:
                trend_stats[trend_key]['lost'] += 1

if trend_stats:
    print(f"\n📊 WIN RATE: OPERAR A FAVOR vs CONTRA TENDENCIA:")
    for trend_key in sorted(trend_stats.keys(), key=lambda x: trend_stats[x]['total'], reverse=True):
        stats = trend_stats[trend_key]
        if stats['total'] >= 2:
            wr = (stats['won'] / stats['total'] * 100) if stats['total'] > 0 else 0
            print(f"   • {trend_key}: {wr:.1f}% ({stats['won']}/{stats['total']})")

# Análisis de rachas
print(f"\n📊 ANÁLISIS DE RACHAS:")
consecutive_wins = 0
consecutive_losses = 0
max_win_streak = 0
max_loss_streak = 0
current_win_streak = 0
current_loss_streak = 0

for order in orders.filter(status__in=['won', 'lost']).order_by('timestamp'):
    if order.status == 'won':
        current_win_streak += 1
        current_loss_streak = 0
        max_win_streak = max(max_win_streak, current_win_streak)
    elif order.status == 'lost':
        current_loss_streak += 1
        current_win_streak = 0
        max_loss_streak = max(max_loss_streak, current_loss_streak)

print(f"   • Racha máxima de ganancias: {max_win_streak}")
print(f"   • Racha máxima de pérdidas: {max_loss_streak}")

# Análisis de P&L acumulado
print(f"\n💰 ANÁLISIS DE P&L:")
pnl_list = [float(o.pnl) for o in orders.filter(status__in=['won', 'lost']) if o.pnl is not None]
if pnl_list:
    positive_pnl = [p for p in pnl_list if p > 0]
    negative_pnl = [p for p in pnl_list if p < 0]
    
    print(f"   • P&L Total: ${sum(pnl_list):.2f}")
    print(f"   • Ganancia promedio: ${mean(positive_pnl):.2f}" if positive_pnl else "   • Ganancia promedio: N/A")
    print(f"   • Pérdida promedio: ${mean(negative_pnl):.2f}" if negative_pnl else "   • Pérdida promedio: N/A")
    
    if positive_pnl and negative_pnl:
        risk_reward = abs(mean(positive_pnl) / mean(negative_pnl)) if mean(negative_pnl) != 0 else 0
        print(f"   • Risk/Reward Ratio: {risk_reward:.2f}:1")

# Recomendaciones
print(f"\n" + "=" * 80)
print("💡 RECOMENDACIONES:")
print("=" * 80)

if win_rate_overall < 50:
    print("⚠️ Win Rate bajo (<50%). Posibles causas:")
    print("   • Filtros demasiado estrictos")
    print("   • Estrategia no adecuada para el mercado actual")
    print("   • Necesidad de ajustar parámetros")
elif win_rate_overall >= 60:
    print("✅ Win Rate excelente (>=60%). Los filtros están funcionando bien.")
else:
    print("📊 Win Rate moderado (50-60%). Los filtros ayudan pero pueden optimizarse.")

if trend_stats:
    aligned_wr = None
    contra_wr = None
    for trend_key, stats in trend_stats.items():
        if 'ALINEADO' in trend_key and stats['total'] >= 2:
            aligned_wr = (stats['won'] / stats['total'] * 100)
        elif 'CONTRA' in trend_key and stats['total'] >= 2:
            contra_wr = (stats['won'] / stats['total'] * 100)
    
    if aligned_wr and contra_wr:
        if aligned_wr > contra_wr + 10:
            print(f"✅ El filtro de TENDENCIA PRINCIPAL es EFECTIVO:")
            print(f"   • A favor: {aligned_wr:.1f}% vs Contra: {contra_wr:.1f}%")
            print(f"   • Diferencia: +{aligned_wr - contra_wr:.1f}%")
        elif contra_wr > aligned_wr:
            print(f"⚠️ ADVERTENCIA: Operar contra la tendencia tiene mejor win rate!")
            print(f"   • Esto puede ser temporal - revisar datos con más trades")

if confidence_ranges:
    high_conf_wr = confidence_ranges['Alta (>0.7)']['won'] / confidence_ranges['Alta (>0.7)']['total'] * 100 if confidence_ranges['Alta (>0.7)']['total'] > 0 else 0
    low_conf_wr = confidence_ranges['Baja (<0.4)']['won'] / confidence_ranges['Baja (<0.4)']['total'] * 100 if confidence_ranges['Baja (<0.4)']['total'] > 0 else 0
    
    if high_conf_wr > low_conf_wr + 5:
        print(f"✅ El filtro de CONFIANZA funciona:")
        print(f"   • Alta confianza: {high_conf_wr:.1f}% vs Baja: {low_conf_wr:.1f}%")

print("\n" + "=" * 80)

