#!/bin/bash
# Script simplificado para monitorear solo errores
# Uso: ./scripts/monitor_errors_only.sh

echo "🚨 Monitoreando SOLO errores y críticos..."
echo "Presiona Ctrl+C para salir"
echo ""

# Crear directorios si no existen
sudo mkdir -p /var/log/intradia /var/log/gunicorn

# Monitorear archivos de log filtrando solo errores
sudo tail -f /var/log/intradia/trading_loop*.log /var/log/intradia/daphne*.log \
    /var/log/intradia/save_ticks*.log /var/log/gunicorn/intradia*.log 2>/dev/null \
    | grep -i --color=always --line-buffered -E "error|ERROR|fail|FAIL|exception|EXCEPTION|critical|CRITICAL|timeout|TIMEOUT|rejected|REJECTED|CRÍTICO|❌|⚠️|Broken|connection|refused|502|503|504|500"

