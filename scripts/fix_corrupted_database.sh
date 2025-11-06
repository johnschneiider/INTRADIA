#!/bin/bash
# Script para reparar base de datos SQLite corrupta
# Uso: ./scripts/fix_corrupted_database.sh

echo "=========================================="
echo "🔧 REPARACIÓN DE BASE DE DATOS CORRUPTA"
echo "=========================================="
echo ""

cd /var/www/intradia.com.co

# 1. Detener servicios que usan la BD
echo "🛑 1. Deteniendo servicios..."
sudo systemctl stop intradia-trading-loop intradia-daphne intradia-save-ticks intradia-gunicorn 2>/dev/null
sleep 2
echo "   ✅ Servicios detenidos"
echo ""

# 2. Crear backup
echo "💾 2. Creando backup de la base de datos..."
DB_FILE="db.sqlite3"
BACKUP_FILE="db.sqlite3.backup.$(date +%Y%m%d_%H%M%S)"

if [ -f "$DB_FILE" ]; then
    cp "$DB_FILE" "$BACKUP_FILE"
    echo "   ✅ Backup creado: $BACKUP_FILE"
    echo "   📊 Tamaño del backup: $(du -h "$BACKUP_FILE" | cut -f1)"
else
    echo "   ⚠️  Archivo de BD no encontrado: $DB_FILE"
fi
echo ""

# 3. Verificar integridad
echo "🔍 3. Verificando integridad de la BD..."
source venv/bin/activate

python manage.py dbshell <<EOF
PRAGMA integrity_check;
.quit
EOF

echo ""
echo "   Verificando con sqlite3 directamente..."
sqlite3 "$DB_FILE" "PRAGMA integrity_check;" 2>&1 | head -20
echo ""

# 4. Intentar reparación
echo "🔧 4. Intentando reparar la base de datos..."
REPAIRED_FILE="db.sqlite3.repaired"

# Método 1: Dump y restore
echo "   📤 Método 1: Dump y restore..."
sqlite3 "$DB_FILE" ".dump" > "${DB_FILE}.dump" 2>&1
if [ $? -eq 0 ]; then
    echo "   ✅ Dump completado"
    sqlite3 "$REPAIRED_FILE" < "${DB_FILE}.dump" 2>&1
    if [ $? -eq 0 ]; then
        echo "   ✅ Restore completado"
        # Verificar la BD reparada
        INTEGRITY=$(sqlite3 "$REPAIRED_FILE" "PRAGMA integrity_check;" 2>&1)
        if echo "$INTEGRITY" | grep -q "ok"; then
            echo "   ✅ Base de datos reparada correctamente"
            mv "$DB_FILE" "${DB_FILE}.corrupted"
            mv "$REPAIRED_FILE" "$DB_FILE"
            echo "   ✅ Base de datos reemplazada"
            rm -f "${DB_FILE}.dump"
        else
            echo "   ❌ La reparación falló: $INTEGRITY"
            rm -f "$REPAIRED_FILE"
        fi
    else
        echo "   ❌ Error en restore"
        rm -f "$REPAIRED_FILE"
    fi
else
    echo "   ❌ Error en dump"
fi
echo ""

# 5. Si la reparación falló, intentar método 2: VACUUM
if [ ! -f "$DB_FILE" ] || ! sqlite3 "$DB_FILE" "PRAGMA integrity_check;" 2>&1 | grep -q "ok"; then
    echo "🔧 5. Intentando método 2: VACUUM..."
    if [ -f "${DB_FILE}.corrupted" ]; then
        mv "${DB_FILE}.corrupted" "$DB_FILE"
    fi
    sqlite3 "$DB_FILE" "VACUUM;" 2>&1
    if [ $? -eq 0 ]; then
        echo "   ✅ VACUUM completado"
        INTEGRITY=$(sqlite3 "$DB_FILE" "PRAGMA integrity_check;" 2>&1)
        if echo "$INTEGRITY" | grep -q "ok"; then
            echo "   ✅ Base de datos reparada con VACUUM"
        else
            echo "   ❌ VACUUM no funcionó: $INTEGRITY"
        fi
    else
        echo "   ❌ Error en VACUUM"
    fi
    echo ""
fi

# 6. Verificar resultado final
echo "🔍 6. Verificación final..."
if [ -f "$DB_FILE" ]; then
    INTEGRITY=$(sqlite3 "$DB_FILE" "PRAGMA integrity_check;" 2>&1 | head -1)
    echo "   Resultado: $INTEGRITY"
    if echo "$INTEGRITY" | grep -q "ok"; then
        echo "   ✅ Base de datos OK"
        echo ""
        echo "🔄 Reiniciando servicios..."
        sudo systemctl start intradia-gunicorn intradia-daphne intradia-save-ticks intradia-trading-loop
        sleep 2
        echo "   ✅ Servicios reiniciados"
    else
        echo "   ❌ Base de datos aún corrupta"
        echo ""
        echo "⚠️  OPCIONES:"
        echo "   1. Restaurar desde backup: mv $BACKUP_FILE $DB_FILE"
        echo "   2. Crear nueva BD: python manage.py migrate"
        echo "   3. Verificar logs: sqlite3 $DB_FILE 'PRAGMA integrity_check;'"
    fi
else
    echo "   ❌ Archivo de BD no existe"
    echo ""
    echo "🆕 Creando nueva base de datos..."
    python manage.py migrate
fi
echo ""

echo "=========================================="
echo "✅ Proceso completado"
echo "=========================================="

