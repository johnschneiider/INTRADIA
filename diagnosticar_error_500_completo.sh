#!/bin/bash

PROJECT_DIR="/var/www/intradia.com.co"
VENV_DIR="${PROJECT_DIR}/venv"

echo "=========================================="
echo "🔍 DIAGNÓSTICO COMPLETO DE ERROR 500"
echo "=========================================="
echo ""

echo "1️⃣ Actualizar código desde GitHub:"
echo "-----------------------------------"
cd "${PROJECT_DIR}"
git pull origin main
echo ""

echo "2️⃣ Verificar sintaxis de Python en engine/views.py:"
echo "-----------------------------------"
source "${VENV_DIR}/bin/activate"
python -m py_compile engine/views.py 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Sintaxis correcta"
else
    echo "❌ Error de sintaxis encontrado"
fi
deactivate
echo ""

echo "3️⃣ Verificar sintaxis de Python en engine/urls.py:"
echo "-----------------------------------"
source "${VENV_DIR}/bin/activate"
python -m py_compile engine/urls.py 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Sintaxis correcta"
else
    echo "❌ Error de sintaxis encontrado"
fi
deactivate
echo ""

echo "4️⃣ Intentar importar engine.views completo:"
echo "-----------------------------------"
source "${VENV_DIR}/bin/activate"
python <<EOF
import sys
import os
sys.path.insert(0, '${PROJECT_DIR}')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
try:
    from engine import views
    print("✅ Módulo engine.views importado correctamente")
    print(f"✅ active_trades_api: {hasattr(views, 'active_trades_api')}")
    print(f"✅ close_trade_api: {hasattr(views, 'close_trade_api')}")
    print(f"✅ get_balance: {hasattr(views, 'get_balance')}")
    print(f"✅ status: {hasattr(views, 'status')}")
except Exception as e:
    print(f"❌ Error al importar: {e}")
    import traceback
    traceback.print_exc()
EOF
deactivate
echo ""

echo "5️⃣ Intentar importar engine.urls:"
echo "-----------------------------------"
source "${VENV_DIR}/bin/activate"
python <<EOF
import sys
import os
sys.path.insert(0, '${PROJECT_DIR}')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
try:
    from engine.urls import urlpatterns
    print("✅ engine.urls importado correctamente")
    print(f"✅ Número de URLs: {len(urlpatterns)}")
    for i, pattern in enumerate(urlpatterns[:5]):
        print(f"   - URL {i+1}: {pattern.pattern}")
except Exception as e:
    print(f"❌ Error al importar engine.urls: {e}")
    import traceback
    traceback.print_exc()
EOF
deactivate
echo ""

echo "6️⃣ Intentar importar config.urls completo:"
echo "-----------------------------------"
source "${VENV_DIR}/bin/activate"
python <<EOF
import sys
import os
sys.path.insert(0, '${PROJECT_DIR}')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
try:
    from config.urls import urlpatterns as main_urls
    print("✅ config.urls importado correctamente")
    print(f"✅ Número de URLs principales: {len(main_urls)}")
except Exception as e:
    print(f"❌ Error al importar config.urls: {e}")
    import traceback
    traceback.print_exc()
EOF
deactivate
echo ""

echo "7️⃣ Ver logs detallados de Daphne con errores:"
echo "-----------------------------------"
sudo journalctl -u intradia-daphne.service -n 200 --no-pager | grep -A 30 -i "error\|exception\|traceback\|ImportError" | tail -n 100
echo ""

echo "8️⃣ Ver logs completos de Daphne (últimas 50 líneas):"
echo "-----------------------------------"
sudo journalctl -u intradia-daphne.service -n 50 --no-pager
echo ""

echo "9️⃣ Ver logs de Gunicorn con errores:"
echo "-----------------------------------"
sudo journalctl -u intradia-gunicorn.service -n 200 --no-pager | grep -A 30 -i "error\|exception\|traceback\|ImportError" | tail -n 100
echo ""

echo "🔟 Verificar archivo de error de Daphne:"
echo "-----------------------------------"
if [ -f "/var/log/intradia/daphne_error.log" ]; then
    echo "📄 Últimas 50 líneas de daphne_error.log:"
    sudo tail -n 50 /var/log/intradia/daphne_error.log
else
    echo "⚠️ Archivo /var/log/intradia/daphne_error.log no existe"
fi
echo ""

echo "1️⃣1️⃣ Verificar estado de los servicios:"
echo "-----------------------------------"
sudo systemctl status intradia-daphne.service --no-pager -l | head -n 20
echo ""
sudo systemctl status intradia-gunicorn.service --no-pager -l | head -n 20
echo ""

echo "1️⃣2️⃣ Probar hacer una petición HTTP directamente:"
echo "-----------------------------------"
curl -s -o /dev/null -w "Status: %{http_code}\n" http://127.0.0.1:8002/engine/status/ || echo "❌ Error al hacer petición"
echo ""

echo "1️⃣3️⃣ Verificar contenido de engine/urls.py (primeras 15 líneas):"
echo "-----------------------------------"
head -n 15 "${PROJECT_DIR}/engine/urls.py"
echo ""

echo "=========================================="
echo "✅ Diagnóstico completado"
echo "=========================================="
echo ""
echo "💡 Si ves errores, copia el traceback completo y compártelo"

