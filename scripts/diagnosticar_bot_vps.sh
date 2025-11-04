#!/bin/bash
# Script para diagnosticar por qué el bot no está operando en la VPS

echo "=========================================="
echo "🔍 DIAGNÓSTICO DEL BOT DE TRADING"
echo "=========================================="
echo ""

echo "1️⃣ Estado de los servicios:"
echo "----------------------------"
sudo systemctl status intradia-trading-loop.service --no-pager -l
echo ""
sudo systemctl status intradia-save-ticks.service --no-pager -l
echo ""
sudo systemctl status intradia-gunicorn.service --no-pager -l
echo ""

echo "2️⃣ Últimas 50 líneas del log de trading_loop:"
echo "---------------------------------------------"
sudo tail -n 50 /var/log/intradia/trading_loop.log
echo ""

echo "3️⃣ Últimas 50 líneas del log de errores:"
echo "-----------------------------------------"
sudo tail -n 50 /var/log/intradia/trading_loop_error.log
echo ""

echo "4️⃣ Verificar si el proceso está corriendo:"
echo "-------------------------------------------"
ps aux | grep "trading_loop" | grep -v grep
echo ""

echo "5️⃣ Verificar configuración de CapitalConfig:"
echo "---------------------------------------------"
cd /var/www/intradia.com.co
source venv/bin/activate
python manage.py shell <<EOF
from engine.models import CapitalConfig
config = CapitalConfig.get_active()
if config:
    print(f"Config activa encontrada:")
    print(f"  - Profit target: {config.profit_target}")
    print(f"  - Max loss: {config.max_loss}")
    print(f"  - Max trades: {config.max_trades}")
    print(f"  - Disable max trades: {config.disable_max_trades}")
    print(f"  - Is active: {config.is_active}")
else:
    print("❌ No hay configuración activa")
EOF

echo ""
echo "6️⃣ Verificar conexión con Deriv API:"
echo "-------------------------------------"
python manage.py shell <<EOF
from trading_bot.models import DerivAPIConfig
config = DerivAPIConfig.objects.filter(is_active=True).first()
if config:
    print(f"✅ Configuración de API encontrada:")
    print(f"  - Token: {config.api_token[:10]}...")
    print(f"  - Is active: {config.is_active}")
    print(f"  - Is demo: {config.is_demo}")
    print(f"  - User: {config.user.username if config.user else 'N/A'}")
else:
    print("❌ No hay configuración de API activa")
EOF

echo ""
echo "=========================================="
echo "✅ Diagnóstico completado"
echo "=========================================="

