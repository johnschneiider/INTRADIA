#!/bin/bash
# Script para verificar y asegurar que los servicios estén corriendo

echo "=========================================="
echo "🔍 Verificando servicios de INTRADIA..."
echo "=========================================="
echo ""

# Servicios a verificar
SERVICES=(
    "intradia-save-ticks:Save Realtime Ticks"
    "intradia-trading-loop:Trading Loop"
    "intradia-daphne:Daphne (WebSocket)"
    "intradia-gunicorn:Gunicorn (Web Server)"
)

# Función para verificar y iniciar servicio
check_and_start_service() {
    local service_name=$1
    local display_name=$2
    
    echo "📋 Verificando: $display_name ($service_name)"
    
    if systemctl is-active --quiet "$service_name"; then
        echo "   ✅ Estado: ACTIVO (running)"
        systemctl show "$service_name" --property=ActiveState,SubState --value | head -1
    else
        echo "   ❌ Estado: INACTIVO (stopped)"
        echo "   🚀 Iniciando servicio..."
        systemctl start "$service_name"
        sleep 2
        
        if systemctl is-active --quiet "$service_name"; then
            echo "   ✅ Servicio iniciado exitosamente"
        else
            echo "   ⚠️  Error al iniciar servicio. Ver logs:"
            echo "      sudo journalctl -u $service_name -n 20"
        fi
    fi
    echo ""
}

# Verificar cada servicio
for service_info in "${SERVICES[@]}"; do
    IFS=':' read -r service_name display_name <<< "$service_info"
    check_and_start_service "$service_name" "$display_name"
done

echo "=========================================="
echo "📊 Resumen de servicios:"
echo "=========================================="
systemctl status intradia-save-ticks intradia-trading-loop intradia-daphne intradia-gunicorn --no-pager -l | head -30

echo ""
echo "=========================================="
echo "📜 Logs recientes:"
echo "=========================================="
echo ""
echo "💾 Save Ticks (últimas 5 líneas):"
sudo tail -5 /var/log/intradia/save_ticks.log 2>/dev/null || echo "   (sin logs aún)"
echo ""
echo "🔄 Trading Loop (últimas 5 líneas):"
sudo tail -5 /var/log/intradia/trading_loop.log 2>/dev/null || echo "   (sin logs aún)"
echo ""
echo "🌐 Daphne (últimas 5 líneas):"
sudo tail -5 /var/log/intradia/daphne.log 2>/dev/null || echo "   (sin logs aún)"
echo ""

