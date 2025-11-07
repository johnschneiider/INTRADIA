#requires -version 5.1
<#
.SYNOPSIS
Configuración automatizada de PostgreSQL para el entorno local de INTRADIA.

.DESCRIPTION
Este script crea la base de datos `intradia`, el usuario `intradia` con la contraseña
`intradia123`, habilita los parámetros recomendados y exporta variables de entorno
para la sesión actual de PowerShell. Requiere que `psql` esté disponible en el PATH
y que el usuario actual tenga permisos para ejecutar comandos como el usuario
`postgres` (puede solicitar credenciales sudo si estás en WSL).

.USAGE
    ./setup_local_postgres.ps1

.NOTES
El script no elimina recursos existentes. Si la base de datos o el usuario ya
existen, simplemente continúa.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-PostgresCommand {
    param (
        [Parameter(Mandatory)] [string] $Sql
    )

    $command = @('psql', '-v', 'ON_ERROR_STOP=1', '-Atqc', $Sql)

    try {
        $null = & $command
    }
    catch {
        if ($_.Exception.Message -like '*already exists*') {
            Write-Host "⚠️  $_" -ForegroundColor Yellow
        }
        else {
            throw
        }
    }
}

Write-Host '🚀 Configurando PostgreSQL local para INTRADIA...' -ForegroundColor Cyan

Invoke-PostgresCommand "CREATE USER intradia WITH PASSWORD 'intradia123';"
Invoke-PostgresCommand 'ALTER ROLE intradia SET client_encoding TO ''UTF8'';'
Invoke-PostgresCommand 'ALTER ROLE intradia SET default_transaction_isolation TO ''read committed'';'
Invoke-PostgresCommand 'ALTER ROLE intradia SET timezone TO ''UTC'';'
Invoke-PostgresCommand 'CREATE DATABASE intradia OWNER intradia;'

Write-Host '✅ Usuario y base de datos listos.' -ForegroundColor Green

# Exportar variables de entorno para la sesión actual
$env:POSTGRES_HOST = '127.0.0.1'
$env:POSTGRES_PORT = '5432'
$env:POSTGRES_DB = 'intradia'
$env:POSTGRES_USER = 'intradia'
$env:POSTGRES_PASSWORD = 'intradia123'
$env:POSTGRES_DISABLED = ''
$env:USE_SQLITE = ''

Write-Host '✅ Variables de entorno configuradas para la sesión actual.' -ForegroundColor Green

Write-Host "ℹ️  Ahora puedes ejecutar 'python manage.py migrate' y luego 'python manage.py runserver'." -ForegroundColor Cyan



