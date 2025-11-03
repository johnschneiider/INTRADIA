# Guía de Despliegue en VPS - INTRADIA

## Paso 1: Arreglar la estructura de carpetas

```bash
# Estás en /var/www/intradia.com.co/intradia.com.co
cd /var/www/intradia.com.co
mv intradia.com.co/* .
mv intradia.com.co/.git* . 2>/dev/null || true
rmdir intradia.com.co
ls -la  # Deberías ver manage.py, requirements.txt, etc.
```

## Paso 2: Crear entorno virtual e instalar dependencias

```bash
cd /var/www/intradia.com.co
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Paso 3: Crear archivo .env

```bash
cd /var/www/intradia.com.co
nano .env
```

Contenido del `.env`:
```
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=vitalmix.com.co,www.vitalmix.com.co
DJANGO_CSRF_TRUSTED_ORIGINS=https://vitalmix.com.co,https://www.vitalmix.com.co
SECRET_KEY=tu-secret-key-aqui-genera-uno-nuevo-si-es-posible
```

**Generar SECRET_KEY nuevo:**
```bash
python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

## Paso 4: Aplicar migraciones y recopilar estáticos

```bash
cd /var/www/intradia.com.co
source venv/bin/activate

# Crear directorio de logs
mkdir -p /var/log/gunicorn
mkdir -p /var/log/intradia

# Aplicar migraciones
python manage.py migrate

# Crear superusuario (opcional, para admin)
# python manage.py createsuperuser

# Recopilar archivos estáticos
python manage.py collectstatic --noinput
```

## Paso 5: Configurar Nginx

```bash
# Copiar configuración de Nginx
sudo cp /var/www/intradia.com.co/nginx_intradia.conf /etc/nginx/sites-available/intradia

# Editar la configuración para ajustar rutas
sudo nano /etc/nginx/sites-available/intradia
```

**Ajustar las rutas en el archivo:**
- Cambiar `/var/www/intradia/` por `/var/www/intradia.com.co/`
- El puerto 8001 ya está configurado (correcto)

```bash
# Activar el sitio
sudo ln -s /etc/nginx/sites-available/intradia /etc/nginx/sites-enabled/

# Probar configuración
sudo nginx -t

# Recargar Nginx
sudo systemctl reload nginx
```

## Paso 6: Crear servicios systemd

### 6.1 Servicio Gunicorn (servidor web)

```bash
sudo nano /etc/systemd/system/intradia-gunicorn.service
```

Contenido:
```ini
[Unit]
Description=INTRADIA Gunicorn Web Server
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/var/www/intradia.com.co
Environment="PATH=/var/www/intradia.com.co/venv/bin"
Environment="DJANGO_DEBUG=0"
ExecStart=/var/www/intradia.com.co/venv/bin/gunicorn \
    --config /var/www/intradia.com.co/gunicorn_config.py \
    --pid /var/run/intradia-gunicorn.pid \
    config.wsgi:application
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 6.2 Servicio Trading Loop

```bash
sudo nano /etc/systemd/system/intradia-trading-loop.service
```

Contenido:
```ini
[Unit]
Description=INTRADIA Trading Loop
After=network.target intradia-gunicorn.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/var/www/intradia.com.co
Environment="PATH=/var/www/intradia.com.co/venv/bin"
Environment="DJANGO_DEBUG=0"
ExecStart=/var/www/intradia.com.co/venv/bin/python manage.py trading_loop
Restart=always
RestartSec=10
StandardOutput=append:/var/log/intradia/trading_loop.log
StandardError=append:/var/log/intradia/trading_loop_error.log

[Install]
WantedBy=multi-user.target
```

### 6.3 Servicio Daphne (WebSocket para ticks en tiempo real)

```bash
sudo nano /etc/systemd/system/intradia-daphne.service
```

Contenido:
```ini
[Unit]
Description=INTRADIA Daphne WebSocket Server
After=network.target intradia-gunicorn.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/var/www/intradia.com.co
Environment="PATH=/var/www/intradia.com.co/venv/bin"
Environment="DJANGO_DEBUG=0"
ExecStart=/var/www/intradia.com.co/venv/bin/daphne -b 127.0.0.1 -p 8002 config.asgi:application
Restart=always
RestartSec=10
StandardOutput=append:/var/log/intradia/daphne.log
StandardError=append:/var/log/intradia/daphne_error.log

