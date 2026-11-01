param(
    [string]$Device = 'chrome',
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$FlutterArgs = @()
)

$ErrorActionPreference = 'Stop'
$sceneDirectory = Join-Path $PSScriptRoot 'assets/flight-map-3d'
$sceneEntry = Join-Path $sceneDirectory 'dist/build/index.html'
$viteCommand = Join-Path $sceneDirectory 'node_modules/.bin/vite.cmd'

Push-Location $sceneDirectory
try {
    if (-not (Test-Path -LiteralPath $viteCommand -PathType Leaf)) {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) {
            throw "npm ci failed (exit code $LASTEXITCODE)."
        }
    }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) {
        throw "Three.js production build failed (exit code $LASTEXITCODE)."
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $sceneEntry -PathType Leaf)) {
    throw "Flutter scene entry was not generated: $sceneEntry"
}

Push-Location $PSScriptRoot
try {
    & flutter pub get
    if ($LASTEXITCODE -ne 0) {
        throw "flutter pub get failed (exit code $LASTEXITCODE)."
    }

    & flutter run -d $Device @FlutterArgs
    if ($LASTEXITCODE -ne 0) {
        throw "flutter run failed (exit code $LASTEXITCODE)."
    }
}
finally {
    Pop-Location
}
