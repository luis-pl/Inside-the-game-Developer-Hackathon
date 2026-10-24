param([int]$Port = 8080, [string]$PythonPath = '', [string]$NodePath = '')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
# Use a supported Node runtime; this machine also has an older Node on PATH.
# NodePath allows the same command to work on machines without Codex runtimes.
$nodeCandidates = @()
if ($NodePath) { $nodeCandidates += $NodePath }
else {
    $systemNode = Get-Command node -ErrorAction SilentlyContinue
    if ($systemNode) { $nodeCandidates += $systemNode.Source }
    $nodeCandidates += Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
}
$selectedNode = $null
foreach ($candidate in $nodeCandidates) {
    if (-not (Test-Path -LiteralPath $candidate)) { continue }
    $nodeVersion = [version]((& $candidate --version).TrimStart('v'))
    if (($nodeVersion.Major -eq 24 -and $nodeVersion -ge [version]'24.22.1') -or
        ($nodeVersion.Major -eq 26 -and $nodeVersion -ge [version]'26.12.1')) {
        $selectedNode = $candidate
        break
    }
}
if (-not $selectedNode) { throw 'Instala Node 24.22.1+ (24.x) o 26.12.1+ (26.x), o indica -NodePath.' }
$env:PATH = (Split-Path -Parent $selectedNode) + [IO.Path]::PathSeparator + $env:PATH
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
