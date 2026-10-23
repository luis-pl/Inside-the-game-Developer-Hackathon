param(
    [string]$HostName = '127.0.0.1',
    [int]$Port = 8000
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$localSettings = Join-Path $projectRoot '.env.local'
if (Test-Path -LiteralPath $localSettings) {
    foreach ($line in Get-Content -LiteralPath $localSettings) {
        if ($line -match '^\s*(INSIDE_GAME_[A-Z_]+|AZURE_CLI_PATH|AZURE_CONFIG_DIR)\s*=(.*)$') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim().Trim('"').Trim("'"), 'Process')
        }
    }
}
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Crea .venv e instala el proyecto siguiendo docs/api.md.' }
Push-Location -LiteralPath $projectRoot
try {
    & $pythonPath -m inside_game.cli --host $HostName --port $Port
} finally {
    Pop-Location
}
