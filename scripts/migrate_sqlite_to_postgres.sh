#!/usr/bin/env bash

set -euo pipefail

cat <<'BANNER'
============================================================
🚀 Migración automatizada de SQLite a PostgreSQL (INTRADIA)
============================================================
BANNER

if [[ $EUID -ne 0 ]]; then
  echo "❌ Debes ejecutar este script como root (o con sudo)." >&2
  exit 1
fi

PROJECT_DIR="/var/www/intradia.com.co"
VENV_DIR="$PROJECT_DIR/venv"
SQLITE_DB="$PROJECT_DIR/db.sqlite3"
BACKUP_DIR="$PROJECT_DIR/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
JSON_BACKUP="$BACKUP_DIR/backup_sqlite_$TIMESTAMP.json"

read -rp "Nombre de la base de datos PostgreSQL [intradia]: " POSTGRES_DB
POSTGRES_DB=${POSTGRES_DB:-intradia}

read -rp "Usuario PostgreSQL [intradia]: " POSTGRES_USER
POSTGRES_USER=${POSTGRES_USER:-intradia}

read -rp "Contraseña PostgreSQL [intradia123]: " POSTGRES_PASSWORD
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-intradia123}

read -rp "Puerto PostgreSQL [5432]: " POSTGRES_PORT
POSTGRES_PORT=${POSTGRES_PORT:-5432}

systemctl stop intradia-trading-loop.service intradia-save-ticks.service intradia-gunicorn.service intradia-daphne.service || true

mkdir -p "$BACKUP_DIR"

echo "📦 Creando respaldo JSON desde SQLite..."
cd "$PROJECT_DIR"

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet psycopg2-binary

python manage.py dumpdata --natural-foreign --natural-primary --exclude auth.permission --exclude contenttypes --indent 2 > "$JSON_BACKUP"

echo "✅ Respaldo guardado en $JSON_BACKUP"

echo "🏗️ Creando usuario y base de datos en PostgreSQL..."
sudo -u postgres psql <<SQL
DO
$$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$POSTGRES_USER') THEN
      CREATE ROLE $POSTGRES_USER LOGIN PASSWORD '$POSTGRES_PASSWORD';
   END IF;
END
$$;

ALTER ROLE $POSTGRES_USER SET client_encoding TO 'UTF8';
ALTER ROLE $POSTGRES_USER SET default_transaction_isolation TO 'read committed';
ALTER ROLE $POSTGRES_USER SET timezone TO 'UTC';

SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = '$POSTGRES_DB' AND pid <> pg_backend_pid();

DROP DATABASE IF EXISTS $POSTGRES_DB;
CREATE DATABASE $POSTGRES_DB OWNER $POSTGRES_USER;
SQL

export POSTGRES_HOST=127.0.0.1
export POSTGRES_PORT=$POSTGRES_PORT
export POSTGRES_DB=$POSTGRES_DB
export POSTGRES_USER=$POSTGRES_USER
export POSTGRES_PASSWORD=$POSTGRES_PASSWORD
export POSTGRES_DISABLED=
export USE_SQLITE=

echo "🛠️ Ejecutando migraciones en PostgreSQL..."
python manage.py migrate --noinput

echo "📥 Cargando respaldo..."
python manage.py loaddata "$JSON_BACKUP"

echo "✅ Migración completada. Actualizando servicios..."

systemctl daemon-reload
systemctl start intradia-gunicorn.service intradia-daphne.service intradia-save-ticks.service intradia-trading-loop.service

echo "🎉 Migración completada. No olvides actualizar /etc/environment o los archivos de systemd
con las variables POSTGRES_* para que persistan tras reinicios."

