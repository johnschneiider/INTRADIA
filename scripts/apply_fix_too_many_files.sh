#!/bin/bash
# Script simplificado para aplicar fix de "Too many open files"
# Uso: ./scripts/apply_fix_too_many_files.sh

echo "=========================================="
echo "🔧 SOLUCIONANDO: Too many open files"
echo "=========================================="
echo ""

# Verificar límites actuales
echo "📊 Límites actuales:"
echo "   - Límite del sistema: $(ulimit -n)"
echo "   - Límite hard: $(ulimit -Hn)"
echo ""

# Configurar límite permanente
echo "🔧 Configurando límite permanente..."
LIMITS_FILE="/etc/security/limits.conf"

# Agregar configuración si no existe
if ! grep -q "www-data.*nofile.*65536" "$LIMITS_FILE" 2>/dev/null; then
    echo "   📝 Agregando configuración para www-data y root..."
    sudo bash -c "cat >> $LIMITS_FILE << 'EOF'

# INTRADIA: Aumentar límite de archivos abiertos
www-data soft nofile 65536
www-data hard nofile 65536
root soft nofile 65536
root hard nofile 65536
EOF"
    echo "   ✅ Configuración agregada"
else
    echo "   ✅ Configuración ya existe"
fi

# Configurar systemd
echo ""
echo "🔧 Configurando límites en systemd..."
SYSTEMD_LIMITS_FILE="/etc/systemd/system.conf"

if ! grep -q "^DefaultLimitNOFILE=65536" "$SYSTEMD_LIMITS_FILE" 2>/dev/null; then
    # Verificar si existe [Manager]
    if grep -q "^\[Manager\]" "$SYSTEMD_LIMITS_FILE" 2>/dev/null; then
        # Agregar después de [Manager]
        sudo sed -i '/^\[Manager\]/a DefaultLimitNOFILE=65536' "$SYSTEMD_LIMITS_FILE"
    else
        # Agregar [Manager] y DefaultLimitNOFILE
        sudo bash -c "echo '[Manager]' >> $SYSTEMD_LIMITS_FILE"
        sudo bash -c "echo 'DefaultLimitNOFILE=65536' >> $SYSTEMD_LIMITS_FILE"
    fi
    echo "   ✅ DefaultLimitNOFILE agregado"
else
    echo "   ✅ DefaultLimitNOFILE ya existe"
fi

# Recargar systemd
echo ""
echo "🔄 Recargando configuración de systemd..."
sudo systemctl daemon-reload

# Aumentar límite en sesión actual
echo ""
echo "🔧 Aumentando límite en sesión actual..."
ulimit -n 65536 2>/dev/null || echo "   ⚠️  No se pudo aumentar límite en sesión actual (requiere reiniciar sesión)"

echo ""
echo "✅ Configuración aplicada"
echo ""
echo "📋 Reiniciando servicios..."
sudo systemctl restart intradia-trading-loop intradia-daphne intradia-save-ticks intradia-gunicorn

echo ""
echo "✅ Servicios reiniciados"
echo ""
echo "📊 Verificar que funcionó:"
echo "   sudo systemctl show intradia-trading-loop | grep LimitNOFILE"
echo "   (Debería mostrar LimitNOFILE=65536)"

