#!/bin/bash
# Script de despliegue para INTRADIA en VPS
# Ejecutar en la VPS después de clonar el repositorio

set -e

echo "🚀 INICIANDO DESPLIEGUE DE INTRADIA..."

# Variables
PROJECT_DIR="/var/www/intradia"
VENV_DIR="$PROJECT_DIR/venv"
DOMAIN="www.vitalmix.com.co"

# 1. Crear directorio si no existe
if [ ! -d "$PROJECT_DIR" ]; then
    echo "📁 Creando directorio $PROJECT_DIR..."
    sudo mkdir -p $PROJECT_DIR
    sudo chown $USER:$USER $PROJECT_DIR
fi

# 2. Ir al directorio
cd $PROJECT_DIR

# 3. Crear entorno virtual
if [ ! -d "$VENV_DIR" ]; then
    echo "🐍 Creando entorno virtual..."
    python3 -m venv venv
fi

# 4. Activar entorno virtual
echo "⚙️ Activando entorno virtual..."
source venv/bin/activate

# 5. Actualizar pip
echo "📦 Actualizando pip..."
pip install --upgrade pip

# 6. Instalar dependencias
echo "📚 Instalando dependencias..."
pip install -r requirements.txt

# 7. Crear directorios necesarios
echo "📁 Creando directorios..."
mkdir -p static media logs
chmod 755 static media logs

# 8. Recolectar archivos estáticos
echo "🗂️ Recolectando archivos estáticos..."
python manage.py collectstatic --noinput

# 9. Ejecutar migraciones
echo "🗄️ Ejecutando migraciones..."
python manage.py migrate --noinput

# 10. Copiar configuración de Nginx
echo "🌐 Configurando Nginx..."
sudo cp nginx_intradia.conf /etc/nginx/sites-available/intradia
sudo ln -sf /etc/nginx/sites-available/intradia /etc/nginx/sites-enabled/

# 11. Configurar Gunicorn systemd
echo "⚙️ Configurando servicio systemd..."
sudo cp systemd_intradia.service /etc/systemd/system/intradia.service
sudo systemctl daemon-reload
sudo systemctl enable intradia

# 12. Crear directorio de logs de gunicorn
echo "📝 Configurando logs..."
sudo mkdir -p /var/log/gunicorn
sudo chown www-data:www-data /var/log/gunicorn

# 13. Reiniciar servicios
echo "🔄 Reiniciando servicios..."
sudo systemctl restart nginx
sudo systemctl restart intradia

# 14. Verificar estado
echo "✅ Verificando estado..."
sudo systemctl status intradia --no-pager

echo ""
echo "🎉 DESPLIEGUE COMPLETADO!"
echo "📍 Dominio: https://$DOMAIN"
echo "🖥️  IP: 92.113.39.100"
echo ""
echo "📊 Comandos útiles:"
echo "  sudo systemctl status intradia"
echo "  sudo systemctl restart intradia"
echo "  sudo systemctl logs intradia -f"
echo "  sudo nginx -t"
echo "  sudo systemctl restart nginx"

