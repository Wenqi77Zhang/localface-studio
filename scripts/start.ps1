$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "The local environment is missing. Run scripts\bootstrap.ps1 first."
}

Set-Location $Root
& $Python scripts\run_dev.py
if ($LASTEXITCODE -ne 0) {
    throw "LocalFace Studio stopped with exit code $LASTEXITCODE."
}
