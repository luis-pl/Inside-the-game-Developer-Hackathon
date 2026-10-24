param([int]$Port = 8080, [string]$PythonPath = '')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath (Join-Path $projectRoot 'frontend')
try {
    if (-not (Test-Path -LiteralPath 'node_modules')) { npm ci; if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' } }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
} finally { Pop-Location }
$previousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = Join-Path $projectRoot 'src'
try {
    $localPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
    $bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if ($PythonPath) { & $PythonPath -m inside_game.dashboard --port $Port }
    elseif (Test-Path -LiteralPath $localPython) { & $localPython -m inside_game.dashboard --port $Port }
    elseif (Test-Path -LiteralPath $bundledPython) { & $bundledPython -m inside_game.dashboard --port $Port }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { py -3 -m inside_game.dashboard --port $Port }
    else { python -m inside_game.dashboard --port $Port }
    if ($LASTEXITCODE -ne 0) { throw 'Se requiere Python 3.12+. Puedes indicar su ejecutable mediante -PythonPath.' }
} finally { $env:PYTHONPATH = $previousPythonPath }
