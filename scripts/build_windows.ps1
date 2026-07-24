# Build a clean Windows desktop bundle without reading or packaging user data.

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$specPath = Join-Path $projectRoot "packaging\windows\junior.spec"
$workPath = Join-Path $projectRoot "build\pyinstaller"
$distributionPath = Join-Path $projectRoot "artifacts\windows"

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "The repository-local Python interpreter was not found: $pythonPath"
}

& $pythonPath -m PyInstaller `
    --clean `
    --noconfirm `
    --workpath $workPath `
    --distpath $distributionPath `
    $specPath

if ($LASTEXITCODE -ne 0) {
    throw "The Windows package build failed."
}

$executablePath = Join-Path $distributionPath "Junior\Junior.exe"
if (-not (Test-Path -LiteralPath $executablePath -PathType Leaf)) {
    throw "The build completed without producing Junior.exe."
}

Write-Host "Windows bundle created:"
Write-Host $executablePath
