# Run Junior's automated release gate entirely against disposable test data.

[CmdletBinding()]
param(
    [string]$InstallerPath,
    [switch]$SkipInstallerBuild
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$installerBuild = Join-Path $projectRoot "scripts\build_windows_installer.ps1"
$installerValidation = Join-Path $projectRoot "scripts\validate_windows_upgrade.ps1"
$defaultInstaller = Join-Path (
    $projectRoot
) "artifacts\installer\Junior-Setup-0.2.0-RC6-build-1.3.exe"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Junior's repository-local Python interpreter was not found: $python"
}

Push-Location $projectRoot
try {
    Write-Host "1/5 Running the complete automated test suite..."
    & $python -m pytest -q tests
    if ($LASTEXITCODE -ne 0) {
        throw "The automated test suite failed."
    }

    Write-Host "2/5 Running Ruff..."
    & $python -m ruff check .
    if ($LASTEXITCODE -ne 0) {
        throw "Ruff validation failed."
    }

    Write-Host "3/5 Checking whitespace..."
    & git diff --check
    if ($LASTEXITCODE -ne 0) {
        throw "Git whitespace validation failed."
    }

    if (-not $SkipInstallerBuild) {
        Write-Host "4/5 Building a fresh Windows installer..."
        & $installerBuild
        if ($LASTEXITCODE -ne 0) {
            throw "The Windows installer build failed."
        }
        $InstallerPath = $defaultInstaller
    }
    elseif (-not $InstallerPath) {
        $InstallerPath = $defaultInstaller
        Write-Host "4/5 Using the existing Windows installer..."
    }
    else {
        Write-Host "4/5 Using the supplied Windows installer..."
    }

    $resolvedInstaller = (Resolve-Path -LiteralPath $InstallerPath).Path

    Write-Host "5/5 Verifying install, repair/upgrade, and uninstall..."
    & $installerValidation -InstallerPath $resolvedInstaller
    if ($LASTEXITCODE -ne 0) {
        throw "Windows installer lifecycle validation failed."
    }

    Write-Host ""
    Write-Host "Junior automated release validation passed."
    Write-Host "Validated installer: $resolvedInstaller"
    Write-Host (
        "The test suite covered clean package installation, first launch, " +
        "guided setup, scanning, restart, migration, backup, and restore."
    )
    Write-Host (
        "The installer check used synthetic sentinels for install, " +
        "repair/upgrade, uninstall, and user-data preservation."
    )
}
finally {
    Pop-Location
}
