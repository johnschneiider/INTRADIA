#!/usr/bin/env python
"""
Script para probar que Celery funciona correctamente
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from engine.tasks import heartbeat

def test_celery():
    """Probar que Celery funciona"""
    print("🧪 Probando Celery...")
    
    try:
        # Enviar tarea de prueba
        result = heartbeat.delay()
        print(f"✅ Tarea enviada: {result.id}")
        
        # Esperar resultado
        task_result = result.get(timeout=10)
        print(f"✅ Resultado: {task_result}")
        
        print("🎉 ¡Celery funcionando correctamente!")
        
    except Exception as e:
        print(f"❌ Error en Celery: {e}")
        print("💡 Asegúrate de que el worker esté ejecutándose")

if __name__ == '__main__':
    test_celery()











