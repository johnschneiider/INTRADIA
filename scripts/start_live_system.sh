#!/usr/bin/env bash
# Script para iniciar el sistema completo con Deriv API real

echo "🚀 Iniciando INTRADIA con Deriv API..."

# Verificar token
if [ -z "$DERIV_API_TOKEN" ] || [ "$DERIV_API_TOKEN" = "tu_token_aqui" ]; then
    echo "❌ DERIV_API_TOKEN no configurado"
    echo "🔑 Configura tu token en .env o variables de entorno"
    exit 1
fi

echo "✅ Token Deriv configurado: ${DERIV_API_TOKEN:0:10}..."

# Migrar base de datos
echo "📊 Configurando base de datos..."
python manage.py migrate

# Obtener datos históricos iniciales
echo "📈 Obteniendo datos históricos de Deriv..."
python manage.py shell -c "
from engine.tasks import fetch_historical_data
from django.conf import settings
import os

symbols = os.getenv('SYMBOLS', 'EURUSD,GBPUSD,USDJPY').split(',')
for symbol in symbols:
    print(f'Obteniendo datos para {symbol}...')
    fetch_historical_data(symbol, '1d', 30)
    fetch_historical_data(symbol, '5m', 100)
"

# Iniciar servicios
echo "🔄 Iniciando servicios..."
echo "   - Web server: http://localhost:8000"
echo "   - Celery worker: procesando tareas"
echo "   - Celery beat: programando tareas"

# Ejecutar en paralelo
python manage.py runserver 0.0.0.0:8000 &
celery -A engine worker -l info &
celery -A engine beat -l info &

echo "🎯 Sistema INTRADIA funcionando con Deriv API!"
echo "📊 Endpoints disponibles:"
echo "   - http://localhost:8000/api/status"
echo "   - http://localhost:8000/engine/test-deriv"
echo "   - http://localhost:8000/engine/backtest/run"

wait

