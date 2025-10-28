# 🚀 INSTRUCCIONES DESPLIEGUE VPS - INTRADIA

## 🎯 Situación Actual

- **VPS:** 92.113.39.100
- **Dominio nuevo:** www.vitalmix.com.co
- **Dominio existente:** (tu otro proyecto ya funcionando)
- **Puerto interno Gunicorn:** 8000 → 8001 (para evitar conflicto)

## ⚠️ IMPORTANTE: No Interferir con Proyecto Existente

Este documento asume que ya tienes otro proyecto Django corriendo en el puerto 8000 con Gunicorn + Nginx.

---

## 📋 PASO 1: Preparar Directorio Separado

```bash
# Conectar a VPS
ssh root@92.113.39.100
# o
ssh tu_usuario@92.113.39.100

# Crear directorio separado
sudo mkdir -p /var/www/intradia
cd /var/www/intradia

# Clonar repositorio
sudo git clone https://github.com/johnschneiider/INTRADIA.git .

# Permisos
sudo chown -R $USER:$USER /var/www/intradia
```

---

## 📋 PASO 2: Configurar Gunicorn en Puerto Diferente

### Modificar `gunicorn_config.py`:

```python
# Cambiar puerto para no interferir
bind = "127.0.0.1:8001"  # ← Cambiado de 8000 a 8001
```

---

## 📋 PASO 3: Configurar Nginx

### Editar configuración de Nginx:

```bash
sudo nano /etc/nginx/sites-available/intradia
```

**Contenido:**

```nginx
server {
    listen 80;
    server_name vitalmix.com.co www.vitalmix.com.co;
    
    client_max_body_size 10M;
    
    # Archivos estáticos
    location /static/ {
        alias /var/www/intradia/static/;
        expires 30d;
    }
    
    # Proxy a Gunicorn EN PUERTO 8001
    location / {
        proxy_pass http://127.0.0.1:8001;  # ← Puerto 8001
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }
}
```

**Activar sitio:**

```bash
sudo ln -s /etc/nginx/sites-available/intradia /etc/nginx/sites-enabled/
```

**Verificar configuración:**

```bash
sudo nginx -t
```

Si hay errores, verificar que tu otro proyecto sigue funcionando.

---

## 📋 PASO 4: Configurar Base de Datos

```bash
# Crear base de datos PostgreSQL
sudo -u postgres psql

# Dentro de psql:
CREATE DATABASE intradia;
CREATE USER intradia WITH PASSWORD 'tu-password-fuerte';
GRANT ALL PRIVILEGES ON DATABASE intradia TO intradia;
\q
```

---

## 📋 PASO 5: Variables de Entorno

```bash
cd /var/www/intradia
nano .env
```

**Contenido:**

```env
DEBUG=False
SECRET_KEY=genera-un-secret-key-nuevo-y-seguro
DJANGO_ALLOWED_HOSTS=vitalmix.com.co,www.vitalmix.com.co,92.113.39.100

# Base de datos
POSTGRES_HOST=localhost
POSTGRES_DB=intradia
POSTGRES_USER=intradia
POSTGRES_PASSWORD=tu-password-fuerte

# Deriv API
DERIV_API_TOKEN=tu-token-deriv
DERIV_ACCOUNT_ID=tu-account-id
```

**Generar SECRET_KEY:**

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## 📋 PASO 6: Instalar y Configurar

```bash
# 1. Crear entorno virtual
python3 -m venv venv

# 2. Activar entorno
source venv/bin/activate

# 3. Instalar dependencias
pip install --upgrade pip
pip install -r requirements.txt

# 4. Crear directorios
mkdir -p static media logs
chmod 755 static media logs

# 5. Recolectar estáticos
python manage.py collectstatic --noinput

# 6. Migraciones
python manage.py migrate

# 7. Crear superusuario (opcional)
python manage.py createsuperuser
```

---

## 📋 PASO 7: Configurar Systemd Service

```bash
sudo nano /etc/systemd/system/intradia.service
```

**Contenido:**

```ini
[Unit]
Description=INTRADIA Trading System
After=network.target postgresql.service

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/var/www/intradia
Environment="PATH=/var/www/intradia/venv/bin"
ExecStart=/var/www/intradia/venv/bin/gunicorn \
    --config /var/www/intradia/gunicorn_config.py \
    config.wsgi:application
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Activar servicio:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable intradia
sudo systemctl start intradia
```

**Verificar:**

```bash
sudo systemctl status intradia
```

---

## 📋 PASO 8: Configurar DNS

En tu proveedor de dominio, agregar:

```
Tipo: A
Nombre: www.vitalmix.com.co
Valor: 92.113.39.100
TTL: 3600
```

**Verificar DNS:**

```bash
dig vitalmix.com.co
# o
nslookup vitalmix.com.co
```

---

## 📋 PASO 9: Reiniciar Servicios

```bash
# Reiniciar Nginx
sudo systemctl restart nginx

# Verificar que tu otro proyecto sigue funcionando
# (accede a su URL)

# Reiniciar INTRADIA
sudo systemctl restart intradia

# Verificar ambos servicios
sudo systemctl status nginx
sudo systemctl status intradia
```

---

## ✅ PASO 10: Verificar Despliegue

### Verificar URLs:

