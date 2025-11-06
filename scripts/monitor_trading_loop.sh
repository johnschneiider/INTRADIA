#!/bin/bash
# Monitorear solo el Trading Loop (el más importante)
# Uso: ./scripts/monitor_trading_loop.sh

echo "🤖 Monitoreando Trading Loop..."
echo "Presiona Ctrl+C para salir"
echo ""

# Crear directorio si no existe
sudo mkdir -p /var/log/intradia

# Monitorear logs del trading loop
sudo tail -f /var/log/intradia/trading_loop.log /var/log/intradia/trading_loop_error.log 2>/dev/null

