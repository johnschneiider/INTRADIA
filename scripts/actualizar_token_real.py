"""
Script para actualizar el token de API de Deriv en la base de datos
"""
import os
import sys
import django

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from trading_bot.models import DerivAPIConfig
from django.contrib.auth import get_user_model

User = get_user_model()

# Token real proporcionado para cuenta CR9822432 (dtrade)
NUEVO_TOKEN = 'jynzRtypyTiwyLX'

def actualizar_token():
    """Actualizar o crear configuración de token para el primer usuario"""
    # Obtener el primer usuario disponible
    user = User.objects.first()
    
    if not user:
        print("❌ No se encontró ningún usuario en la base de datos")
        print("   Por favor, crea un usuario primero desde la interfaz web")
        return False
    
    # Obtener o crear la configuración (solo campos que existen en BD)
    # Usar only() para evitar errores con campos scope_* que no existen en BD
    try:
        config = DerivAPIConfig.objects.filter(user=user).only('api_token', 'is_demo', 'app_id', 'is_active').first()
        if not config:
            # Crear nueva configuración
            config = DerivAPIConfig.objects.create(
                user=user,
                api_token=NUEVO_TOKEN,
                is_demo=False,
                app_id='1089',
                is_active=True
            )
            print("✅ Configuración creada")
        else:
            # Actualizar existente
            config.api_token = NUEVO_TOKEN
            config.is_demo = False  # Cuenta REAL
            config.is_active = True
            config.app_id = '1089'
            config.save(update_fields=['api_token', 'is_demo', 'is_active', 'app_id'])
            print("✅ Configuración actualizada")
    except Exception as e:
        print(f"⚠️ Error al acceder con only(): {e}")
        # Fallback: usar raw SQL para evitar problemas con campos que no existen
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id FROM trading_bot_derivapiconfig WHERE user_id = ?
            """, [user.id])
            row = cursor.fetchone()
            
            if row:
                # Actualizar existente
                cursor.execute("""
                    UPDATE trading_bot_derivapiconfig 
                    SET api_token = ?, is_demo = 0, is_active = 1, app_id = '1089'
                    WHERE user_id = ?
                """, [NUEVO_TOKEN, user.id])
                print("✅ Token actualizado usando SQL directo")
            else:
                # Crear nuevo
                cursor.execute("""
                    INSERT INTO trading_bot_derivapiconfig 
                    (user_id, api_token, is_demo, app_id, is_active, created_at, updated_at)
                    VALUES (?, ?, 0, '1089', 1, datetime('now'), datetime('now'))
                """, [user.id, NUEVO_TOKEN])
                print("✅ Token creado usando SQL directo")
        
        # Re-obtener el objeto para mostrar información
        config = DerivAPIConfig.objects.filter(user=user).first()
    
    print("✅ Token actualizado exitosamente")
    print(f"   Usuario: {user.username}")
    print(f"   Token: {config.api_token[:10]}...{config.api_token[-5:]}")
    print(f"   Tipo de cuenta: {'REAL' if not config.is_demo else 'DEMO'}")
    print(f"   Estado: {'Activa' if config.is_active else 'Inactiva'}")
    print(f"\n   Puedes verificar la configuración en:")
    print(f"   http://localhost:8000/trading/config/api/")
    
    return True

if __name__ == '__main__':
    try:
        actualizar_token()
    except Exception as e:
        print(f"❌ Error al actualizar token: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

