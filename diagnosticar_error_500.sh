#!/bin/bash

PROJECT_DIR="/var/www/intradia.com.co"
VENV_DIR="${PROJECT_DIR}/venv"

echo "=========================================="
echo "🔍 DIAGNÓSTICO DE ERROR 500"
echo "=========================================="
echo ""

echo "1️⃣ Verificar sintaxis de Python en engine/views.py:"
echo "-----------------------------------"
source "${VENV_DIR}/bin/activate"
python -m py_compile engine/views.py
if [ $? -eq 0 ]; then
    echo "✅ Sintaxis correcta"
else
    echo "❌ Error de sintaxis encontrado"
fi
deactivate
echo ""

echo "2️⃣ Intentar importar el módulo engine.views:"
echo "-----------------------------------"
source "${VENV_DIR}/bin/activate"
python manage.py shell <<EOF
try:
    from engine import views
    print("✅ Módulo engine.views importado correctamente")
    print(f"✅ active_trades_api: {hasattr(views, 'active_trades_api')}")
    print(f"✅ close_trade_api: {hasattr(views, 'close_trade_api')}")
except Exception as e:
    print(f"❌ Error al importar: {e}")
    import traceback
    traceback.print_exc()
EOF
deactivate
echo ""

echo "3️⃣ Ver logs detallados de Daphne (últimas 100 líneas):"
echo "-----------------------------------"
sudo journalctl -u intradia-daphne.service -n 100 --no-pager | tail -n 50
echo ""

echo "4️⃣ Ver logs de Gunicorn (últimas 100 líneas):"
echo "-----------------------------------"
sudo journalctl -u intradia-gunicorn.service -n 100 --no-pager | tail -n 50
echo ""

echo "5️⃣ Verificar estado de los servicios:"
echo "-----------------------------------"
sudo systemctl status intradia-daphne.service --no-pager -l
echo ""
sudo systemctl status intradia-gunicorn.service --no-pager -l
echo ""

echo "6️⃣ Verificar si hay errores en los logs de error de Daphne:"
echo "-----------------------------------"
if [ -f "/var/log/intradia/daphne_error.log" ]; then
    sudo tail -n 50 /var/log/intradia/daphne_error.log
else
    echo "⚠️ Archivo de error no encontrado"
fi
echo ""

echo "7️⃣ Probar importación directa de las funciones:"
echo "-----------------------------------"
source "${VENV_DIR}/bin/activate"
python <<EOF
import sys
import os
sys.path.insert(0, '/var/www/intradia.com.co')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

try:
    from engine.views import active_trades_api, close_trade_api
    print("✅ Funciones importadas correctamente")
    print(f"   - active_trades_api: {active_trades_api}")
    print(f"   - close_trade_api: {close_trade_api}")
except Exception as e:
    print(f"❌ Error al importar funciones: {e}")
    import traceback
    traceback.print_exc()
EOF
deactivate
echo ""

echo "8️⃣ Verificar errores de Django (si hay archivo de logs):"
echo "-----------------------------------"
if [ -f "/var/log/django/error.log" ]; then
    sudo tail -n 50 /var/log/django/error.log
else
    echo "⚠️ Archivo de logs de Django no encontrado"
fi
echo ""

echo "=========================================="
echo "✅ Diagnóstico completado"
echo "=========================================="

