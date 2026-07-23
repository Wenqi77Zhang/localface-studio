param(
    [switch]$Offline
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Tools = Join-Path $Root ".tools"
$NodeDir = Join-Path $Tools "node"
$NodeVersion = "24.18.0"
$NodeArchiveName = "node-v$NodeVersion-win-x64.zip"
$NodeSha256 = "0AE68406B42D7725661DA979B1403EC9926DA205C6770827F33AAC9D8F26E821"
$NodeBaseUrl = "https://nodejs.org/dist/v$NodeVersion"
$UvCache = Join-Path $Tools "uv-cache"
$NpmCache = Join-Path $Tools "npm-cache"

function Assert-ExitCode {
    param([string]$Name)
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE."
    }
}

if (-not [Environment]::Is64BitOperatingSystem) {
    throw "LocalFace Studio currently requires 64-bit Windows."
}

$Uv = Get-Command uv.exe -ErrorAction SilentlyContinue
if (-not $Uv) {
    throw "uv is required. Install it from https://docs.astral.sh/uv/ and rerun this script."
}

$PythonPath = (& py -3.14 -c "import sys; print(sys.executable)").Trim()
Assert-ExitCode "Python 3.14 discovery"
if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "Python 3.14 was not found."
}

New-Item -ItemType Directory -Force -Path $Tools | Out-Null
Set-Location $Root

if (-not (Test-Path -LiteralPath (Join-Path $Root ".venv\Scripts\python.exe"))) {
    & $Uv.Source venv .venv --python $PythonPath --no-managed-python --cache-dir $UvCache
    Assert-ExitCode "Python virtual environment creation"
}

$UvSyncArguments = @(
    "sync", "--locked", "--no-managed-python", "--no-python-downloads", "--cache-dir", $UvCache
)
if ($Offline) {
    $UvSyncArguments += "--offline"
}
& $Uv.Source @UvSyncArguments
Assert-ExitCode "Python dependency sync"

if (-not (Test-Path -LiteralPath (Join-Path $NodeDir "node.exe"))) {
    if ($Offline) {
        throw "Project-local Node.js is missing and cannot be downloaded in offline mode."
    }
    $Downloads = Join-Path $Tools "downloads"
    $Archive = Join-Path $Downloads $NodeArchiveName
    $Manifest = Join-Path $Downloads "SHASUMS256.txt"
    $Staging = Join-Path $Tools "node-extract"
    New-Item -ItemType Directory -Force -Path $Downloads | Out-Null

    Invoke-WebRequest -UseBasicParsing -Uri "$NodeBaseUrl/$NodeArchiveName" -OutFile $Archive
    Invoke-WebRequest -UseBasicParsing -Uri "$NodeBaseUrl/SHASUMS256.txt" -OutFile $Manifest

    $ManifestLine = Get-Content -Encoding ASCII $Manifest |
        Where-Object { $_ -match "$([regex]::Escape($NodeArchiveName))$" }
    if (-not $ManifestLine) {
        throw "The official Node.js checksum entry is missing."
    }
    $ManifestHash = ($ManifestLine -split "\s+")[0].ToUpperInvariant()
    $ActualHash = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($ManifestHash -ne $NodeSha256 -or $ActualHash -ne $NodeSha256) {
        throw "Node.js checksum verification failed."
    }
    if (Test-Path -LiteralPath $Staging) {
        throw "Temporary Node.js extraction directory already exists: $Staging"
    }

    Expand-Archive -LiteralPath $Archive -DestinationPath $Staging
    $Extracted = Join-Path $Staging "node-v$NodeVersion-win-x64"
    if (-not (Test-Path -LiteralPath (Join-Path $Extracted "node.exe"))) {
        throw "Unexpected Node.js archive layout."
    }
    Move-Item -LiteralPath $Extracted -Destination $NodeDir
}

$Node = Join-Path $NodeDir "node.exe"
$Npm = Join-Path $NodeDir "npm.cmd"
$InstalledNodeVersion = (& $Node --version).Trim()
if ($InstalledNodeVersion -ne "v$NodeVersion") {
    throw "Expected Node.js v$NodeVersion, found $InstalledNodeVersion."
}

$env:Path = "$NodeDir;$env:Path"
Set-Location (Join-Path $Root "frontend")
$NpmArguments = @("ci", "--cache", $NpmCache)
if ($Offline) {
    $NpmArguments += "--offline"
}
& $Npm @NpmArguments
Assert-ExitCode "Frontend dependency sync"

Set-Location $Root
Write-Host "LocalFace Studio environment is ready."
