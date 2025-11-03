# Configuración SSL con Certbot para vitalmix.com.co

## Paso 1: Instalar Certbot

```bash
# Actualizar paquetes
sudo apt update

# Instalar Certbot y el plugin de Nginx
sudo apt install -y certbot python3-certbot-nginx
```

## Paso 2: Preparar configuración Nginx

```bash
cd /var/www/intradia.com.co
git pull origin main

# Hacer backup de la configuración actual
sudo cp /etc/nginx/sites-available/intradia /etc/nginx/sites-available/intradia.backup

# Copiar la nueva configuración con SSL
sudo cp /var/www/intradia.com.co/nginx_intradia_ssl.conf /etc/nginx/sites-available/intradia

# Verificar que la configuración sea válida (sin SSL todavía)
sudo nginx -t
```

## Paso 3: Crear directorio para desafíos de Certbot

```bash
sudo mkdir -p /var/www/certbot
sudo chown www-data:www-data /var/www/certbot
```

## Paso 4: Configurar Nginx temporalmente (sin SSL)

Primero, asegúrate de que Nginx pueda servir los desafíos de Certbot:

```bash
# La configuración ya incluye el bloque para /.well-known/acme-challenge/
# Solo necesitas reiniciar Nginx
sudo systemctl reload nginx
```

## Paso 5: Obtener certificado SSL con Certbot

```bash
# Ejecutar Certbot para obtener el certificado
sudo certbot --nginx -d vitalmix.com.co -d www.vitalmix.com.co

# Certbot pedirá:
# - Email para notificaciones (opcional pero recomendado)
# - Aceptar términos de servicio
# - Si quieres compartir email con EFF (opcional)
# - Si quieres redirigir HTTP a HTTPS (seleccionar "2" para redirigir)
```

## Paso 6: Verificar renovación automática

Certbot configura automáticamente un cron job para renovar los certificados. Verificar:

```bash
# Ver el timer de renovación
sudo systemctl status certbot.timer

# Probar renovación (dry-run)
sudo certbot renew --dry-run
```

## Paso 7: Verificar que todo funcione

```bash
# Verificar que Nginx esté corriendo
sudo systemctl status nginx

# Verificar que el certificado esté activo
sudo certbot certificates

# Probar acceso HTTPS
curl -I https://vitalmix.com.co/
```

## Notas importantes:

1. **Renovación automática**: Certbot configura automáticamente la renovación. Los certificados se renuevan 30 días antes de expirar.

2. **Verificar renovación manualmente**:
   ```bash
   sudo certbot renew
   ```

3. **Si necesitas renovar manualmente antes**:
   ```bash
   sudo certbot renew --force-renewal
   ```

4. **Logs de Certbot**:
   ```bash
   sudo tail -f /var/log/letsencrypt/letsencrypt.log
   ```

5. **Después de renovar, recargar Nginx**:
   ```bash
   sudo systemctl reload nginx
   ```

## Troubleshooting:

### Error: "Connection refused" al obtener certificado
- Verifica que el dominio apunte correctamente a la IP del servidor
- Verifica que Nginx esté corriendo y escuchando en el puerto 80
- Verifica que no haya firewall bloqueando el puerto 80

### Error: "Domain not found"
- Verifica que el DNS del dominio esté configurado correctamente
- Espera unos minutos después de configurar DNS (puede tardar en propagarse)

### Error: "Too many requests"
- Let's Encrypt tiene límites de rate. Si obtienes muchos certificados, espera 1 semana.
- Puedes usar `--staging` para pruebas (certificados no válidos pero sin límites)

### Si necesitas un certificado de prueba (staging):
```bash
sudo certbot --nginx -d vitalmix.com.co -d www.vitalmix.com.co --staging
```

