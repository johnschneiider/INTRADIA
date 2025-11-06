#!/usr/bin/env python3
"""
Script para reparar base de datos SQLite corrupta usando Python
"""
import sqlite3
import shutil
import os
import sys
from datetime import datetime

def main():
    print("=" * 50)
    print("🔧 REPARACIÓN DE BASE DE DATOS CORRUPTA")
    print("=" * 50)
    print()
    
    db_file = "db.sqlite3"
    
    # 1. Verificar que existe
    if not os.path.exists(db_file):
        print(f"❌ Archivo de BD no encontrado: {db_file}")
        return 1
    
    # 2. Crear backup
    print("💾 2. Creando backup de la base de datos...")
    backup_file = f"{db_file}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(db_file, backup_file)
    backup_size = os.path.getsize(backup_file) / (1024 * 1024)  # MB
    print(f"   ✅ Backup creado: {backup_file}")
    print(f"   📊 Tamaño del backup: {backup_size:.2f} MB")
    print()
    
    # 3. Verificar integridad
    print("🔍 3. Verificando integridad de la BD...")
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()
        conn.close()
        
        if result and result[0] == "ok":
            print("   ✅ Base de datos está OK, no necesita reparación")
            return 0
        else:
            print(f"   ❌ Base de datos corrupta: {result}")
    except Exception as e:
        print(f"   ❌ Error verificando integridad: {e}")
    print()
    
    # 4. Intentar reparación con dump/restore
    print("🔧 4. Intentando reparar la base de datos...")
    repaired_file = f"{db_file}.repaired"
    dump_file = f"{db_file}.dump"
    
    try:
        # Dump
        print("   📤 Creando dump...")
        conn_old = sqlite3.connect(db_file)
        with open(dump_file, 'w', encoding='utf-8') as f:
            for line in conn_old.iterdump():
                f.write(f"{line}\n")
        conn_old.close()
        print("   ✅ Dump completado")
        
        # Restore
        print("   📥 Restaurando a nueva BD...")
        conn_new = sqlite3.connect(repaired_file)
        with open(dump_file, 'r', encoding='utf-8') as f:
            dump_content = f.read()
            conn_new.executescript(dump_content)
        conn_new.close()
        print("   ✅ Restore completado")
        
        # Verificar la BD reparada
        print("   🔍 Verificando BD reparada...")
        conn_check = sqlite3.connect(repaired_file)
        cursor_check = conn_check.cursor()
        cursor_check.execute("PRAGMA integrity_check;")
        result_check = cursor_check.fetchone()
        conn_check.close()
        
        if result_check and result_check[0] == "ok":
            print("   ✅ Base de datos reparada correctamente")
            
            # Reemplazar
            corrupted_file = f"{db_file}.corrupted"
            if os.path.exists(corrupted_file):
                os.remove(corrupted_file)
            
            os.rename(db_file, corrupted_file)
            os.rename(repaired_file, db_file)
            os.remove(dump_file)
            
            print("   ✅ Base de datos reemplazada")
            print()
            print("=" * 50)
            print("✅ Reparación completada exitosamente")
            print("=" * 50)
            return 0
        else:
            print(f"   ❌ La reparación falló: {result_check}")
            os.remove(repaired_file)
            os.remove(dump_file)
            return 1
            
    except Exception as e:
        print(f"   ❌ Error en reparación: {e}")
        import traceback
        traceback.print_exc()
        
        # Limpiar archivos temporales
        if os.path.exists(repaired_file):
            os.remove(repaired_file)
        if os.path.exists(dump_file):
            os.remove(dump_file)
        return 1

if __name__ == "__main__":
    sys.exit(main())

