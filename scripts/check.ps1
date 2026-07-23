param(
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Ruff = Join-Path $Root ".venv\Scripts\ruff.exe"
$Mypy = Join-Path $Root ".venv\Scripts\mypy.exe"
$Pytest = Join-Path $Root ".venv\Scripts\pytest.exe"
$NodeDir = Join-Path $Root ".tools\node"
$Npm = Join-Path $NodeDir "npm.cmd"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Command"
    }
}

Set-Location $Root

Invoke-Checked $Ruff check src tests scripts
Invoke-Checked $Ruff format --check src tests scripts
Invoke-Checked $Mypy src scripts tests
Invoke-Checked $Pytest -q --cov --cov-report=term-missing
Invoke-Checked $Python scripts\scan_public_repo.py
Invoke-Checked $Python scripts\verify_backend.py
Invoke-Checked git diff --check
Invoke-Checked git diff --cached --check

if (-not $SkipFrontend) {
    if (-not (Test-Path $Npm)) {
        throw "Project-local Node.js is missing at .tools/node."
    }
    $env:Path = "$NodeDir;$env:Path"
    Set-Location (Join-Path $Root "frontend")
    Invoke-Checked $Npm run check
    Set-Location $Root
    Invoke-Checked $Python scripts\verify_frontend.py
}

Write-Host "All LocalFace Studio quality gates passed."
