#!/bin/bash
# Script para actualizar desde GitHub y reiniciar servicios en la VPS

echo "=========================================="
echo "🔄 ACTUALIZAR Y REINICIAR BOT"
echo "=========================================="
echo ""

cd /var/www/intradia.com.co

echo "1️⃣ Obteniendo cambios de GitHub..."
echo "-----------------------------------"
git pull origin main

if [ $? -ne 0 ]; then
    echo "❌ Error al hacer git pull"
    exit 1
fi

echo ""
echo "2️⃣ Instalando dependencias..."
echo "-------------------------------"
source venv/bin/activate
pip install -r requirements.txt --quiet

echo ""
echo "3️⃣ Ejecutando migraciones..."
echo "------------------------------"
python manage.py migrate --noinput

echo ""
echo "4️⃣ Recopilando archivos estáticos..."
echo "--------------------------------------"
python manage.py collectstatic --noinput --clear

echo ""
echo "5️⃣ Reiniciando servicios..."
echo "-----------------------------"
sudo systemctl daemon-reload
sudo systemctl restart intradia-trading-loop.service
sudo systemctl restart intradia-save-ticks.service
sudo systemctl restart intradia-gunicorn.service

echo ""
echo "6️⃣ Verificando estado..."
echo "-------------------------"
sleep 2
sudo systemctl status intradia-trading-loop.service --no-pager -l | head -n 20

echo ""
echo "=========================================="
echo "✅ Actualización completada"
echo "=========================================="
echo ""
echo "Para ver los logs en tiempo real:"
echo "  sudo tail -f /var/log/intradia/trading_loop.log"

