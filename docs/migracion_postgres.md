## Plan de migración de SQLite a PostgreSQL

### 1. Preparativos y dependencias

1. Instala PostgreSQL (versión 13+ recomendada) en la VPS o en un servicio gestionado.
2. Instala las client tools necesarias (opcional si usas el script automatizado más abajo):
   ```bash
   sudo apt update
   sudo apt install -y postgresql postgresql-contrib libpq-dev
   ```
3. Instala el driver de Python en el entorno virtual del proyecto:
   ```bash
   source /var/www/intradia.com.co/venv/bin/activate
   pip install psycopg2-binary
   ```

### 2. Crear base de datos y usuario

```bash
sudo -u postgres psql
CREATE DATABASE intradia;
CREATE USER intradia WITH PASSWORD 'intradia123';
ALTER ROLE intradia SET client_encoding TO 'UTF8';
ALTER ROLE intradia SET default_transaction_isolation TO 'read committed';
ALTER ROLE intradia SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE intradia TO intradia;
\q
```

Opcional: Si quieres separar el esquema para futuras migraciones:
```sql
CREATE SCHEMA intradia AUTHORIZATION intradia;
```

### 3. Configurar variables de entorno

En el archivo de servicio (`/etc/systemd/system/intradia-gunicorn.service`, `intradia-daphne.service` y el loop) añade:

```
Environment="POSTGRES_HOST=127.0.0.1"
Environment="POSTGRES_PORT=5432"
Environment="POSTGRES_DB=intradia"
Environment="POSTGRES_USER=intradia"
Environment="POSTGRES_PASSWORD=intradia123"
```

Recarga los demonios para que systemd lea los cambios pero aún **no** reinicies los servicios:
```bash
sudo systemctl daemon-reload
```

### 4. Respaldar la base de datos SQLite

Desde el directorio del proyecto:
```bash
cd /var/www/intradia.com.co
source venv/bin/activate
python manage.py dumpdata --natural-foreign --natural-primary --exclude auth.permission --exclude contenttypes --exclude sessions --indent 2 > backup_sqlite.json
cp db.sqlite3 db.sqlite3.backup_$(date +%Y%m%d_%H%M%S)
```

### 5. Ejecutar migraciones sobre PostgreSQL

1. Asegúrate de que los servicios estén detenidos para evitar escrituras durante la migración:
   ```bash
   sudo systemctl stop intradia-gunicorn intradia-daphne intradia-trading-loop intradia-save-ticks
   ```
2. Activa el entorno virtual y ejecuta:
   ```bash
   source venv/bin/activate
   python manage.py migrate --noinput
   ```

### 6. Cargar los datos exportados

```bash
python manage.py loaddata backup_sqlite.json
```

Si encuentras errores de claves duplicadas, revisa el archivo `backup_sqlite.json` para eliminar registros inconsistentes antes de reintentar.

### 7. Verificación

1. Ejecuta pruebas básicas:
   ```bash
   python manage.py check
   python manage.py showmigrations
   ```
2. Abre el shell de Django y verifica conteos de modelos críticos:
   ```bash
   python manage.py shell
   >>> from monitoring.models import OrderAudit
   >>> OrderAudit.objects.count()
   ```

### 8. Reinicio de servicios

```bash
sudo systemctl start intradia-gunicorn intradia-daphne intradia-trading-loop intradia-save-ticks
sudo systemctl status intradia-gunicorn
```

### 9. Limpieza y mantenimiento

1. Conserva el respaldo `db.sqlite3.backup_*` por si necesitas volver atrás.
2. Configura backups automáticos de PostgreSQL (ej.: `pg_dump` diario a S3).
3. Opcional: habilita `pg_stat_statements`/`auto_vacuum` según la carga del sistema.

> NOTA: si prefieres seguir usando SQLite en algún entorno, establece la variable `USE_SQLITE=1` antes de ejecutar `manage.py`.

---

### Modo automático en la VPS (recomendado)

El repositorio incluye un script que ejecuta todos los pasos (respaldo, creación de base y usuario, migración y restauración). Para usarlo:

```bash
cd /var/www/intradia.com.co
chmod +x scripts/migrate_sqlite_to_postgres.sh
sudo ./scripts/migrate_sqlite_to_postgres.sh
```

El script detiene los servicios, crea un respaldo JSON en `backups/`, provisiona PostgreSQL con usuario `intradia`/`intradia123`, importa datos y reactiva los servicios.

### Modo automático en tu entorno local (Windows PowerShell / WSL)

Para preparar tu entorno de desarrollo local con PostgreSQL usando las mismas credenciales, ejecuta:

```powershell
cd E:\INTRADIA
PowerShell -ExecutionPolicy Bypass -File .\scripts\setup_local_postgres.ps1
```

Esto crea la base `intradia`, el usuario `intradia` con clave `intradia123` y deja las variables de entorno listas para que `manage.py` use PostgreSQL de inmediato.


