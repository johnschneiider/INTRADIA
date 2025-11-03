# 🚀 GUÍA DE DESPLIEGUE - INTRADIA

## 📋 Configuración Actual

- **Dominio:** www.vitalmix.com.co
- **IP VPS:** 92.113.39.100
- **Puerto Gunicorn:** 8000 (interno)
- **Puerto Nginx:** 80 (público)

---

## 🔧 CONFIGURACIÓN PRE-DESPLIEGUE

### 1. Settings Actualizado

El archivo `config/settings.py` ya tiene configurados los allowed hosts:

```python
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', '*').split(',')
```

Para producción, establecer variable de entorno:
```bash
export DJANGO_ALLOWED_HOSTS="vitalmix.com.co,www.vitalmix.com.co,92.113.39.100"
```

### 2. Archivos Creados

- ✅ `.gitignore` - Archivos a ignorar en git
- ✅ `gunicorn_config.py` - Configuración de Gunicorn
- ✅ `nginx_intradia.conf` - Configuración de Nginx
- ✅ `systemd_intradia.service` - Servicio systemd
- ✅ `deploy.sh` - Script de despliegue automático
- ✅ `deploy_local.sh` - Script para desarrollo local

---

## 📤 SUBIR A GITHUB

### Paso 1: Inicializar Git

```bash
# Inicializar repositorio
git init

# Configurar usuario (opcional)
git config user.name "John Schneider"
git config user.email "tu-email@example.com"

# Agregar origen
git remote add origin https://github.com/johnschneiider/INTRADIA.git
```

### Paso 2: Agregar y Commit

```bash
# Agregar todos los archivos (respeta .gitignore)
git add .

# Commit inicial
git commit -m "Initial commit: Sistema INTRADIA v2.0 con filtros bayesianos optimizados"

# Subir a GitHub
git branch -M main
git push -u origin main
```

---

## 🖥️ DESPLIEGUE EN VPS

### Conexión SSH

```bash
ssh root@92.113.39.100
# o
ssh tu_usuario@92.113.39.100
```

### Paso 1: Clonar Repositorio

```bash
# Instalar git si no está instalado
sudo apt update
sudo apt install git nginx python3-pip python3-venv postgresql -y

# Clonar repositorio
cd /var/www
sudo git clone https://github.com/johnschneiider/INTRADIA.git intradia

# Permisos
sudo chown -R $USER:$USER /var/www/intradia
cd /var/www/intradia
```

### Paso 2: Ejecutar Script de Despliegue

```bash
# Dar permisos de ejecución
chmod +x deploy.sh

# Ejecutar despliegue
./deploy.sh
```

### Paso 3: Configurar Variables de Entorno

```bash
# Crear archivo .env
nano /var/www/intradia/.env
```

Contenido:
```env
DEBUG=False
SECRET_KEY=tu-secret-key-aqui
DJANGO_ALLOWED_HOSTS=vitalmix.com.co,www.vitalmix.com.co,92.113.39.100

# Base de datos
POSTGRES_HOST=localhost
POSTGRES_DB=intradia
POSTGRES_USER=intradia
POSTGRES_PASSWORD=tu-password

# Deriv API
DERIV_API_TOKEN=tu-token-aqui
DERIV_ACCOUNT_ID=tu-account-id

# Celery (opcional)
CELERY_BROKER_URL=redis://localhost:6379/0
```

---

## 🔧 CONFIGURACIÓN DE NGINX

### Verificar configuración:

```bash
# Probar configuración de Nginx
sudo nginx -t

# Si hay errores, revisar
cat /etc/nginx/sites-available/intradia
```

### Reiniciar Nginx:

```bash
sudo systemctl restart nginx
sudo systemctl status nginx
```

---

## 🎮 GESTIÓN DEL SERVICIO

### Comandos Útiles:

