#!/usr/bin/env python3
"""
Script de diagnóstico para identificar por qué no se están creando entradas
"""

import os
import sys
import django
from pathlib import Path

# Configurar Django
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils import timezone
from datetime import timedelta
from market.models import Tick
from monitoring.models import OrderAudit
from engine.services.tick_trading_loop import TickTradingLoop

def diagnosticar_entradas():
    """Diagnosticar por qué no se están creando entradas"""
    
    print("=" * 80)
    print("🔍 DIAGNÓSTICO DE CREACIÓN DE ENTRADAS")
    print("=" * 80)
    print()
    
    # 1. Verificar ticks disponibles
    print("1️⃣ VERIFICANDO TICKS DISPONIBLES")
    print("-" * 80)
    since = timezone.now() - timedelta(hours=24)
    ticks_count = Tick.objects.filter(timestamp__gte=since).count()
    symbols_with_ticks = Tick.objects.filter(timestamp__gte=since).values_list('symbol', flat=True).distinct()
    
    print(f"   📊 Ticks en últimas 24h: {ticks_count}")
    print(f"   📈 Símbolos con ticks: {len(symbols_with_ticks)}")
    
    if len(symbols_with_ticks) > 0:
        print(f"   🔍 Primeros 10 símbolos: {list(symbols_with_ticks[:10])}")
    else:
        print("   ❌ NO HAY TICKS DISPONIBLES - El script save_realtime_ticks.py debe estar corriendo")
        return
    
    print()
    
    # 2. Verificar órdenes recientes
    print("2️⃣ VERIFICANDO ÓRDENES RECIENTES")
    print("-" * 80)
    recent_orders = OrderAudit.objects.filter(timestamp__gte=since).order_by('-timestamp')[:10]
    print(f"   📋 Órdenes en últimas 24h: {OrderAudit.objects.filter(timestamp__gte=since).count()}")
    
    if recent_orders.exists():
        print(f"   ✅ Últimas órdenes:")
        for order in recent_orders:
            print(f"      • {order.symbol} {order.action} - {order.status} ({order.timestamp.strftime('%H:%M:%S')})")
    else:
        print("   ⚠️ No hay órdenes recientes")
    
    print()
    
    # 3. Probar estrategia en símbolos reales
    print("3️⃣ PROBANDO ESTRATEGIA EN SÍMBOLOS ACTIVOS")
    print("-" * 80)
    
    # Excluir símbolos no operables
    excluded = ['cry', 'OTC', 'BOOM', 'CRASH']
    test_symbols = [s for s in symbols_with_ticks if not any(s.startswith(prefix) for prefix in excluded)][:5]
    
    if not test_symbols:
        print("   ❌ No hay símbolos válidos para probar")
        return
    
    loop = TickTradingLoop(use_statistical=True)
    
    for symbol in test_symbols:
        print(f"\n   🔍 Analizando {symbol}...")
        
        # Verificar ticks del símbolo
        symbol_ticks = Tick.objects.filter(symbol=symbol, timestamp__gte=since).count()
        print(f"      📊 Ticks disponibles: {symbol_ticks}")
        
        if symbol_ticks < 10:
            print(f"      ❌ Insuficientes ticks (< 10)")
            continue
        
        # Intentar analizar
        try:
            signal = loop.strategy.analyze_symbol(symbol)
            
            if signal:
                print(f"      ✅ SEÑAL GENERADA:")
                print(f"         • Dirección: {signal.direction}")
                print(f"         • Tipo: {signal.signal_type}")
                print(f"         • Confianza: {signal.confidence:.1%}")
                print(f"         • Z-score: {signal.z_score:.2f}")
                print(f"         • Confluencia: {getattr(signal, 'confluence_score', 0)}")
                print(f"         • ATR ratio: {getattr(signal, 'atr_ratio', 0)*100:.3f}%")
                
                # Verificar si debería entrar
                should_enter = loop.strategy.should_enter_trade(signal)
                print(f"         • ¿Debe entrar?: {'✅ SÍ' if should_enter else '❌ NO'}")
                
                if not should_enter:
                    if signal.confidence < 0.30:
                        print(f"         ⚠️ Confianza muy baja: {signal.confidence:.1%} < 30%")
                    if getattr(signal, 'confluence_score', 0) < 1:
                        print(f"         ⚠️ Confluencia insuficiente: {getattr(signal, 'confluence_score', 0)} < 1")
                
                # Verificar intervalo
                now = timezone.now()
                last_trade = loop.last_trade_time.get(symbol)
                if last_trade:
                    elapsed = (now - last_trade).total_seconds()
                    remaining = 60 - elapsed
                    print(f"         • Tiempo desde última entrada: {elapsed:.0f}s (faltan {remaining:.0f}s para próxima)")
                    if elapsed < 60:
                        print(f"         ⚠️ Intervalo mínimo no cumplido (60s)")
                
                # Si debería entrar, simular proceso completo
                if should_enter:
                    print(f"      🚀 SIMULANDO PROCESO COMPLETO...")
                    result = loop.process_symbol(symbol)
                    if result:
                        print(f"         • Estado: {result.get('status')}")
                        if result.get('status') == 'executed':
                            print(f"         ✅ ORDEN EJECUTADA")
                        else:
                            print(f"         ❌ NO EJECUTADA: {result.get('reason', 'unknown')}")
            else:
                print(f"      ❌ NO SE GENERÓ SEÑAL")
                
        except Exception as e:
            print(f"      ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
    
    print()
    print("=" * 80)
    print("✅ DIAGNÓSTICO COMPLETADO")
    print("=" * 80)
    print()
    print("💡 SUGERENCIAS:")
    print("   • Si no hay señales: verificar filtros de estrategia (RSI, EMA, ATR, etc.)")
    print("   • Si hay señales pero no entran: verificar umbrales de confianza/confluencia")
    print("   • Si hay timeouts: verificar conexión WebSocket con Deriv")
    print("   • Si hay 'not_offered': el contrato no está disponible para ese símbolo/duración")
    print()

if __name__ == "__main__":
    diagnosticar_entradas()

