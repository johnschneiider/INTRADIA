from django.core.management.base import BaseCommand
from engine.tasks import heartbeat


class Command(BaseCommand):
    help = 'Probar que Celery funciona correctamente'

    def handle(self, *args, **options):
        self.stdout.write("🧪 Probando Celery...")
        
        try:
            # Enviar tarea de prueba
            result = heartbeat.delay()
            self.stdout.write(f"✅ Tarea enviada: {result.id}")
            
            # Esperar resultado
            task_result = result.get(timeout=10)
            self.stdout.write(f"✅ Resultado: {task_result}")
            
            self.stdout.write("🎉 ¡Celery funcionando correctamente!")
            
        except Exception as e:
            self.stdout.write(f"❌ Error en Celery: {e}")
            self.stdout.write("💡 Asegúrate de que el worker esté ejecutándose")








