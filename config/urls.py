"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.decorators import api_view


@api_view(['GET'])
def status_view(request):
    """API endpoint para verificar estado del sistema"""
    return Response({'status': 'ok'})

@never_cache
def home_view(request):
    """Vista para la landing page - renderiza HTML directamente"""
    # Asegurar que no se trate como API
    response = render(request, 'home.html')
    response['Content-Type'] = 'text/html; charset=utf-8'
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home_view, name='home'),
    path('api/status/', status_view, name='api-status'),
    path('cuentas/', include('cuentas.urls')),
    path('engine/', include('engine.urls')),
    path('trading/', include('trading_bot.urls')),
]
