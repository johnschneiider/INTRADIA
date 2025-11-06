#!/bin/bash
# Script para monitorear todos los logs del sistema en tiempo real
# Uso: ./scripts/monitor_all_logs.sh [--errors-only]

set -e

ERRORS_ONLY=false

if [ "$1" == "--errors-only" ]; then
    ERRORS_ONLY=true
fi

echo "=========================================="
echo "🔍 MONITOREO DE LOGS EN TIEMPO REAL"
echo "=========================================="
echo ""
echo "Servicios monitoreados:"
echo "  - intradia-trading-loop"
echo "  - intradia-daphne"
echo "  - intradia-gunicorn"
echo "  - intradia-save-ticks"
echo ""

if [ "$ERRORS_ONLY" == "true" ]; then
    echo "⚠️  Modo: Solo errores/críticos"
    echo ""
    echo "Filtrando por: error|ERROR|fail|FAIL|exception|EXCEPTION|critical|CRITICAL|timeout|TIMEOUT|rejected|REJECTED"
    echo ""
    echo "=========================================="
    echo ""
    
    # Monitorear todos los servicios filtrando solo errores
    sudo journalctl -u intradia-trading-loop -u intradia-daphne -u intradia-gunicorn -u intradia-save-ticks -f \
        | grep -i --line-buffered -E "error|ERROR|fail|FAIL|exception|EXCEPTION|critical|CRITICAL|timeout|TIMEOUT|rejected|REJECTED|CRÍTICO|❌|⚠️"
else
    echo "📊 Modo: Todos los logs (sin filtros)"
    echo ""
    echo "=========================================="
    echo ""
    
    # Monitorear todos los servicios sin filtros
    sudo journalctl -u intradia-trading-loop -u intradia-daphne -u intradia-gunicorn -u intradia-save-ticks -f
fi

