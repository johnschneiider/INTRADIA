"""
Script para analizar estadísticas de trades y calcular martingala óptima
"""
import os
import sys
import django

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from monitoring.models import OrderAudit
from django.db.models import Q
from collections import Counter

def analizar_estadisticas():
    """Analizar estadísticas de trades completados"""
    trades = OrderAudit.objects.filter(status__in=['won', 'lost']).order_by('timestamp')
    
    total = trades.count()
    won = trades.filter(status='won').count()
    lost = trades.filter(status='lost').count()
    
    if total == 0:
        print("❌ No hay trades completados para analizar")
        return
    
    win_rate = (won / total) * 100
    
    print("=" * 60)
    print("📊 ESTADÍSTICAS DE TRADES")
    print("=" * 60)
    print(f"Total trades completados: {total}")
    print(f"Ganados: {won} ({win_rate:.1f}%)")
    print(f"Perdidos: {lost} ({lost/total*100:.1f}%)")
    print()
    
    # Calcular rachas perdedoras
    losing_streaks = []
    current_streak = 0
    
    for trade in trades:
        if trade.status == 'lost':
            current_streak += 1
        else:
            if current_streak > 0:
                losing_streaks.append(current_streak)
                current_streak = 0
    
    # Agregar última racha si terminó en pérdida
    if current_streak > 0:
        losing_streaks.append(current_streak)
    
    if losing_streaks:
        streak_counter = Counter(losing_streaks)
        max_streak = max(losing_streaks)
        avg_streak = sum(losing_streaks) / len(losing_streaks)
        
        print("=" * 60)
        print("📉 RACHAS PERDEDORAS")
        print("=" * 60)
        print(f"Racha máxima: {max_streak}")
        print(f"Racha promedio: {avg_streak:.2f}")
        print(f"Total de rachas: {len(losing_streaks)}")
        print()
        print("Distribución:")
        for streak_len in sorted(streak_counter.keys()):
            count = streak_counter[streak_len]
            print(f"  {streak_len} pérdidas consecutivas: {count} veces ({count/len(losing_streaks)*100:.1f}%)")
    else:
        print("✅ No se encontraron rachas perdedoras")
        max_streak = 0
    
    print()
    print("=" * 60)
    print("💰 ANÁLISIS DE MARTINGALA")
    print("=" * 60)
    
    # Calcular martingala óptima
    if max_streak > 0:
        # Diferentes multiplicadores de martingala
        multipliers = [2.0, 2.5, 3.0]
        
        print("\n📊 Cálculo de capital necesario para diferentes estrategias:")
        print()
        
        base_amount = 0.10  # Monto base
        
        for multiplier in multipliers:
            print(f"\n🔹 Multiplicador: {multiplier}x")
            print(f"   Monto base: ${base_amount:.2f}")
            
            total_required = 0
            amounts = []
            current_amount = base_amount
            
            for i in range(max_streak):
                amounts.append(current_amount)
                total_required += current_amount
                current_amount *= multiplier
            
            print(f"   Capital necesario para {max_streak} pérdidas: ${total_required:.2f}")
            print(f"   Desglose:")
            for i, amount in enumerate(amounts, 1):
                print(f"     Nivel {i}: ${amount:.2f}")
            
            # Calcular probabilidad teórica
            if win_rate > 0:
                prob_losing = (100 - win_rate) / 100
                prob_n_losses = prob_losing ** max_streak
                print(f"   Probabilidad de {max_streak} pérdidas seguidas: {prob_n_losses*100:.4f}%")
    
    print()
    print("=" * 60)
    print("💡 RECOMENDACIONES")
    print("=" * 60)
    
    if max_streak <= 5:
        print("✅ La racha máxima es ≤ 5, lo cual es manejable con martingala")
        print("✅ Recomendación: Usar multiplicador 2.0x o 2.5x")
        print("✅ Profundidad máxima sugerida: 5-6 niveles")
    else:
        print("⚠️ La racha máxima es > 5, requiere cuidado con martingala")
        print("⚠️ Recomendación: Usar multiplicador menor (2.0x) y profundidad limitada")
    
    print()
    print(f"📊 Con win rate de {win_rate:.1f}%, la probabilidad de:")
    prob_losing = (100 - win_rate) / 100
    for n in [3, 4, 5, 6]:
        prob = prob_losing ** n
        print(f"  - {n} pérdidas seguidas: {prob*100:.2f}%")

if __name__ == "__main__":
    analizar_estadisticas()

