"""
Análisis de Horarios de Mejor Desempeño
Analiza la base de datos para identificar los horarios con mejor rendimiento
"""

from __future__ import annotations
from typing import Dict, List, Tuple
from decimal import Decimal
from django.utils import timezone
from django.db.models import Count, Avg, Sum, Q
from monitoring.models import OrderAudit
from collections import defaultdict


class TimeAnalysis:
    """Analiza el desempeño por horarios"""
    
    def __init__(self, lookback_days: int = 30):
        """
        Args:
            lookback_days: Días hacia atrás para analizar (default: 30)
        """
        self.lookback_days = lookback_days
    
    def analyze_hourly_performance(self) -> Dict[int, Dict[str, float]]:
        """
        Analizar desempeño por hora del día (0-23)
        
        Returns:
            Dict con métricas por hora: {
                9: {'win_rate': 0.65, 'total_pnl': 15.50, 'trades_count': 20},
                10: {'win_rate': 0.55, 'total_pnl': 5.20, 'trades_count': 15},
                ...
            }
        """
        try:
            from datetime import timedelta
            
            since = timezone.now() - timedelta(days=self.lookback_days)
            
            # Obtener todos los trades finalizados en el período
            trades = OrderAudit.objects.filter(
                timestamp__gte=since,
                accepted=True,
                status__in=['won', 'lost']
            )
            
            # Agrupar por hora
            hourly_stats = defaultdict(lambda: {'won': 0, 'lost': 0, 'pnl': Decimal('0.00'), 'trades': []})
            
            for trade in trades:
                hour = trade.timestamp.hour
                hourly_stats[hour]['trades'].append(trade)
                
                if trade.status == 'won':
                    hourly_stats[hour]['won'] += 1
                elif trade.status == 'lost':
                    hourly_stats[hour]['lost'] += 1
                
                if trade.pnl:
                    hourly_stats[hour]['pnl'] += Decimal(str(trade.pnl))
            
            # Calcular métricas finales
            result = {}
            for hour, stats in hourly_stats.items():
                total = stats['won'] + stats['lost']
                if total == 0:
                    continue
                
                win_rate = stats['won'] / total
                total_pnl = float(stats['pnl'])
                avg_pnl = total_pnl / total if total > 0 else 0.0
                
                # Score combinado
                win_rate_score = win_rate
                normalized_pnl = max(0, min(1, (avg_pnl + 2) / 4))
                consistency_score = min(1.0, total / 10)
                score = (win_rate_score * 0.4) + (normalized_pnl * 0.4) + (consistency_score * 0.2)
                
                result[hour] = {
                    'win_rate': win_rate,
                    'total_pnl': total_pnl,
                    'avg_pnl': avg_pnl,
                    'trades_count': total,
                    'score': score
                }
            
            return result
            
        except Exception as e:
            print(f"Error analizando desempeño por horarios: {e}")
            return {}
    
    def get_best_hours(self, top_n: int = 5) -> List[Tuple[int, float]]:
        """
        Obtener las mejores horas del día
        
        Returns:
            Lista de tuplas (hora, score) ordenadas por score descendente
        """
        hourly_perf = self.analyze_hourly_performance()
        sorted_hours = sorted(hourly_perf.items(), key=lambda x: x[1]['score'], reverse=True)
        return [(hour, perf['score']) for hour, perf in sorted_hours[:top_n]]
    
    def is_current_hour_optimal(self) -> bool:
        """
        Verificar si la hora actual es una de las mejores
        
        Returns:
            True si la hora actual está en el top 5
        """
        best_hours = self.get_best_hours(top_n=5)
        current_hour = timezone.now().hour
        best_hour_numbers = [h[0] for h in best_hours]
        return current_hour in best_hour_numbers

