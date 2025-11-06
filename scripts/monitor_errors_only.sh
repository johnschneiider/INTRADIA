#!/bin/bash
# Script simplificado para monitorear solo errores
# Uso: ./scripts/monitor_errors_only.sh

echo "🚨 Monitoreando SOLO errores y críticos..."
echo "Presiona Ctrl+C para salir"
echo ""

sudo journalctl -u intradia-trading-loop -u intradia-daphne -u intradia-gunicorn -u intradia-save-ticks -f \
    | grep -i --color=always --line-buffered -E "error|ERROR|fail|FAIL|exception|EXCEPTION|critical|CRITICAL|timeout|TIMEOUT|rejected|REJECTED|CRÍTICO|❌|⚠️|Broken|connection|refused|502|503|504|500"