[Install]
WantedBy=multi-user.target
```

## Paso 7: Ajustar permisos

```bash
cd /var/www/intradia.com.co
sudo chown -R www-data:www-data /var/www/intradia.com.co
sudo chmod -R 755 /var/www/intradia.com.co
sudo chmod -R 775 /var/www/intradia.com.co/media  # Si existe
sudo chmod -R 775 /var/www/intradia.com.co/staticfiles  # Si existe
```

## Paso 8: Habilitar y iniciar servicios

```bash
# Recargar systemd
sudo systemctl daemon-reload

# Habilitar servicios (inicio automático)
sudo systemctl enable intradia-gunicorn
sudo systemctl enable intradia-trading-loop
sudo systemctl enable intradia-daphne

# Iniciar servicios
sudo systemctl start intradia-gunicorn
sudo systemctl start intradia-trading-loop
sudo systemctl start intradia-daphne

# Verificar estado
sudo systemctl status intradia-gunicorn
sudo systemctl status intradia-trading-loop
sudo systemctl status intradia-daphne
```

## Paso 9: Verificar logs

```bash
# Logs de Gunicorn
sudo tail -f /var/log/gunicorn/intradia_error.log
sudo tail -f /var/log/gunicorn/intradia_access.log

# Logs de servicios
sudo journalctl -u intradia-gunicorn -f
sudo journalctl -u intradia-trading-loop -f
sudo journalctl -u intradia-daphne -f

# Logs personalizados
sudo tail -f /var/log/intradia/trading_loop.log
sudo tail -f /var/log/intradia/daphne.log
```

## Paso 10: Configurar el token de API de Deriv

**IMPORTANTE:** Necesitas configurar el token de API de Deriv en la base de datos:

```bash
cd /var/www/intradia.com.co
source venv/bin/activate
python manage.py shell
```

En el shell de Django:
```python
from trading_bot.models import DerivAPIConfig
# Obtener o crear la configuración
config, created = DerivAPIConfig.objects.get_or_create(is_active=True)
config.api_token = 'jynzRtypyTiwyLX'  # Tu token actual
config.is_demo = False
config.app_id = '1089'
config.save()
print(f"Configuración {'creada' if created else 'actualizada'}")
exit()
```

## Comandos útiles

```bash
# Reiniciar todos los servicios
sudo systemctl restart intradia-gunicorn
sudo systemctl restart intradia-trading-loop
sudo systemctl restart intradia-daphne

# Detener servicios
sudo systemctl stop intradia-gunicorn
sudo systemctl stop intradia-trading-loop
sudo systemctl stop intradia-daphne

# Ver estado de todos
sudo systemctl status intradia-gunicorn intradia-trading-loop intradia-daphne

# Ver logs en tiempo real
sudo journalctl -u intradia-* -f
```

## Notas importantes

1. **Puerto 8001**: Gunicorn usa el puerto 8001 para no interferir con otros proyectos (predicta.com.co probablemente usa 8000)
2. **Puerto 8002**: Daphne usa el puerto 8002 para WebSockets
3. **Base de datos**: El proyecto usa SQLite por defecto (`db.sqlite3`). Si quieres usar PostgreSQL, deberás configurarlo.
4. **Archivos estáticos**: Se recopilan en `/var/www/intradia.com.co/staticfiles/`
5. **Logs**: Los logs están en `/var/log/intradia/` y `/var/log/gunicorn/`

## Verificar que todo funciona

1. **Servidor web**: Visita `http://vitalmix.com.co` (o `https://` si tienes SSL)
2. **Trading loop**: Verifica con `sudo journalctl -u intradia-trading-loop -n 50`
3. **Daphne**: Verifica con `sudo journalctl -u intradia-daphne -n 50`

## Solución de problemas

Si algún servicio no inicia:
```bash
# Ver errores detallados
sudo journalctl -u intradia-gunicorn -n 100 --no-pager
sudo journalctl -u intradia-trading-loop -n 100 --no-pager
sudo journalctl -u intradia-daphne -n 100 --no-pager
```

Si hay problemas de permisos:
```bash
sudo chown -R www-data:www-data /var/www/intradia.com.co
sudo chmod -R 755 /var/www/intradia.com.co
```

