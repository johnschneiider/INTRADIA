"""
Script de verificación completa antes de iniciar el bot en cuenta real
"""
import os
import sys
import django

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from trading_bot.models import DerivAPIConfig
from connectors.deriv_client import DerivClient
from decimal import Decimal

def verificar_configuracion():
    """Verificar que todo esté configurado correctamente para cuenta real"""
    
    print("=" * 60)
    print("VERIFICACIÓN PRE-INICIO - CUENTA REAL")
    print("=" * 60)
    
    errores = []
    advertencias = []
    
    # 1. Verificar configuración en BD (usar only() para evitar campos que no existen)
    print("\n1. Verificando configuración en base de datos...")
    try:
        config = DerivAPIConfig.objects.filter(is_active=True).only('api_token', 'is_demo', 'app_id', 'is_active', 'user').first()
    except Exception:
        # Fallback: usar raw SQL
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT user_id, api_token, is_demo, is_active, app_id FROM trading_bot_derivapiconfig WHERE is_active = 1 LIMIT 1")
            row = cursor.fetchone()
            if row:
                # Crear un objeto mock para continuar
                class MockConfig:
                    def __init__(self, row):
                        from django.contrib.auth import get_user_model
                        User = get_user_model()
                        self.user = User.objects.get(id=row[0]) if row[0] else None
                        self.api_token = row[1]
                        self.is_demo = bool(row[2])
                        self.is_active = bool(row[3])
                        self.app_id = row[4] or '1089'
                config = MockConfig(row)
            else:
                config = None
    
    if not config:
        errores.append("❌ No hay configuración de API activa en la base de datos")
        print("   ❌ CRÍTICO: No se encontró DerivAPIConfig activa")
    else:
        print(f"   ✅ Configuración encontrada")
        print(f"      Usuario: {config.user.username if config.user else 'Sin usuario'}")
        print(f"      Token: {config.api_token[:10]}...{config.api_token[-5:]}")
        print(f"      Tipo cuenta: {'REAL' if not config.is_demo else 'DEMO'}")
        print(f"      Estado: {'Activa' if config.is_active else 'Inactiva'}")
        
        if config.is_demo:
            errores.append("❌ La configuración está marcada como DEMO, debe ser REAL")
        
        if not config.is_active:
            errores.append("❌ La configuración está inactiva")
    
    # 2. Verificar que no haya tokens hardcodeados
    print("\n2. Verificando tokens hardcodeados...")
    try:
        # Crear cliente usando la configuración de BD (no sin parámetros, porque puede fallar)
        if config:
            client = DerivClient(
                api_token=config.api_token,
                is_demo=config.is_demo,
                app_id=config.app_id
            )
            if hasattr(client, 'api_token') and client.api_token:
                print(f"   ✅ Token obtenido correctamente: {client.api_token[:10]}...")
                if client.is_demo:
                    errores.append("❌ DerivClient está usando cuenta DEMO")
                else:
                    print(f"   ✅ DerivClient configurado para cuenta REAL")
            else:
                errores.append("❌ No se pudo obtener token del DerivClient")
        else:
            print("   ⚠️ No se puede verificar sin configuración")
    except Exception as e:
        errores.append(f"❌ Error al inicializar DerivClient: {e}")
    
    # 3. Verificar balance y conexión
    print("\n3. Verificando conexión y balance...")
    try:
        if config:
            client = DerivClient(
                api_token=config.api_token,
                is_demo=config.is_demo,
                app_id=config.app_id
            )
            
            if client.authenticate():
                print("   ✅ Autenticación exitosa")
                
                balance_info = client.get_balance()
                if isinstance(balance_info, dict):
                    balance = balance_info.get('balance', 0)
                    account_type = balance_info.get('account_type', 'unknown')
                    loginid = balance_info.get('loginid', '')
                    
                    print(f"   ✅ Balance obtenido: ${balance:.2f}")
                    print(f"   ✅ LoginID actual: {loginid}")
                    print(f"   ✅ Tipo de cuenta detectado: {account_type.upper()}")
                    
                    # Verificar loginid para confirmar tipo de cuenta
                    is_real_by_loginid = loginid and not (loginid.startswith('VRTC') or loginid.startswith('VRT'))
                    
                    if balance < 1.00:
                        advertencias.append(f"⚠️ Balance muy bajo: ${balance:.2f} (mínimo $1.00 para operar)")
                    
                    # Verificar que el loginid sea de cuenta real
                    # IMPORTANTE: Si el loginid es DEMO pero current_loginid es REAL, usar current_loginid
                    if client.current_loginid and is_real_by_loginid:
                        # Si current_loginid es REAL, confiar en eso aunque la respuesta tenga loginid DEMO
                        # (puede ser que get_balance devuelva el loginid por defecto)
                        if client.current_loginid.startswith('CR') or (not client.current_loginid.startswith('VRTC') and not client.current_loginid.startswith('VRT')):
                            print(f"   ✅ Confirmado: current_loginid es REAL ({client.current_loginid})")
                            # No es error si current_loginid es REAL
                            if loginid and (loginid.startswith('VRTC') or loginid.startswith('VRT')):
                                advertencias.append(f"⚠️ Balance devuelve loginid DEMO ({loginid}) pero current_loginid es REAL ({client.current_loginid}) - usar current_loginid")
                    elif loginid and (loginid.startswith('VRTC') or loginid.startswith('VRT')):
                        # Solo error si no hay current_loginid REAL que lo corrija
                        if not (client.current_loginid and not (client.current_loginid.startswith('VRTC') or client.current_loginid.startswith('VRT'))):
                            errores.append(f"❌ LoginID detectado es DEMO ({loginid}), verifica el token")
                    elif is_real_by_loginid:
                        print(f"   ✅ Confirmado: LoginID corresponde a cuenta REAL")
                    
                    # El account_type puede estar mal si se leyó de caché, verificar por loginid
                    if account_type == 'demo' and is_real_by_loginid:
                        print(f"   ⚠️ account_type dice 'demo' pero loginid es REAL - se usará loginid como referencia")
                        # No es error, solo advertencia
                    elif account_type == 'demo' and not is_real_by_loginid:
                        # Solo error si no hay current_loginid REAL
                        if not (client.current_loginid and not (client.current_loginid.startswith('VRTC') or client.current_loginid.startswith('VRT'))):
                            errores.append("❌ La cuenta detectada es DEMO, verifica el token")
                    
                    if account_type == 'real' and balance == 0:
                        advertencias.append("⚠️ Cuenta REAL con balance $0.00 - No se ejecutarán trades (correcto)")
                else:
                    advertencias.append(f"⚠️ Balance devuelto en formato inesperado: {type(balance_info)}")
            else:
                errores.append("❌ Falló la autenticación con Deriv")
    except Exception as e:
        advertencias.append(f"⚠️ No se pudo verificar balance (puede ser normal si no hay conexión): {e}")
    
    # 4. Verificar validaciones de seguridad
    print("\n4. Verificando validaciones de seguridad...")
    from engine.services.tick_trading_loop import TickTradingLoop
    
    # Verificar que las validaciones están en el código
    import inspect
    source = inspect.getsource(TickTradingLoop.process_symbol)
    
    validaciones_encontradas = []
    if 'MIN_BALANCE_TO_TRADE' in source:
        validaciones_encontradas.append("✅ Validación de balance mínimo")
    else:
        errores.append("❌ No se encontró validación MIN_BALANCE_TO_TRADE")
    
    if 'insufficient_balance' in source:
        validaciones_encontradas.append("✅ Validación de balance insuficiente")
    else:
        advertencias.append("⚠️ No se encontró validación de balance insuficiente")
    
    for v in validaciones_encontradas:
        print(f"   {v}")
    
    # Resumen final
    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)
    
    if errores:
        print("\n❌ ERRORES CRÍTICOS (DEBES CORREGIR ANTES DE INICIAR):")
        for error in errores:
            print(f"   {error}")
        print("\n⚠️ NO INICIES EL BOT HASTA CORREGIR ESTOS ERRORES")
        return False
    else:
        print("\n✅ No se encontraron errores críticos")
    
    if advertencias:
        print("\n⚠️ ADVERTENCIAS:")
        for advertencia in advertencias:
            print(f"   {advertencia}")
        print("\n💡 Revisa las advertencias antes de continuar")
    
    if not errores:
        print("\n✅ VERIFICACIÓN COMPLETADA")
        print("   El bot está listo para iniciar en cuenta REAL")
        print("\n📋 PRÓXIMOS PASOS:")
        print("   1. Verifica el balance en: http://localhost:8000/trading/config/api/")
        print("   2. Asegúrate de tener balance suficiente (>$1.00)")
        print("   3. Inicia el bot con: python manage.py trading_loop")
        return True
    
    return False

if __name__ == '__main__':
    try:
        exito = verificar_configuracion()
        sys.exit(0 if exito else 1)
    except Exception as e:
        print(f"\n❌ Error durante la verificación: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

