#!/bin/bash
# Script para verificar dónde están los logs reales de los servicios
# Uso: ./scripts/check_service_logs.sh

echo "=========================================="
echo "🔍 VERIFICANDO CONFIGURACIÓN DE LOGS"
echo "=========================================="
echo ""

# Verificar archivos de servicio systemd
echo "📋 Archivos de servicio systemd:"
echo ""
ls -la /etc/systemd/system/intradia-*.service 2>/dev/null || echo "No se encontraron archivos de servicio"
echo ""

# Ver configuración de cada servicio
for service in intradia-trading-loop intradia-daphne intradia-gunicorn intradia-save-ticks; do
    echo "=========================================="
    echo "📦 Servicio: $service"
    echo "=========================================="
    
    # Ver archivo de servicio
    if [ -f "/etc/systemd/system/${service}.service" ]; then
        echo ""
        echo "📄 Contenido del archivo de servicio:"
        cat /etc/systemd/system/${service}.service
        echo ""
    else
        echo "⚠️  Archivo de servicio no encontrado"
    fi
    
    # Ver estado del servicio
    echo "📊 Estado del servicio:"
    systemctl status ${service} --no-pager -l | head -20
    echo ""
    
    # Intentar ver logs reales (no solo systemd)
    echo "📝 Últimos 20 logs del servicio (incluyendo stdout/stderr):"
    journalctl -u ${service} -n 20 --no-pager | tail -20
    echo ""
    echo "---"
    echo ""
done

echo ""
echo "💡 Si no ves logs de la aplicación, los servicios pueden estar escribiendo a archivos."
echo "Buscando archivos de log posibles..."
echo ""

# Buscar archivos de log posibles
echo "📁 Buscando archivos de log en /var/log:"
find /var/log -name "*intradia*" -o -name "*trading*" 2>/dev/null | head -10
echo ""

echo "📁 Buscando archivos de log en el proyecto:"
find /var/www/intradia.com.co -name "*.log" 2>/dev/null | head -10