```bash
# Ver estado del servicio
sudo systemctl status intradia

# Iniciar servicio
sudo systemctl start intradia

# Reiniciar servicio
sudo systemctl restart intradia

# Ver logs
sudo journalctl -u intradia -f

# Ver logs de Gunicorn
tail -f /var/log/gunicorn/intradia_error.log

# Ver logs de acceso
tail -f /var/log/gunicorn/intradia_access.log
```

---

## 🗄️ CONFIGURACIÓN DE BASE DE DATOS (PostgreSQL)

```bash
# Crear base de datos
sudo -u postgres psql

# Dentro de psql:
CREATE DATABASE intradia;
CREATE USER intradia WITH PASSWORD 'tu-password';
GRANT ALL PRIVILEGES ON DATABASE intradia TO intradia;
\q
```

---

## 🔐 CERTIFICADO SSL (Opcional pero Recomendado)

### Usando Certbot:

```bash
# Instalar certbot
sudo apt install certbot python3-certbot-nginx -y

# Obtener certificado
sudo certbot --nginx -d vitalmix.com.co -d www.vitalmix.com.co

# Renovación automática
sudo certbot renew --dry-run
```

Esto actualizará automáticamente la configuración de Nginx para HTTPS.

---

## 🚨 TROUBLESHOOTING

### Problema: Error 502 Bad Gateway

**Solución:**
```bash
# Verificar que Gunicorn está corriendo
sudo systemctl status intradia

# Verificar logs
sudo journalctl -u intradia -n 50

# Reiniciar servicio
sudo systemctl restart intradia
```

### Problema: Error 403 Forbidden

**Solución:**
```bash
# Verificar permisos
sudo chown -R www-data:www-data /var/www/intradia
sudo chmod -R 755 /var/www/intradia
```

### Problema: Static files no cargan

**Solución:**
```bash
# Recolectar estáticos nuevamente
cd /var/www/intradia
source venv/bin/activate
python manage.py collectstatic --noinput

# Verificar permisos
sudo chown -R www-data:www-data /var/www/intradia/static
```

---

## 📊 MONITOREO

### Ver Métricas en Tiempo Real:

```bash
# Logs del sistema
tail -f /var/log/gunicorn/intradia_access.log

# Estado del servicio
watch -n 5 'sudo systemctl status intradia'

# Memoria y CPU
htop
```

### Acceder al Admin:

```
http://www.vitalmix.com.co/admin/
Usuario: admin
Password: (configurar en deploy)
```

---

## 🔄 ACTUALIZAR CÓDIGO EN VPS

```bash
cd /var/www/intradia

# Obtener últimos cambios
git pull origin main

# Activar entorno virtual
source venv/bin/activate

# Instalar nuevas dependencias
pip install -r requirements.txt

# Migraciones
python manage.py migrate

# Recolectar estáticos
python manage.py collectstatic --noinput

# Reiniciar servicio
sudo systemctl restart intradia
```

---

## ✅ CHECKLIST DE DESPLIEGUE

- [ ] Repositorio subido a GitHub
- [ ] VPS con Python3, Nginx, PostgreSQL instalados
- [ ] Repositorio clonado en `/var/www/intradia`
- [ ] Variables de entorno configuradas en `.env`
- [ ] Base de datos PostgreSQL creada
- [ ] Migraciones ejecutadas
- [ ] Archivos estáticos recolectados
- [ ] Nginx configurado y funcionando
- [ ] Servicio systemd activo
- [ ] Dominio configurado en DNS
- [ ] SSL instalado (opcional pero recomendado)
- [ ] Acceso al admin verificado

---

## 📞 SOPORTE

Si hay problemas durante el despliegue, verificar:

1. **Logs de Gunicorn:** `/var/log/gunicorn/intradia_error.log`
2. **Logs del sistema:** `sudo journalctl -u intradia`
3. **Logs de Nginx:** `sudo tail -f /var/log/nginx/error.log`
4. **Estado de servicios:** `sudo systemctl status intradia nginx postgresql`

---

**Versión:** 2.0.0  
**Fecha:** 2025-01-28  
**Estado:** ✅ LISTO PARA DESPLEGAR

