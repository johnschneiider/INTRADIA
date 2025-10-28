"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.
"""

import os
import django

# Configurar settings primero
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Configurar Django
django.setup()

# Intentar cargar Channels, si no está disponible usar WSGI normal
try:
    from channels.routing import ProtocolTypeRouter, URLRouter
    from channels.auth import AuthMiddlewareStack
    from django.core.asgi import get_asgi_application
    import market.routing
    
    # Cargar aplicación Django
    django_asgi_app = get_asgi_application()
    
    application = ProtocolTypeRouter({
        "http": django_asgi_app,
        "websocket": URLRouter(
            market.routing.websocket_urlpatterns
        ),
    })
except ImportError:
    # Channels no instalado, usar WSGI normal
    from django.core.asgi import get_asgi_application
    application = get_asgi_application()
