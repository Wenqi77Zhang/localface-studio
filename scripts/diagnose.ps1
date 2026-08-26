param(
    [switch]$FullModelHash
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Failures = 0
$Warnings = 0

function Write-Check {
    param(
        [string]$Label,
        [ValidateSet("OK", "WARN", "FAIL")][string]$Status,
        [string]$Detail
    )
    if ($Status -eq "FAIL") { $script:Failures += 1 }
    if ($Status -eq "WARN") { $script:Warnings += 1 }
    Write-Host ("[{0}] {1} - {2}" -f $Status, $Label, $Detail)
}

function Test-LocalPort {
    param([int]$Port)
    $Listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Loopback,
        $Port
    )
    try {
        $Listener.Start()
        return $true
    }
    catch [System.Net.Sockets.SocketException] {
        return $false
    }
    finally {
        $Listener.Stop()
    }
}

Write-Host "LocalFace Studio diagnostics (no image or identity data is read)"

if ([Environment]::Is64BitOperatingSystem) {
    Write-Check "Windows architecture" "OK" "64-bit"
}
else {
    Write-Check "Windows architecture" "FAIL" "64-bit Windows is required"
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $Python) {
    $PythonVersion = (& $Python -c "import platform; print(platform.python_version())").Trim()
    if ($LASTEXITCODE -eq 0 -and $PythonVersion.StartsWith("3.14.")) {
        Write-Check "Project Python" "OK" $PythonVersion
    }
    else {
        Write-Check "Project Python" "FAIL" "expected Python 3.14.x"
    }
}
else {
    Write-Check "Project Python" "FAIL" "run setup.cmd first"
}

$Node = Join-Path $Root ".tools\node\node.exe"
if (Test-Path -LiteralPath $Node) {
    $NodeVersion = (& $Node --version).Trim()
    Write-Check "Project Node.js" "OK" $NodeVersion
}
else {
    Write-Check "Project Node.js" "FAIL" "run setup.cmd first"
}

$Vite = Join-Path $Root "frontend\node_modules\vite\bin\vite.js"
if (Test-Path -LiteralPath $Vite) {
    Write-Check "Frontend dependencies" "OK" "installed in the project"
}
else {
    Write-Check "Frontend dependencies" "FAIL" "run setup.cmd first"
}

foreach ($Port in 8000, 5173) {
    if (Test-LocalPort $Port) {
        Write-Check "Loopback port $Port" "OK" "available"
    }
    else {
        Write-Check "Loopback port $Port" "WARN" "already in use; close the old app instance"
    }
}

$ManifestPath = Join-Path $Root "config\models.json"
if (Test-Path -LiteralPath $ManifestPath) {
    $Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($Model in $Manifest.models) {
        $ModelPath = Join-Path $Root ([string]$Model.relative_path)
        $Required = $Model.id -in @(
            "yunet-opencv",
            "inswapper-128-research",
            "arcface-w600k-r50-research"
        )
        if (-not (Test-Path -LiteralPath $ModelPath)) {
            $Status = if ($Required) { "FAIL" } else { "WARN" }
            $Detail = if ($Required) { "required file is missing" } else { "optional file is missing" }
            Write-Check ("Model " + $Model.id) $Status $Detail
            continue
        }
        $Length = (Get-Item -LiteralPath $ModelPath).Length
        if ($Length -ne [long]$Model.size_bytes) {
            Write-Check ("Model " + $Model.id) "FAIL" "file size does not match the manifest"
            continue
        }
        if ($FullModelHash) {
            $Hash = (Get-FileHash -LiteralPath $ModelPath -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($Hash -ne ([string]$Model.sha256).ToLowerInvariant()) {
                Write-Check ("Model " + $Model.id) "FAIL" "SHA-256 does not match"
                continue
            }
            Write-Check ("Model " + $Model.id) "OK" "size and SHA-256 verified"
        }
        else {
            Write-Check ("Model " + $Model.id) "OK" "size verified; use -FullModelHash for SHA-256"
        }
    }
}
else {
    Write-Check "Model manifest" "FAIL" "config/models.json is missing"
}

if (Test-Path -LiteralPath $Python) {
    $ProviderJson = & $Python -c "import json, onnxruntime as ort; print(json.dumps(ort.get_available_providers()))" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $Providers = $ProviderJson | ConvertFrom-Json
        if ($Providers -contains "CUDAExecutionProvider") {
            Write-Check "ONNX Runtime" "OK" "CUDA and CPU providers available"
        }
        elseif ($Providers -contains "CPUExecutionProvider") {
            Write-Check "ONNX Runtime" "WARN" "CPU only; GPU acceleration is unavailable"
        }
        else {
            Write-Check "ONNX Runtime" "FAIL" "no supported execution provider"
        }
    }
    else {
        Write-Check "ONNX Runtime" "FAIL" "runtime import failed; rerun setup.cmd"
    }
}

Write-Host ""
Write-Host ("Summary: {0} failure(s), {1} warning(s)." -f $Failures, $Warnings)
if ($Failures -gt 0) {
    exit 1
}
exit 0
