# Celery initialization (opcional)
try:
    from .celery import celery_app
    __all__ = ('celery_app',)
except (ImportError, ModuleNotFoundError):
    # Celery no instalado - el sistema funciona sin tareas automáticas
    # Usar mensajes sin emojis para evitar problemas de encoding en Windows
    import sys
    try:
        print("⚠️  Celery no está instalado. Las tareas programadas no funcionarán.")
        print("💡 Para usar trading automático, instala: pip install celery django-celery-beat django-celery-results")
        print("✅ El sistema funciona sin Celery para ejecuciones manuales.")
    except UnicodeEncodeError:
        # Fallback para sistemas con encoding limitado (Windows)
        print("[WARNING] Celery no esta instalado. Las tareas programadas no funcionaran.")
        print("[INFO] Para usar trading automatico, instala: pip install celery django-celery-beat django-celery-results")
        print("[OK] El sistema funciona sin Celery para ejecuciones manuales.")
    __all__ = ()
