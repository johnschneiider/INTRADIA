#!/bin/bash

echo "🔍 Diagnóstico de Balance y Daphne"
echo "===================================="
echo ""

# 1. Verificar estado de Daphne
echo "📊 1. Estado de Daphne:"
sudo systemctl status intradia-daphne --no-pager -l | head -20
echo ""

# 2. Verificar logs recientes de Daphne
echo "📋 2. Últimos logs de Daphne (últimas 30 líneas):"
sudo journalctl -u intradia-daphne -n 30 --no-pager | tail -30
echo ""

# 3. Verificar si Daphne está escuchando en el puerto
echo "🔌 3. Puertos en los que Daphne debería estar escuchando:"
echo "   - Puerto 8003 (Daphne ASGI):"
sudo netstat -tlnp | grep 8003 || echo "   ⚠️ No se encontró proceso escuchando en 8003"
echo ""

# 4. Verificar configuración de Nginx para WebSocket
echo "🌐 4. Configuración de Nginx para WebSocket:"
if [ -f /etc/nginx/sites-available/intradia ]; then
    echo "   Verificando configuración de WebSocket en Nginx:"
    grep -A 5 "location /ws/" /etc/nginx/sites-available/intradia || echo "   ⚠️ No se encontró configuración de WebSocket"
else
    echo "   ⚠️ Archivo de configuración de Nginx no encontrado"
fi
echo ""

# 5. Verificar logs de Gunicorn (balance API)
echo "📋 5. Últimos logs de Gunicorn (balance API, últimas 20 líneas):"
sudo journalctl -u intradia-gunicorn -n 20 --no-pager | tail -20
echo ""

# 6. Verificar configuración de API en la base de datos
echo "🔑 6. Verificando configuración de API en la base de datos:"
cd /var/www/intradia.com.co
source venv/bin/activate
python manage.py shell << 'EOF'
from trading_bot.models import DerivAPIConfig
configs = DerivAPIConfig.objects.all()
print(f"Total configuraciones: {configs.count()}")
for cfg in configs:
    print(f"  - ID: {cfg.id}, is_active: {cfg.is_active}, is_demo: {cfg.is_demo}, app_id: {cfg.app_id}, token: {cfg.api_token[:10] if cfg.api_token else 'None'}...")
active = DerivAPIConfig.objects.filter(is_active=True).first()
if active:
    print(f"\n✅ Configuración activa encontrada:")
    print(f"   - Token: {active.api_token[:15] if active.api_token else 'None'}...")
    print(f"   - is_demo: {active.is_demo}")
    print(f"   - app_id: {active.app_id}")
else:
    print("\n⚠️ No hay configuración activa")
EOF
echo ""

# 7. Probar conexión HTTP directa al endpoint de balance
echo "🌐 7. Probando endpoint de balance (HTTP):"
echo "   Haciendo petición a http://localhost:8002/engine/balance/"
curl -s -H "Accept: application/json" http://localhost:8002/engine/balance/ | python3 -m json.tool 2>/dev/null || echo "   ⚠️ Error al obtener balance"
echo ""

# 8. Verificar logs de errores de Django
echo "📋 8. Verificando logs de errores de Django:"
if [ -f /var/log/intradia/error.log ]; then
    tail -20 /var/log/intradia/error.log
else
    echo "   ⚠️ Archivo de log de errores no encontrado"
fi
echo ""

# 9. Verificar procesos Python relacionados
echo "🐍 9. Procesos Python relacionados:"
ps aux | grep -E "(daphne|gunicorn|trading_loop|save_realtime)" | grep -v grep
echo ""

# 10. Verificar conexión WebSocket de Deriv (simulación)
echo "🔌 10. Verificando capacidad de conexión WebSocket:"
cd /var/www/intradia.com.co
source venv/bin/activate
python3 << 'EOF'
import sys
try:
    import websocket
    print("   ✅ Módulo websocket disponible")
    
    # Intentar crear un cliente WebSocket (sin conectar realmente)
    try:
        ws = websocket.WebSocketApp("wss://ws.derivws.com/websockets/v3?app_id=1089")
        print("   ✅ WebSocketApp puede ser creado")
    except Exception as e:
        print(f"   ❌ Error creando WebSocketApp: {e}")
        
except ImportError as e:
    print(f"   ❌ Módulo websocket no disponible: {e}")
    sys.exit(1)
EOF
echo ""

echo "✅ Diagnóstico completado"
echo ""
echo "💡 Recomendaciones:"
echo "   1. Si Daphne no está corriendo: sudo systemctl start intradia-daphne"
echo "   2. Si hay errores en los logs, revisarlos con: sudo journalctl -u intradia-daphne -f"
echo "   3. Si el balance sigue en 0, verificar que DerivAPIConfig esté activo y el token sea válido"
echo "   4. Verificar que Nginx esté configurado correctamente para WebSocket"

