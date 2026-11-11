param(
    [string]$Device = 'windows',
    [string]$DevHost = ''
)

$ErrorActionPreference = 'Stop'
$repoRoot = $PSScriptRoot
$backendDir = Join-Path $repoRoot 'backend'
$sceneDir = Join-Path $repoRoot 'frontend\assets\flight-map-3d'
$python = Join-Path $backendDir '.venv\Scripts\python.exe'
$logsDir = Join-Path $env:TEMP 'airspace-dev-logs'
$apiLog = Join-Path $logsDir 'backend.log'
$apiErrorLog = Join-Path $logsDir 'backend-error.log'
$sceneLog = Join-Path $logsDir 'scene.log'
$sceneErrorLog = Join-Path $logsDir 'scene-error.log'
$startedProcesses = [System.Collections.Generic.List[System.Diagnostics.Process]]::new()

if ([string]::IsNullOrWhiteSpace($DevHost)) {
    $DevHost = if ($Device -match 'android|emulator') { '10.0.2.2' } else { 'localhost' }
}

if (-not (Test-Path $python)) {
    throw "Backend environment is missing. Create it with: py -3.12 -m venv backend\.venv; backend\.venv\Scripts\python -m pip install -r backend\requirements-dev.txt"
}
if (-not (Test-Path (Join-Path $sceneDir 'node_modules'))) {
    throw 'Three.js dependencies are missing. Run npm install in frontend\assets\flight-map-3d.'
}

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

function Test-ServiceReady([string]$url) {
    try {
        Invoke-WebRequest -Uri $url -TimeoutSec 2 -UseBasicParsing | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Wait-ServiceReady(
    [string]$url,
    [System.Diagnostics.Process]$process,
    [string]$name,
    [string]$logPath,
    [string]$errorLogPath
) {
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($process.HasExited) {
            Get-Content $logPath, $errorLogPath -ErrorAction SilentlyContinue
            throw "$name stopped before becoming ready."
        }
        if (Test-ServiceReady $url) {
            return
        }
        Wait-Process -Id $process.Id -Timeout 1 -ErrorAction SilentlyContinue
    }
    Get-Content $logPath, $errorLogPath -ErrorAction SilentlyContinue
    throw "$name did not become ready at $url."
}

function Stop-ProcessTree([System.Diagnostics.Process]$process) {
    if ($null -ne $process -and -not $process.HasExited) {
        & taskkill.exe /PID $process.Id /T /F | Out-Null
    }
}

try {
    $env:AIRSPACE_CORS_ORIGINS = "http://${DevHost}:5173"

    if (Test-ServiceReady 'http://127.0.0.1:8000/health') {
        Write-Host 'Reusing backend at http://127.0.0.1:8000'
    } else {
        $backendProcess = Start-Process `
            -FilePath $python `
            -ArgumentList @('-m', 'uvicorn', 'main:app', '--host', '0.0.0.0', '--port', '8000') `
            -WorkingDirectory $backendDir `
            -RedirectStandardOutput $apiLog `
            -RedirectStandardError $apiErrorLog `
            -PassThru `
            -WindowStyle Hidden
        $startedProcesses.Add($backendProcess)
        Wait-ServiceReady 'http://127.0.0.1:8000/health' $backendProcess 'Backend' $apiLog $apiErrorLog
        Write-Host 'Backend ready at http://127.0.0.1:8000'
    }

    if (Test-ServiceReady 'http://127.0.0.1:5173/') {
        Write-Host 'Reusing Three.js dev server at http://127.0.0.1:5173'
    } else {
        $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
        $sceneProcess = Start-Process `
            -FilePath $npm `
            -ArgumentList @('run', 'dev', '--', '--host', '0.0.0.0', '--strictPort') `
            -WorkingDirectory $sceneDir `
            -RedirectStandardOutput $sceneLog `
            -RedirectStandardError $sceneErrorLog `
            -PassThru `
            -WindowStyle Hidden
        $startedProcesses.Add($sceneProcess)
        Wait-ServiceReady 'http://127.0.0.1:5173/' $sceneProcess 'Three.js dev server' $sceneLog $sceneErrorLog
        Write-Host 'Three.js ready at http://127.0.0.1:5173'
    }

    Write-Host "Starting Flutter on $Device (scene/API host: $DevHost). Ctrl+C stops Flutter and services started here."
    Push-Location (Join-Path $repoRoot 'frontend')
    try {
        & flutter run -d $Device "--dart-define=AIRSPACE_DEV_HOST=$DevHost"
        $flutterExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
} finally {
    foreach ($process in $startedProcesses) {
        Stop-ProcessTree $process
    }
}

if ($null -ne $flutterExitCode) {
    exit $flutterExitCode
}