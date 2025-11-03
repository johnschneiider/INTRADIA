#!/usr/bin/env python3
"""
Script para crear o actualizar un usuario administrador en Django
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

from django.contrib.auth.models import User

def create_admin_user():
    """Crear o actualizar usuario administrador"""
    username = "admin10"
    password = "Malware2025"
    email = "admin10@vitalmix.com.co"
    
    try:
        # Intentar obtener el usuario existente
        user = User.objects.get(username=username)
        print(f"⚠️  Usuario '{username}' ya existe. Actualizando contraseña...")
        user.set_password(password)
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.email = email
        user.save()
        print(f"✅ Usuario '{username}' actualizado exitosamente")
        print(f"   - Contraseña: {password}")
        print(f"   - Es staff: {user.is_staff}")
        print(f"   - Es superusuario: {user.is_superuser}")
        
    except User.DoesNotExist:
        # Crear nuevo usuario
        user = User.objects.create_user(
            username=username,
            password=password,
            email=email,
            is_staff=True,
            is_superuser=True,
            is_active=True
        )
        print(f"✅ Usuario '{username}' creado exitosamente")
        print(f"   - Contraseña: {password}")
        print(f"   - Es staff: {user.is_staff}")
        print(f"   - Es superusuario: {user.is_superuser}")
    
    return user

if __name__ == "__main__":
    print("=" * 60)
    print("🔐 Creando/Actualizando usuario administrador...")
    print("=" * 60)
    
    try:
        user = create_admin_user()
        print("\n" + "=" * 60)
        print("✅ Proceso completado exitosamente")
        print("=" * 60)
        print(f"\n📋 Credenciales:")
        print(f"   Usuario: {user.username}")
        print(f"   Contraseña: Malware2025")
        print(f"   Email: {user.email}")
        print(f"\n🌐 Puedes iniciar sesión en: http://vitalmix.com.co/admin/")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

