#!/bin/bash
# Script para solucionar el error "Too many open files"
# Uso: ./scripts/fix_too_many_files.sh

echo "=========================================="
echo "🔧 SOLUCIONANDO: Too many open files"
echo "=========================================="
echo ""

# Verificar límites actuales
echo "📊 Límites actuales:"
echo "   - Límite del sistema: $(ulimit -n)"
echo "   - Límite del usuario: $(ulimit -Hn)"
echo ""

# Verificar cuántos archivos están abiertos
echo "📊 Archivos abiertos actualmente:"
echo "   - Por proceso: $(lsof 2>/dev/null | wc -l) archivos"
echo ""

# Aumentar límite temporalmente (para la sesión actual)
echo "🔧 Aumentando límite temporalmente..."
ulimit -n 65536
echo "   ✅ Nuevo límite: $(ulimit -n)"
echo ""

# Aumentar límite permanentemente (para todos los usuarios)
echo "🔧 Configurando límite permanente..."
LIMITS_FILE="/etc/security/limits.conf"

# Verificar si ya existe configuración
if grep -q "www-data.*nofile" "$LIMITS_FILE" 2>/dev/null; then
    echo "   ⚠️  Ya existe configuración para www-data en $LIMITS_FILE"
    echo "   📝 Verifica manualmente: sudo nano $LIMITS_FILE"
else
    echo "   📝 Agregando configuración para www-data..."
    sudo tee -a "$LIMITS_FILE" > /dev/null <<EOF

# INTRADIA: Aumentar límite de archivos abiertos
www-data soft nofile 65536
www-data hard nofile 65536
root soft nofile 65536
root hard nofile 65536
EOF
    echo "   ✅ Configuración agregada"
fi

# Configurar systemd limits
echo ""
echo "🔧 Configurando límites en systemd..."
SYSTEMD_LIMITS_FILE="/etc/systemd/system.conf"

if grep -q "^DefaultLimitNOFILE" "$SYSTEMD_LIMITS_FILE" 2>/dev/null; then
    echo "   ⚠️  Ya existe DefaultLimitNOFILE en systemd.conf"
    echo "   📝 Verifica: sudo nano $SYSTEMD_LIMITS_FILE"
else
    echo "   📝 Agregando DefaultLimitNOFILE=65536..."
    sudo sed -i '/^\[Manager\]/a DefaultLimitNOFILE=65536' "$SYSTEMD_LIMITS_FILE" 2>/dev/null || {
        echo "   ⚠️  No se pudo agregar automáticamente"
        echo "   📝 Agrega manualmente en $SYSTEMD_LIMITS_FILE:"
        echo "      [Manager]"
        echo "      DefaultLimitNOFILE=65536"
    }
fi

# Recargar systemd
echo ""
echo "🔄 Recargando configuración de systemd..."
sudo systemctl daemon-reload

echo ""
echo "✅ Configuración aplicada"
echo ""
echo "📋 PRÓXIMOS PASOS:"
echo "   1. Reiniciar los servicios:"
echo "      sudo systemctl restart intradia-trading-loop intradia-daphne intradia-save-ticks intradia-gunicorn"
echo ""
echo "   2. Verificar límites después del reinicio:"
echo "      sudo systemctl show intradia-trading-loop | grep LimitNOFILE"
echo ""

