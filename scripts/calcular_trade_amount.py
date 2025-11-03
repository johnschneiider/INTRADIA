"""
Script para calcular el monto por trade según la lógica del proyecto
"""
import os
import sys
import django
from decimal import Decimal

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from trading_bot.models import DerivAPIConfig
from engine.models import CapitalConfig
from connectors.deriv_client import DerivClient
from engine.services.advanced_capital_manager import AdvancedCapitalManager


def calcular_monto_trade():
    """Calcular monto por trade según la lógica del proyecto"""
    print("=" * 60)
    print("CÁLCULO DE MONTO POR TRADE".center(60))
    print("=" * 60)
    
    # 1. Obtener balance actual
    print("\n1. Obteniendo balance actual...")
    try:
        config_api = DerivAPIConfig.objects.filter(is_active=True).only('api_token', 'is_demo', 'app_id').first()
        if not config_api:
            print("❌ No hay configuración de API activa")
            return
        
        client = DerivClient(
            api_token=config_api.api_token,
            is_demo=config_api.is_demo,
            app_id=config_api.app_id
        )
        
        if not client.authenticate():
            print("❌ Error al autenticar con Deriv")
            return
        
        balance_info = client.get_balance()
        if isinstance(balance_info, dict):
            current_balance = Decimal(str(balance_info.get('balance', 0)))
        else:
            current_balance = Decimal(str(balance_info)) if balance_info else Decimal('0')
        
        print(f"   ✅ Balance actual: ${current_balance:.2f}")
        print(f"   📊 Cuenta: {balance_info.get('loginid', 'N/A')} ({balance_info.get('account_type', 'unknown').upper()})")
        
    except Exception as e:
        print(f"❌ Error obteniendo balance: {e}")
        return
    
    # 2. Obtener configuración de capital
    print("\n2. Obteniendo configuración de capital...")
    try:
        capital_config = CapitalConfig.get_active()
        position_method = getattr(capital_config, 'position_sizing_method', 'kelly_fractional')
        kelly_fraction = getattr(capital_config, 'kelly_fraction', 0.25)
        risk_per_trade_pct = getattr(capital_config, 'risk_per_trade_pct', 1.0)
        max_risk_per_trade_pct = getattr(capital_config, 'max_risk_per_trade_pct', 2.0)
        min_position_size = getattr(capital_config, 'min_position_size', 1.0)
        max_position_size = getattr(capital_config, 'max_position_size', 1000.0)
        
        print(f"   ✅ Método: {position_method}")
        print(f"   ✅ Kelly Fraction: {kelly_fraction * 100:.0f}%")
        print(f"   ✅ Risk Per Trade: {risk_per_trade_pct}%")
        print(f"   ✅ Max Risk Per Trade: {max_risk_per_trade_pct}%")
        print(f"   ✅ Min Position Size: ${min_position_size:.2f}")
        print(f"   ✅ Max Position Size: ${max_position_size:.2f}")
        
    except Exception as e:
        print(f"❌ Error obteniendo configuración: {e}")
        return
    
    # 3. Inicializar Capital Manager
    print("\n3. Inicializando Capital Manager...")
    try:
        capital_manager = AdvancedCapitalManager(
            position_sizing_method=position_method,
            kelly_fraction=kelly_fraction,
            risk_per_trade_pct=risk_per_trade_pct,
            max_risk_per_trade_pct=max_risk_per_trade_pct,
        )
        print("   ✅ Capital Manager inicializado")
        
    except Exception as e:
        print(f"❌ Error inicializando Capital Manager: {e}")
        return
    
    # 4. Obtener estadísticas de trading (para Kelly)
    print("\n4. Obteniendo estadísticas de trading...")
    try:
        stats = capital_manager.get_trading_statistics(days=30)
        print(f"   ✅ Total trades: {stats['total_trades']}")
        print(f"   ✅ Win Rate: {stats['win_rate'] * 100:.1f}%")
        print(f"   ✅ Avg Win: ${stats['avg_win']:.2f}")
        print(f"   ✅ Avg Loss: ${abs(stats['avg_loss']):.2f}")
        print(f"   ✅ Kelly %: {stats['kelly_percentage'] * 100:.2f}%")
        
    except Exception as e:
        print(f"⚠️  Error obteniendo estadísticas: {e}")
        stats = {
            'total_trades': 0,
            'win_rate': 0.0,
            'avg_win': Decimal('0'),
            'avg_loss': Decimal('0'),
            'kelly_percentage': 0.0
        }
    
    # 5. Calcular monto por trade
    print("\n5. Calculando monto por trade...")
    print("-" * 60)
    
    # Calcular según el método configurado
    if position_method == 'kelly_fractional':
        # Kelly Fractional
        kelly_pct = stats['kelly_percentage']
        if kelly_pct > 0:
            fractional_kelly = kelly_pct * kelly_fraction
            risk_amount = current_balance * Decimal(str(fractional_kelly))
            method_used = 'Kelly Fractional (Conservative)'
            print(f"   📐 Kelly óptimo: {kelly_pct * 100:.2f}%")
            print(f"   📐 Kelly fraccional ({kelly_fraction * 100:.0f}%): {fractional_kelly * 100:.2f}%")
        else:
            # Fallback a fixed fractional
            risk_amount = current_balance * Decimal(str(risk_per_trade_pct / 100))
            method_used = 'Fixed Fractional (fallback - no hay estadísticas)'
            print(f"   ⚠️  Kelly no viable (sin estadísticas), usando Fixed Fractional")
            print(f"   📐 Risk Per Trade: {risk_per_trade_pct}%")
    
    elif position_method == 'fixed_fractional':
        risk_amount = current_balance * Decimal(str(risk_per_trade_pct / 100))
        method_used = 'Fixed Fractional'
        print(f"   📐 Risk Per Trade: {risk_per_trade_pct}%")
    
    else:
        # Otros métodos
        position_result = capital_manager.calculate_position_size(
            current_balance=current_balance,
            symbol=None,
            entry_price=None,
            stop_loss_price=None,
            atr_value=None
        )
        risk_amount = position_result.risk_amount
        method_used = position_result.method_used
        print(f"   📐 Método: {method_used}")
    
    # Aplicar límites
    min_amount = Decimal(str(min_position_size))
    max_amount = Decimal(str(max_position_size))
    max_risk_amount = current_balance * Decimal(str(max_risk_per_trade_pct / 100))
    
    # Asegurar que no exceda el máximo
    risk_amount = min(risk_amount, max_risk_amount)
    
    # Aplicar límites min/max
    if risk_amount < min_amount:
        risk_amount = min_amount
        print(f"   ⚠️  Ajustado al mínimo: ${min_amount:.2f}")
    elif risk_amount > max_amount:
        risk_amount = max_amount
        print(f"   ⚠️  Ajustado al máximo: ${max_amount:.2f}")
    
    # Para opciones binarias, el monto es directamente el risk_amount
    final_amount = risk_amount
    
    print("-" * 60)
    print("\n" + "=" * 60)
    print("RESULTADO".center(60))
    print("=" * 60)
    print(f"\n💰 Balance actual: ${current_balance:.2f}")
    print(f"📊 Método usado: {method_used}")
    print(f"💵 Monto por trade: ${final_amount:.2f}")
    if current_balance > 0:
        print(f"📈 Porcentaje del balance: {(float(final_amount) / float(current_balance)) * 100:.2f}%")
    else:
        print(f"⚠️  Balance es $0.00 - No se pueden realizar trades")
    print(f"\n🔒 Límites aplicados:")
    print(f"   • Mínimo: ${min_amount:.2f}")
    print(f"   • Máximo: ${max_amount:.2f}")
    print(f"   • Max Risk: {max_risk_per_trade_pct}% = ${max_risk_amount:.2f}")
    
    if final_amount >= current_balance:
        print(f"\n⚠️  ADVERTENCIA: El monto calculado (${final_amount:.2f}) es mayor o igual al balance")
        print(f"   El sistema debería rechazar trades con balance insuficiente")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    calcular_monto_trade()

