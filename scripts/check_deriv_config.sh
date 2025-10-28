#!/usr/bin/env bash
# Script para probar conexión con Deriv

echo "🔍 Verificando configuración Deriv..."

# Verificar que existe archivo .env
if [ ! -f .env ]; then
    echo "❌ Archivo .env no encontrado"
    echo "📝 Crea .env con tu DERIV_API_TOKEN"
    exit 1
fi

# Cargar variables de entorno
source .env

# Verificar token
if [ -z "$DERIV_API_TOKEN" ] || [ "$DERIV_API_TOKEN" = "tu_token_aqui" ]; then
    echo "❌ DERIV_API_TOKEN no configurado"
    echo "🔑 Ve a deriv.com → Settings → API Token → Generate"
    exit 1
fi

echo "✅ Token configurado: ${DERIV_API_TOKEN:0:10}..."
echo "🚀 Sistema listo para conectar con Deriv"
