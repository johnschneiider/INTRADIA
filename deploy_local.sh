#!/bin/bash
# Script para desarrollo local (sin nginx/gunicorn)
# Simula el ambiente de producción

set -e

echo "🚀 PREPARANDO AMBIENTE DE DESARROLLO LOCAL..."

# 1. Activar entorno virtual
echo "⚙️ Activando entorno virtual..."
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "❌ Error: venv no encontrado. Ejecuta: python -m venv venv"
    exit 1
fi

# 2. Instalar dependencias
echo "📚 Instalando dependencias..."
pip install -r requirements.txt

# 3. Crear directorios
echo "📁 Creando directorios..."
mkdir -p static media

# 4. Migraciones
echo "🗄️ Ejecutando migraciones..."
python manage.py migrate

# 5. Recolectar estáticos
echo "🗂️ Recolectando archivos estáticos..."
python manage.py collectstatic --noinput

# 6. Crear superusuario (solo si no existe)
echo "👤 Creando superusuario si es necesario..."
python manage.py shell << EOF
from django.contrib.auth.models import User
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@intradia.com', 'admin123')
    print("Superusuario 'admin' creado (password: admin123)")
else:
    print("Superusuario ya existe")
EOF

echo ""
echo "✅ AMBIENTE LISTO!"
echo ""
echo "📊 Comandos para iniciar:"
echo "  Terminal 1: python manage.py trading_loop"
echo "  Terminal 2: celery -A config worker -l info"
echo "  Terminal 3: celery -A config beat -l info"
echo ""
echo "O usar: INICIO_COMPLETO.bat (Windows)"

