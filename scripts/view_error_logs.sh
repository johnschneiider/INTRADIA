#!/bin/bash
# Script para ver errores en tiempo real
# Uso: ./scripts/view_error_logs.sh

echo "=========================================="
echo "🔍 MONITOREO DE ERRORES EN TIEMPO REAL"
echo "=========================================="
echo ""
echo "Presiona Ctrl+C para salir"
echo ""

# Ver logs de Gunicorn con errores
sudo tail -f /var/log/gunicorn/intradia_error.log 2>/dev/null | grep --line-buffered -i -E "error|ERROR|exception|EXCEPTION|traceback|Traceback|database|Database|corrupt|Corrupt|500" || \
sudo tail -f /var/log/gunicorn/intradia_error.log 2>/dev/null

