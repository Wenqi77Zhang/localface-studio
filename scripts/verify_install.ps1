$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Diagnostics = Join-Path $PSScriptRoot "diagnose.ps1"
$ReportDirectory = Join-Path $Root "runtime\diagnostics"
$ReportPath = Join-Path $ReportDirectory "install-verification.json"

function Test-FreeLoopbackPort {
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

function Find-FreeLoopbackPort {
    param([int]$Start)
    foreach ($Port in $Start..($Start + 99)) {
        if (Test-FreeLoopbackPort $Port) {
            return $Port
        }
    }
    throw "No free verification port was found."
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "The project environment is missing. Run setup.cmd first."
}

Write-Host "Step 1/2: full privacy-safe environment and model verification"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Diagnostics -FullModelHash -ExportReport
if ($LASTEXITCODE -ne 0) {
    throw "Environment diagnostics failed. Read runtime\diagnostics\localface-diagnostics.json."
}

$BackendPort = Find-FreeLoopbackPort 18000
$FrontendPort = Find-FreeLoopbackPort ($BackendPort + 1)
Write-Host "Step 2/2: bounded frontend, security-header, API-proxy, and shutdown verification"
$SmokeOutput = @(& $Python (Join-Path $PSScriptRoot "verify_frontend.py") --backend-port $BackendPort --frontend-port $FrontendPort)
if ($LASTEXITCODE -ne 0) {
    throw "The local product startup verification failed."
}
$SmokeLine = $SmokeOutput | Where-Object { $_ -like '*"frontend":"ok"*' } | Select-Object -Last 1
if ([string]::IsNullOrWhiteSpace($SmokeLine)) {
    throw "The startup verification did not return a valid result."
}
$Smoke = $SmokeLine | ConvertFrom-Json

New-Item -ItemType Directory -Path $ReportDirectory -Force | Out-Null
$Report = [ordered]@{
    schema_version = 1
    generated_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
    environment_and_models = "ok"
    frontend = [string]$Smoke.frontend
    api_proxy = [string]$Smoke.api_proxy
    clean_shutdown = "ok"
    manual_real_swap_required = $true
    privacy_note = "No images, face data, task identifiers, username, hostname, ports, or local paths are included."
}
$Report | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
Write-Host "Installation verification passed."
Write-Host ("Privacy-safe evidence saved to: {0}" -f $ReportPath)
