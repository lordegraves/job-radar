# Build and export the Linux tarball without exposing user-owned repository data.
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$dockerfile = Join-Path $projectRoot "packaging\linux\Dockerfile"
$artifactRoot = Join-Path $projectRoot "artifacts\linux"

docker info --format "{{.OSType}}/{{.Architecture}}" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop's Linux engine is not available."
}

New-Item -ItemType Directory -Force -Path $artifactRoot | Out-Null
docker build `
    --file $dockerfile `
    --target artifact `
    --output "type=local,dest=$artifactRoot" `
    $projectRoot
if ($LASTEXITCODE -ne 0) {
    throw "The Linux package build failed."
}

$archive = Join-Path $artifactRoot "Junior-linux-x86_64.tar.gz"
if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {
    throw "The Linux build completed without producing the expected tarball."
}

Write-Host "Linux tarball created:"
Write-Host $archive
