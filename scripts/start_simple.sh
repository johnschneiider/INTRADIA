#!/usr/bin/env bash
# Script simplificado para iniciar INTRADIA sin Redis

echo "🚀 Iniciando INTRADIA (modo desarrollo)..."
echo "📊 Usando SQLite en lugar de Redis para Celery"

# Verificar que Django funciona
echo "🔍 Verificando Django..."
python manage.py check

if [ $? -ne 0 ]; then
    echo "❌ Error en configuración de Django"
    exit 1
fi

echo "✅ Django configurado correctamente"

# Aplicar migraciones
echo "📊 Aplicando migraciones..."
python manage.py migrate

# Crear datos de ejemplo si no existen
echo "🎯 Verificando datos de ejemplo..."
python manage.py create_dashboard_data

echo ""
echo "🎉 ¡INTRADIA listo!"
echo ""
echo "📱 Para acceder al dashboard:"
echo "   http://localhost:8000/engine/"
echo ""
echo "🔧 Para iniciar servicios:"
echo "   1. Servidor Django: python manage.py runserver"
echo "   2. Celery Worker: python -m celery -A engine worker -l info"
echo "   3. Celery Beat: python -m celery -A engine beat -l info"
echo ""
echo "💡 Nota: Celery ahora usa base de datos en lugar de Redis"


