#!/bin/bash
# Despliegue automatizado de INTRADIA en VPS (sin interferir con otros proyectos)
# Uso: sudo bash deploy.sh

set -euo pipefail

echo "\n🚀 Iniciando despliegue de INTRADIA...\n"

# =============================
# Variables configurables
# =============================
PROJECT_DIR="/var/www/intradia.com.co"
PROJECT_NAME="intradia"
DOMAIN="vitalmix.com.co"
DOMAIN_WWW="www.vitalmix.com.co"
PYTHON_BIN="python3"
GUNICORN_PORT=8001       # No interferir con otros proyectos (p.ej., 8000)
DAPHNE_PORT=8002         # WebSocket

VENV_DIR="$PROJECT_DIR/venv"
NGINX_SITE="/etc/nginx/sites-available/${PROJECT_NAME}"
NGINX_SITE_LINK="/etc/nginx/sites-enabled/${PROJECT_NAME}"
SYSTEMD_GUNICORN="/etc/systemd/system/${PROJECT_NAME}-gunicorn.service"
SYSTEMD_LOOP="/etc/systemd/system/${PROJECT_NAME}-trading-loop.service"
SYSTEMD_DAPHNE="/etc/systemd/system/${PROJECT_NAME}-daphne.service"

# =============================
# Prechequeos
# =============================
if [ "$(id -u)" -ne 0 ]; then
  echo "❌ Ejecuta este script como root: sudo bash deploy.sh"; exit 1;
fi

command -v $PYTHON_BIN >/dev/null 2>&1 || { echo "❌ No se encontró $PYTHON_BIN"; exit 1; }

mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# Si el repositorio quedó anidado (intradia.com.co/intradia.com.co), desanidar
if [ -d "$PROJECT_DIR/intradia.com.co" ]; then
  echo "📦 Reorganizando contenido (desanidar carpeta)..."
  rsync -a "$PROJECT_DIR/intradia.com.co/" "$PROJECT_DIR/"
  rm -rf "$PROJECT_DIR/intradia.com.co"
fi

chown -R www-data:www-data "$PROJECT_DIR"
chmod -R 755 "$PROJECT_DIR"

# =============================
# Entorno virtual y dependencias
# =============================
if [ ! -d "$VENV_DIR" ]; then
  echo "🐍 Creando entorno virtual..."
  $PYTHON_BIN -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

# Instalar websocket-client si falta (requerido por deriv_client)
pip install websocket-client==1.7.0

# =============================
# Variables de entorno y Django
# =============================
touch .env
if ! grep -q "DJANGO_ALLOWED_HOSTS" .env 2>/dev/null; then
  cat >> .env <<EOF
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=${DOMAIN},${DOMAIN_WWW}
DJANGO_CSRF_TRUSTED_ORIGINS=https://${DOMAIN},https://${DOMAIN_WWW}
EOF
fi

mkdir -p /var/log/gunicorn /var/log/intradia "$PROJECT_DIR/staticfiles" "$PROJECT_DIR/media" "$PROJECT_DIR/static"
chown -R www-data:www-data /var/log/gunicorn /var/log/intradia "$PROJECT_DIR/staticfiles" "$PROJECT_DIR/media" "$PROJECT_DIR/static"

echo "🗄️ Migraciones y estáticos..."
python manage.py makemigrations --noinput || true
python manage.py migrate --noinput
python manage.py collectstatic --noinput

