#!/bin/bash
# Script para diagnosticar errores 500 en el servidor
# Uso: ./scripts/diagnose_500_error.sh

echo "=========================================="
echo "🔍 DIAGNÓSTICO DE ERROR 500"
echo "=========================================="
echo ""

# 1. Verificar estado de servicios
echo "📊 1. Estado de servicios:"
echo "   - Gunicorn:"
sudo systemctl is-active intradia-gunicorn.service
echo "   - Daphne:"
sudo systemctl is-active intradia-daphne.service
echo ""

# 2. Ver últimos logs de Gunicorn (errores)
echo "📋 2. Últimos errores de Gunicorn:"
sudo tail -n 50 /var/log/gunicorn/intradia_error.log 2>/dev/null || echo "   ⚠️  No se encontró el archivo de log"
echo ""

# 3. Ver logs de Django (si existen)
echo "📋 3. Últimos logs de Django:"
sudo tail -n 50 /var/log/intradia/django.log 2>/dev/null || echo "   ⚠️  No se encontró el archivo de log"
echo ""

# 4. Verificar permisos de archivos
echo "🔐 4. Verificando permisos de templates:"
ls -la /var/www/intradia.com.co/templates/dashboard_precios_realtime_v2.html 2>/dev/null || echo "   ❌ Template dashboard no encontrado"
ls -la /var/www/intradia.com.co/templates/engine/services_admin.html 2>/dev/null || echo "   ❌ Template services_admin no encontrado"
echo ""

# 5. Verificar base de datos
echo "💾 5. Verificando conexión a base de datos:"
cd /var/www/intradia.com.co
source venv/bin/activate 2>/dev/null
python manage.py check --database default 2>&1 | head -20
echo ""

# 6. Verificar sintaxis de Python
echo "🐍 6. Verificando sintaxis de views.py:"
python -m py_compile engine/views.py 2>&1 || echo "   ❌ Error de sintaxis detectado"
echo ""

# 7. Verificar imports
echo "📦 7. Verificando imports críticos:"
python -c "
import sys
sys.path.insert(0, '/var/www/intradia.com.co')
try:
    from engine.views import dashboard, services_admin
    print('   ✅ Imports de views OK')
except Exception as e:
    print(f'   ❌ Error en imports: {e}')
" 2>&1
echo ""

# 8. Verificar configuración Django
echo "⚙️  8. Verificando configuración Django:"
python manage.py check 2>&1 | head -30
echo ""

echo "=========================================="
echo "✅ Diagnóstico completado"
echo "=========================================="
echo ""
echo "💡 Para ver logs en tiempo real:"
echo "   sudo tail -f /var/log/gunicorn/intradia_error.log"

