#!/bin/bash
# Script para monitorear todos los logs del sistema en tiempo real
# Los logs están en archivos, no en journalctl
# Uso: ./scripts/monitor_all_logs.sh [--errors-only]

set -e

ERRORS_ONLY=false

if [ "$1" == "--errors-only" ]; then
    ERRORS_ONLY=true
fi

# Crear directorios de log si no existen
sudo mkdir -p /var/log/intradia
sudo mkdir -p /var/log/gunicorn
sudo touch /var/log/intradia/trading_loop.log /var/log/intradia/trading_loop_error.log
sudo touch /var/log/intradia/daphne.log /var/log/intradia/daphne_error.log
sudo touch /var/log/intradia/save_ticks.log /var/log/intradia/save_ticks_error.log
sudo touch /var/log/gunicorn/intradia_error.log /var/log/gunicorn/intradia_access.log
sudo chmod 644 /var/log/intradia/*.log /var/log/gunicorn/*.log 2>/dev/null || true

echo "=========================================="
echo "🔍 MONITOREO DE LOGS EN TIEMPO REAL"
echo "=========================================="
echo ""
echo "Servicios monitoreados:"
echo "  - Trading Loop: /var/log/intradia/trading_loop.log"
echo "  - Daphne: /var/log/intradia/daphne.log"
echo "  - Gunicorn: /var/log/gunicorn/intradia_error.log"
echo "  - Save Ticks: /var/log/intradia/save_ticks.log"
echo ""

if [ "$ERRORS_ONLY" == "true" ]; then
    echo "⚠️  Modo: Solo errores/críticos"
    echo ""
    echo "Filtrando por: error|ERROR|fail|FAIL|exception|EXCEPTION|critical|CRITICAL|timeout|TIMEOUT|rejected|REJECTED"
    echo ""
    echo "=========================================="
    echo ""
    
    # Monitorear archivos de log filtrando solo errores
    sudo tail -f /var/log/intradia/trading_loop*.log /var/log/intradia/daphne*.log \
        /var/log/intradia/save_ticks*.log /var/log/gunicorn/intradia*.log 2>/dev/null \
        | grep -i --line-buffered -E "error|ERROR|fail|FAIL|exception|EXCEPTION|critical|CRITICAL|timeout|TIMEOUT|rejected|REJECTED|CRÍTICO|❌|⚠️"
else
    echo "📊 Modo: Todos los logs (sin filtros)"
    echo ""
    echo "=========================================="
    echo ""
    
    # Monitorear todos los archivos de log sin filtros
    sudo tail -f /var/log/intradia/trading_loop*.log /var/log/intradia/daphne*.log \
        /var/log/intradia/save_ticks*.log /var/log/gunicorn/intradia*.log 2>/dev/null
fi

