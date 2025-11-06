#!/bin/bash
# Monitorear solo el Trading Loop (el más importante)
# Uso: ./scripts/monitor_trading_loop.sh

echo "🤖 Monitoreando Trading Loop..."
echo "Presiona Ctrl+C para salir"
echo ""

sudo journalctl -u intradia-trading-loop -f

