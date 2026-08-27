param(
    [switch]$FullModelHash,
    [switch]$ExportReport
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Failures = 0
$Warnings = 0
$Checks = [System.Collections.Generic.List[object]]::new()

function Write-Check {
    param(
        [string]$Label,
        [ValidateSet("OK", "WARN", "FAIL")][string]$Status,
        [string]$Detail
    )
    if ($Status -eq "FAIL") { $script:Failures += 1 }
    if ($Status -eq "WARN") { $script:Warnings += 1 }
    $script:Checks.Add([pscustomobject]@{
        label = $Label
        status = $Status
        detail = $Detail
    })
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

$OsVersion = [Environment]::OSVersion.Version
Write-Check "Windows version" "OK" ("{0}.{1}.{2}" -f $OsVersion.Major, $OsVersion.Minor, $OsVersion.Build)

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

try {
    $Drive = [System.IO.DriveInfo]::new((Get-Item -LiteralPath $Root).PSDrive.Root)
    $FreeGb = [math]::Round($Drive.AvailableFreeSpace / 1GB, 1)
    if ($FreeGb -lt 2) {
        Write-Check "Free disk space" "FAIL" ("{0} GB available; at least 2 GB is required" -f $FreeGb)
    }
    elseif ($FreeGb -lt 10) {
        Write-Check "Free disk space" "WARN" ("{0} GB available; keep at least 10 GB for safer setup and updates" -f $FreeGb)
    }
    else {
        Write-Check "Free disk space" "OK" ("{0} GB available" -f $FreeGb)
    }
}
catch {
    Write-Check "Free disk space" "WARN" "could not read available space"
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
    $RuntimeJson = & $Python -c "import importlib.metadata as m,json,onnxruntime as ort; names=['localface-studio','onnxruntime-gpu','insightface','numpy','opencv-python-headless']; print(json.dumps({'providers':ort.get_available_providers(),'packages':{n:m.version(n) for n in names}}))" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $Runtime = $RuntimeJson | ConvertFrom-Json
        $Providers = $Runtime.providers
        if ($Providers -contains "CUDAExecutionProvider") {
            Write-Check "ONNX Runtime" "OK" "CUDA and CPU providers available"
        }
        elseif ($Providers -contains "CPUExecutionProvider") {
            Write-Check "ONNX Runtime" "WARN" "CPU only; GPU acceleration is unavailable"
        }
        else {
            Write-Check "ONNX Runtime" "FAIL" "no supported execution provider"
        }
        foreach ($Package in $Runtime.packages.PSObject.Properties) {
            Write-Check ("Python package " + $Package.Name) "OK" ([string]$Package.Value)
        }
    }
    else {
        Write-Check "ONNX Runtime" "FAIL" "runtime import failed; rerun setup.cmd"
    }
}

$NvidiaSmi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
if ($null -ne $NvidiaSmi) {
    $GpuRows = @(& $NvidiaSmi.Source --query-gpu=name,driver_version,memory.total --format=csv,noheader,nounits 2>$null)
    if ($LASTEXITCODE -eq 0 -and $GpuRows.Count -gt 0) {
        foreach ($GpuRow in $GpuRows) {
            $GpuParts = @(([string]$GpuRow).Split(",") | ForEach-Object { $_.Trim() })
            if ($GpuParts.Count -eq 3) {
                Write-Check "NVIDIA adapter" "OK" ("{0}; driver {1}; {2} MiB VRAM" -f $GpuParts[0], $GpuParts[1], $GpuParts[2])
            }
        }
    }
    else {
        Write-Check "NVIDIA adapter" "WARN" "nvidia-smi could not read adapter information"
    }
}
else {
    try {
        $Adapters = @(Get-CimInstance Win32_VideoController -ErrorAction Stop)
        if ($Adapters.Count -eq 0) {
            Write-Check "Display adapter" "WARN" "Windows did not report a display adapter"
        }
        else {
            foreach ($Adapter in $Adapters) {
                $Name = ([string]$Adapter.Name).Trim()
                $Driver = ([string]$Adapter.DriverVersion).Trim()
                Write-Check "Display adapter" "OK" ("{0}; driver {1}" -f $Name, $Driver)
            }
        }
    }
    catch {
        Write-Check "Display adapter" "WARN" "could not read adapter and driver information"
    }
}

Write-Host ""
Write-Host ("Summary: {0} failure(s), {1} warning(s)." -f $Failures, $Warnings)
if ($ExportReport) {
    $ReportDirectory = Join-Path $Root "runtime\diagnostics"
    $ReportPath = Join-Path $ReportDirectory "localface-diagnostics.json"
    New-Item -ItemType Directory -Path $ReportDirectory -Force | Out-Null
    $Report = [ordered]@{
        schema_version = 1
        generated_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
        full_model_hash = [bool]$FullModelHash
        failures = $Failures
        warnings = $Warnings
        checks = $Checks
        privacy_note = "No images, face data, task identifiers, username, hostname, or local paths are included."
    }
    $Report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
    Write-Host ("Privacy-safe report saved to: {0}" -f $ReportPath)
}
if ($Failures -gt 0) {
    exit 1
}
exit 0
