# Build Junior's per-user Windows installer from the verified desktop bundle.

[CmdletBinding()]
param(
    [string]$CompilerPath
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$bundleScript = Join-Path $projectRoot "scripts\build_windows.ps1"
$installerScript = Join-Path $projectRoot "packaging\windows\junior-installer.iss"

if (-not $CompilerPath) {
    $candidates = @(
        (Join-Path $projectRoot ".tools\innosetup-7.0.2\ISCC.exe"),
        "${env:ProgramFiles}\Inno Setup 7\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    )
    $CompilerPath = $candidates |
        Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
        Select-Object -First 1
}

if (-not $CompilerPath) {
    throw "Inno Setup ISCC.exe was not found. Install Inno Setup or pass -CompilerPath."
}

& $bundleScript
if ($LASTEXITCODE -ne 0) {
    throw "The Windows application bundle failed."
}

& $CompilerPath $installerScript
if ($LASTEXITCODE -ne 0) {
    throw "The Windows installer build failed."
}

$installerPath = Join-Path $projectRoot "artifacts\installer\Junior-Setup-0.2.0-RC6-build-1.6.exe"
if (-not (Test-Path -LiteralPath $installerPath -PathType Leaf)) {
    throw "The installer compiler did not produce the expected setup file."
}

Write-Host "Windows installer created:"
Write-Host $installerPath
