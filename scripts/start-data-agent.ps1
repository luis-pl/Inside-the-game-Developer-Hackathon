param(
    [string]$Text,
    [string]$RequestFile,
    [string]$OutputFile,
    [switch]$ShowTools
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $repoRoot '.env.local'
# Sólo asignaciones de configuración, nunca Invoke-Expression o dot-sourcing.
if (Test-Path -LiteralPath $envFile) {
    foreach ($line in Get-Content -LiteralPath $envFile) {
        if ($line -match '^\s*(INSIDE_GAME_[A-Z_]+|AZURE_[A-Z_]+)\s*=(.*)$') {
            [Environment]::SetEnvironmentVariable(
                $Matches[1], $Matches[2].Trim().Trim('"').Trim("'"), 'Process'
            )
        }
    }
}
if ($env:AZURE_CLI_PATH) {
    $env:PATH = (Split-Path -Parent $env:AZURE_CLI_PATH) + [IO.Path]::PathSeparator + $env:PATH
}
$agentArgs = @('-m', 'inside_game.data_agent_cli')
if ($Text) { $agentArgs += @('--text', $Text) }
if ($RequestFile) { $agentArgs += @('--request-file', $RequestFile) }
if ($OutputFile) { $agentArgs += @('--output', $OutputFile) }
if ($ShowTools) { $agentArgs += '--verbose' }
& (Join-Path $repoRoot '.venv/Scripts/python.exe') @agentArgs
exit $LASTEXITCODE
