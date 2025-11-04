#!/bin/bash
# Script para diagnosticar por qué no se ejecutan operaciones

echo "=========================================="
echo "🔍 DIAGNÓSTICO DE OPERACIONES"
echo "=========================================="
echo ""

cd /var/www/intradia.com.co
source venv/bin/activate

echo "1️⃣ Verificar configuración de API:"
echo "-----------------------------------"
python manage.py shell <<EOF
from trading_bot.models import DerivAPIConfig
config = DerivAPIConfig.objects.filter(is_active=True).first()
if config:
    print(f"✅ Configuración de API encontrada:")
    print(f"  - Token: {config.api_token[:10]}...")
    print(f"  - Is active: {config.is_active}")
    print(f"  - Is demo: {config.is_demo}")
    print(f"  - User: {config.user.username if config.user else 'N/A'}")
    
    # Verificar conexión
    try:
        from connectors.deriv_client import DerivClient
        client = DerivClient(api_token=config.api_token, is_demo=config.is_demo, app_id=config.app_id)
        balance_info = client.get_balance()
        if isinstance(balance_info, dict):
            balance = balance_info.get('balance', 0)
            account_type = balance_info.get('account_type', 'demo')
            loginid = balance_info.get('loginid', 'N/A')
            print(f"  - Balance: \${balance}")
            print(f"  - Account type: {account_type}")
            print(f"  - Login ID: {loginid}")
        else:
            print(f"  - Balance: \${balance_info}")
    except Exception as e:
        print(f"  ❌ Error conectando: {str(e)[:100]}")
else:
    print("❌ No hay configuración de API activa")
EOF

echo ""
echo "2️⃣ Verificar última operación ejecutada:"
echo "-----------------------------------------"
python manage.py shell <<EOF
from monitoring.models import OrderAudit
from django.utils import timezone
from datetime import timedelta

last_trade = OrderAudit.objects.order_by('-timestamp').first()
if last_trade:
    print(f"Última operación:")
    print(f"  - Símbolo: {last_trade.symbol}")
    print(f"  - Estado: {last_trade.status}")
    print(f"  - Timestamp: {last_trade.timestamp}")
    print(f"  - Hace: {timezone.now() - last_trade.timestamp}")
    
    # Operaciones en la última hora
    one_hour_ago = timezone.now() - timedelta(hours=1)
    recent = OrderAudit.objects.filter(timestamp__gte=one_hour_ago)
    print(f"\nOperaciones en última hora: {recent.count()}")
    print(f"  - Ejecutadas: {recent.filter(status__in=['pending', 'active', 'won', 'lost']).count()}")
    print(f"  - Rechazadas: {recent.filter(status='rejected').count()}")
    print(f"  - Omitidas: {recent.filter(status='skipped').count()}")
    
    # Últimas 5 operaciones rechazadas
    print(f"\nÚltimas 5 operaciones rechazadas:")
    for trade in recent.filter(status='rejected').order_by('-timestamp')[:5]:
        print(f"  - {trade.symbol} ({trade.timestamp}): {trade.reason or 'N/A'}")
else:
    print("❌ No hay operaciones registradas")
EOF

echo ""
echo "3️⃣ Verificar logs recientes de trading_loop:"
echo "----------------------------------------------"
echo "Últimas 20 líneas con señales generadas:"
sudo tail -n 200 /var/log/intradia/trading_loop.log | grep -E "(FUERZA OK|SEÑAL GENERADA|Ejecutando|place_order|rejected|rechazado)" | tail -n 20

echo ""
echo "4️⃣ Verificar estado del servicio:"
echo "-----------------------------------"
sudo systemctl status intradia-trading-loop.service --no-pager -l | head -n 15

echo ""
echo "5️⃣ Verificar configuración de CapitalConfig:"
echo "----------------------------------------------"
python manage.py shell <<EOF
from engine.models import CapitalConfig
config = CapitalConfig.get_active()
if config:
    print(f"Config activa:")
    print(f"  - Profit target: {config.profit_target}")
    print(f"  - Max loss: {config.max_loss}")
    print(f"  - Max trades: {config.max_trades}")
    print(f"  - Disable max trades: {config.disable_max_trades}")
    print(f"  - Is active: {config.is_active}")
else:
    print("❌ No hay configuración activa")
EOF

echo ""
echo "=========================================="
echo "✅ Diagnóstico completado"
echo "=========================================="
echo ""
echo "Para ver logs en tiempo real:"
echo "  sudo tail -f /var/log/intradia/trading_loop.log"

