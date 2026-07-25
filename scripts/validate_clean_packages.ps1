# Validate Windows and Linux artifacts without source-tree runtime dependencies.

[CmdletBinding()]
param(
    [switch]$SkipPackageBuild
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$windowsValidation = Join-Path (
    $projectRoot
) "scripts\validate_clean_windows_package.ps1"
$linuxValidation = Join-Path (
    $projectRoot
) "scripts\validate_clean_linux_package.sh"
$linuxArchive = Join-Path (
    $projectRoot
) "artifacts\linux\Junior-linux-x86_64.tar.gz"

if (-not $SkipPackageBuild) {
    & (Join-Path $projectRoot "scripts\build_windows_installer.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "The Windows installer build failed."
    }
    & (Join-Path $projectRoot "scripts\build_linux_tarball.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "The Linux archive build failed."
    }
}

& $windowsValidation
if (-not $?) {
    throw "Clean Windows package validation failed."
}

if (-not (Test-Path -LiteralPath $linuxArchive -PathType Leaf)) {
    & (Join-Path $projectRoot "scripts\build_linux_tarball.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "The Linux archive build failed."
    }
}

$archiveMount = "$($linuxArchive):/input/Junior-linux-x86_64.tar.gz:ro"
$scriptMount = "$($linuxValidation):/validate-clean-linux.sh:ro"
docker run --rm `
    --volume $archiveMount `
    --volume $scriptMount `
    debian:bookworm-slim `
    sh /validate-clean-linux.sh
if ($LASTEXITCODE -ne 0) {
    throw "Clean Linux package validation failed."
}

Write-Host "Clean Windows and Linux package validation passed."