```bash
# Tu proyecto existente (debería seguir funcionando)
curl http://tu-dominio-existente.com

# Nuevo proyecto INTRADIA
curl http://www.vitalmix.com.co
```

### Verificar Logs:

```bash
# Logs de INTRADIA
sudo journalctl -u intradia -f

# Logs de Nginx
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Acceder al Admin:

```
http://www.vitalmix.com.co/admin/
Usuario: (el que creaste)
Password: (el que configuraste)
```

---

## 🔧 TROUBLESHOOTING

### Problema: Puerto 8000 ocupado

**Solución:** Ya configuramos puerto 8001 en `gunicorn_config.py`

Verificar:
```bash
netstat -tulpn | grep 8000
netstat -tulpn | grep 8001
```

### Problema: "502 Bad Gateway" en vitalmix.com.co

**Verificar:**

```bash
# 1. Verificar que Gunicorn está corriendo
sudo systemctl status intradia

# 2. Verificar que escucha en puerto 8001
sudo netstat -tulpn | grep 8001

# 3. Verificar logs
sudo journalctl -u intradia -n 50

# 4. Probar conexión directa
curl http://127.0.0.1:8001
```

### Problema: Nginx no funciona en ambos dominios

**Verificar configuración:**

```bash
# Ver todos los sitios Nginx
ls -la /etc/nginx/sites-enabled/

# Verificar sintaxis de Nginx
sudo nginx -t

# Ver configuración actual
cat /etc/nginx/nginx.conf
```

### Problema: Error "No module named django"

**Solución:**

```bash
cd /var/www/intradia
source venv/bin/activate
pip install -r requirements.txt
```

---

## 📊 MONITOREO POST-DESPLIEGUE

### Ver Estado de Servicios:

```bash
# Ver todos los servicios Django
sudo systemctl status | grep django
sudo systemctl status | grep intradia

# Ver puertos en uso
sudo netstat -tulpn | grep python
```

### Verificar que No Haya Conflictos:

```bash
# Ver que cada servicio usa su puerto
sudo ss -tulpn | grep -E '8000|8001'

# Deberías ver:
# 8000 → Tu proyecto existente
# 8001 → INTRADIA
```

---

## 🔐 CERTIFICADO SSL (Opcional)

Si quieres HTTPS:

```bash
# Instalar Certbot
sudo apt install certbot python3-certbot-nginx -y

# Obtener certificado para vitalmix.com.co
sudo certbot --nginx -d vitalmix.com.co -d www.vitalmix.com.co

# Verificar renovación automática
sudo certbot renew --dry-run
```

**Nota:** Esto NO afectará el certificado de tu otro proyecto si está configurado en sitios separados.

---

## 📝 ARCHIVOS IMPORTANTES

```
VPS Configuration Files:
├── /var/www/intradia/               → Proyecto INTRADIA
├── /var/www/tu-proyecto-existente/   → Tu proyecto actual
├── /etc/nginx/sites-available/      → Configuraciones Nginx
│   ├── intradia                      → Nueva configuración
│   └── tu-proyecto                   → Tu configuración actual
├── /etc/systemd/system/
│   └── intradia.service              → Servicio systemd
└── /var/log/
    ├── gunicorn/intradia_*.log       → Logs Gunicorn
    └── nginx/                        → Logs Nginx
```

---

## 🔄 ACTUALIZAR CÓDIGO EN FUTURO

```bash
# En la VPS
cd /var/www/intradia

# Obtener cambios
git pull origin main

# Activar entorno
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

## ✅ CHECKLIST FINAL

- [ ] Código subido a GitHub
- [ ] Código clonado en VPS en `/var/www/intradia`
- [ ] Entorno virtual creado y dependencias instaladas
- [ ] `gunicorn_config.py` configurado en puerto 8001
- [ ] Nginx configurado con sitio separado
- [ ] Base de datos PostgreSQL creada
- [ ] Variables de entorno configuradas en `.env`
- [ ] Migraciones ejecutadas
- [ ] Archivos estáticos recolectados
- [ ] Servicio systemd configurado y activo
- [ ] DNS configurado para vitalmix.com.co
- [ ] Servicios funcionando (nginx + intradia)
- [ ] Proyecto existente sigue funcionando
- [ ] Puedo acceder a www.vitalmix.com.co

---

## 📞 SOPORTE

Si hay problemas:

1. **Ver logs:**
   ```bash
   sudo journalctl -u intradia -f
   sudo tail -f /var/log/nginx/error.log
   ```

2. **Verificar servicios:**
   ```bash
   sudo systemctl status intradia
   sudo systemctl status nginx
   sudo systemctl status postgresql
   ```

3. **Verificar puertos:**
   ```bash
   sudo netstat -tulpn | grep -E '80|8000|8001|5432'
   ```

4. **Probar conexión:**
   ```bash
   curl http://www.vitalmix.com.co
   curl http://127.0.0.1:8001
   ```

---

## 🎉 DESPLIEGUE EXITOSO

Si todo está correcto:

- ✅ https://www.vitalmix.com.co → INTRADIA (puerto 8001)
- ✅ https://tu-dominio-existente.com → Tu proyecto (puerto 8000)
- ✅ Ambos funcionan independientemente
- ✅ No hay conflictos

---

**Fecha:** 2025-01-28  
**Versión:** 2.0.0  
**Estado:** ✅ LISTO PARA DESPLEGAR

