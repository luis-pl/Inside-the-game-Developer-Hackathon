<#
.SYNOPSIS
Inicia el servidor MCP local que consulta la API de analítica deportiva.
.DESCRIPTION
Requiere la API activa (por defecto, puerto 8000) y el proyecto instalado en
.venv. Carga opciones INSIDE_GAME_* de .env.local sin ejecutar su contenido.
stdio lo inicia normalmente un cliente MCP; HTTP queda disponible en /mcp.
.PARAMETER Transport
stdio para entrada/salida del proceso; streamable-http para conexión HTTP local.
.PARAMETER Port
Puerto del servidor HTTP MCP. No cambia el puerto de la API; stdio no lo usa.
.EXAMPLE
.\scripts\start-mcp.ps1
.EXAMPLE
.\scripts\start-mcp.ps1 -Transport streamable-http -Port 8001
#>
param(
    [ValidateSet('stdio', 'streamable-http')]
    [string]$Transport = 'stdio',
    [int]$Port = 8001
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$localSettings = Join-Path $projectRoot '.env.local'
if (Test-Path -LiteralPath $localSettings) {
    # Sólo admite claves de configuración del proyecto; no evalúa PowerShell
    # ni imprime valores que puedan contener la clave de acceso a la API.
    foreach ($line in Get-Content -LiteralPath $localSettings) {
        if ($line -match '^\s*(INSIDE_GAME_[A-Z_]+)\s*=(.*)$') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim().Trim('"').Trim("'"), 'Process')
        }
    }
}
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Crea .venv e instala el proyecto siguiendo docs/api.md.' }
# Permite invocar el script desde otro directorio y restaura la ubicación al salir.
Push-Location -LiteralPath $projectRoot
try {
    & $pythonPath -m inside_game.mcp_server --transport $Transport --port $Port
} finally {
    Pop-Location
}