# =============================
# Nginx (solo para este dominio)
# =============================
echo "🌐 Configurando Nginx para ${DOMAIN}..."
cat > "$NGINX_SITE" <<NGINX
server {
    listen 80;
    server_name ${DOMAIN} ${DOMAIN_WWW};

    client_max_body_size 10M;

    # Archivos estáticos
    location /static/ {
        alias ${PROJECT_DIR}/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias ${PROJECT_DIR}/media/;
        expires 30d;
        add_header Cache-Control "public";
    }

    # Proxy a Gunicorn
    location / {
        proxy_pass http://127.0.0.1:${GUNICORN_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_redirect off;

        # WebSocket (por si la app lo usa en /)
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINX

ln -sf "$NGINX_SITE" "$NGINX_SITE_LINK"
nginx -t
systemctl reload nginx

# =============================
# Servicios systemd (solo de INTRADIA)
# =============================
echo "⚙️ Configurando servicios systemd..."

# Gunicorn
cat > "$SYSTEMD_GUNICORN" <<UNIT
[Unit]
Description=INTRADIA Gunicorn Web Server
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=${PROJECT_DIR}
Environment="PATH=${VENV_DIR}/bin"
Environment="DJANGO_DEBUG=0"
ExecStart=${VENV_DIR}/bin/gunicorn \
  --config ${PROJECT_DIR}/gunicorn_config.py \
  --bind 127.0.0.1:${GUNICORN_PORT} \
  config.wsgi:application
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

# Trading loop
cat > "$SYSTEMD_LOOP" <<UNIT
[Unit]
Description=INTRADIA Trading Loop
After=network.target ${PROJECT_NAME}-gunicorn.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=${PROJECT_DIR}
Environment="PATH=${VENV_DIR}/bin"
Environment="DJANGO_DEBUG=0"
ExecStart=${VENV_DIR}/bin/python manage.py trading_loop
Restart=always
RestartSec=10
StandardOutput=append:/var/log/intradia/trading_loop.log
StandardError=append:/var/log/intradia/trading_loop_error.log

[Install]
WantedBy=multi-user.target
UNIT

# Daphne (WebSockets) - opcional
cat > "$SYSTEMD_DAPHNE" <<UNIT
[Unit]
Description=INTRADIA Daphne WebSocket Server
After=network.target ${PROJECT_NAME}-gunicorn.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=${PROJECT_DIR}
Environment="PATH=${VENV_DIR}/bin"
Environment="DJANGO_DEBUG=0"
ExecStart=${VENV_DIR}/bin/daphne -b 127.0.0.1 -p ${DAPHNE_PORT} config.asgi:application
Restart=always
RestartSec=10
StandardOutput=append:/var/log/intradia/daphne.log
StandardError=append:/var/log/intradia/daphne_error.log

[Install]
WantedBy=multi-user.target
UNIT

# Configurar permisos sudo para www-data (reiniciar servicios sin contraseña)
echo "🔐 Configurando permisos sudo para administración de servicios..."
SUDOERS_FILE="/etc/sudoers.d/${PROJECT_NAME}-services"
cat > "$SUDOERS_FILE" <<SUDOERS
# Permisos para www-data para administrar servicios de ${PROJECT_NAME}
www-data ALL=(ALL) NOPASSWD: /bin/systemctl restart ${PROJECT_NAME}-gunicorn.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl restart ${PROJECT_NAME}-trading-loop.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl restart ${PROJECT_NAME}-daphne.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl status ${PROJECT_NAME}-gunicorn.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl status ${PROJECT_NAME}-trading-loop.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl status ${PROJECT_NAME}-daphne.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl is-active ${PROJECT_NAME}-gunicorn.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl is-active ${PROJECT_NAME}-trading-loop.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl is-active ${PROJECT_NAME}-daphne.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl show ${PROJECT_NAME}-gunicorn.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl show ${PROJECT_NAME}-trading-loop.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl show ${PROJECT_NAME}-daphne.service
SUDOERS
chmod 440 "$SUDOERS_FILE"

systemctl daemon-reload
systemctl enable ${PROJECT_NAME}-gunicorn ${PROJECT_NAME}-trading-loop ${PROJECT_NAME}-daphne
systemctl restart ${PROJECT_NAME}-gunicorn
systemctl restart ${PROJECT_NAME}-trading-loop
systemctl restart ${PROJECT_NAME}-daphne

echo "\n✅ Despliegue completado"
echo "🌍 Dominio: http://${DOMAIN} (o https si tienes SSL)"
echo "🧰 Servicios: ${PROJECT_NAME}-gunicorn, ${PROJECT_NAME}-trading-loop, ${PROJECT_NAME}-daphne"
echo "📜 Logs: /var/log/intradia/ y /var/log/gunicorn/"

exit 0

