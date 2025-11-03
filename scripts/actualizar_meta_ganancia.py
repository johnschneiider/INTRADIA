"""
Script para actualizar la meta de ganancia al 5% del capital
"""
import os
import sys
import django

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from engine.models import CapitalConfig
from decimal import Decimal


def actualizar_meta_ganancia():
    """Actualizar meta de ganancia al 5% del capital"""
    print("=" * 60)
    print("ACTUALIZACIÓN DE META DE GANANCIA".center(60))
    print("=" * 60)
    
    try:
        config = CapitalConfig.get_active()
        
        print(f"\n📊 Configuración actual:")
        print(f"   Meta de ganancia: {config.profit_target_pct}%")
        print(f"   Meta en USD: ${config.profit_target}")
        print(f"   Desactivada: {config.disable_profit_target}")
        
        # Actualizar a 5%
        config.profit_target_pct = 5.0
        config.disable_profit_target = False  # Asegurar que esté activada
        
        # El profit_target se calculará dinámicamente basado en el porcentaje
        # pero mantenemos un valor por defecto razonable
        if config.profit_target <= Decimal('10.00'):
            # Si el valor actual es muy bajo, establecer un valor base
            config.profit_target = Decimal('50.00')  # Valor base, se calculará por porcentaje
        
        config.save()
        
        print(f"\n✅ Configuración actualizada:")
        print(f"   Meta de ganancia: {config.profit_target_pct}% del capital")
        print(f"   Meta en USD: ${config.profit_target} (se calculará dinámicamente)")
        print(f"   Desactivada: {config.disable_profit_target}")
        
        print(f"\n💡 Nota: La meta de ganancia ahora es del 5% del capital inicial.")
        print(f"   El sistema calculará automáticamente la meta basada en el balance.")
        
        print("\n" + "=" * 60)
        return True
        
    except Exception as e:
        print(f"❌ Error al actualizar configuración: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    actualizar_meta_ganancia()

