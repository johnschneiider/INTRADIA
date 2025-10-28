from celery import Celery
import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

celery_app = Celery('intradia')
celery_app.config_from_object('django.conf:settings', namespace='CELERY')

# Configurar autodiscovery para todas las apps
celery_app.autodiscover_tasks()

# Configuración adicional para desarrollo sin Redis
celery_app.conf.task_always_eager = False
celery_app.conf.task_eager_propagates = True

# Configuración para Windows (evitar errores de multiprocessing)
if sys.platform.startswith('win'):
    # En Windows usar solo 1 worker (no multiprocessing)
    celery_app.conf.worker_pool = 'solo'
    celery_app.conf.worker_prefetch_multiplier = 1
    celery_app.conf.task_acks_late = True
    celery_app.conf.task_reject_on_worker_lost = True

__all__ = ('celery_app',)
