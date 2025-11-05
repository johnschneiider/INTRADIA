#!/bin/bash

echo "🔧 Actualizando configuración de Nginx para WebSocket"
echo "======================================================"
echo ""

NGINX_CONFIG="/etc/nginx/sites-available/intradia"

if [ ! -f "$NGINX_CONFIG" ]; then
    echo "⚠️ Archivo de configuración no encontrado: $NGINX_CONFIG"
    echo "   Buscando archivos alternativos..."
    find /etc/nginx/sites-available -name "*intradia*" -o -name "*vitalmix*"
    exit 1
fi

echo "📋 Configuración actual de Nginx:"
grep -A 5 "location /" "$NGINX_CONFIG" | head -20
echo ""

# Verificar si ya tiene configuración de WebSocket
if grep -q "proxy_set_header Upgrade" "$NGINX_CONFIG"; then
    echo "✅ La configuración de WebSocket ya existe"
else
    echo "⚠️ No se encontró configuración de WebSocket"
fi

# Verificar si hay configuración específica para /ws/
if grep -q "location /ws/" "$NGINX_CONFIG"; then
    echo "✅ Configuración específica para /ws/ encontrada"
else
    echo "⚠️ No hay configuración específica para /ws/"
    echo ""
    echo "💡 Nota: Si el WebSocket no funciona, necesitas agregar:"
    echo ""
    echo "    location /ws/ {"
    echo "        proxy_pass http://127.0.0.1:8003;"
    echo "        proxy_http_version 1.1;"
    echo "        proxy_set_header Upgrade \$http_upgrade;"
    echo "        proxy_set_header Connection \"upgrade\";"
    echo "        proxy_set_header Host \$host;"
    echo "        proxy_set_header X-Real-IP \$remote_addr;"
    echo "        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;"
    echo "        proxy_set_header X-Forwarded-Proto \$scheme;"
    echo "        proxy_read_timeout 86400;"
    echo "    }"
    echo ""
fi

echo ""
echo "✅ Diagnóstico completado"
echo ""
echo "💡 Para aplicar cambios:"
echo "   1. Editar $NGINX_CONFIG"
echo "   2. sudo nginx -t  # Verificar sintaxis"
echo "   3. sudo systemctl reload nginx  # Aplicar cambios"

