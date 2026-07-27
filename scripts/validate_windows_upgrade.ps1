# Verify install, repair/upgrade, and uninstall never change user-owned files.

[CmdletBinding()]
param(
    [string]$InstallerPath = (
        Join-Path $PSScriptRoot "..\artifacts\installer\Junior-Setup-0.2.0-SP5-build-1.6.exe"
    )
)

$ErrorActionPreference = "Stop"
$resolvedInstaller = (Resolve-Path -LiteralPath $InstallerPath).Path
$validationRoot = Join-Path $env:TEMP (
    "junior-installer-validation-" + [guid]::NewGuid().ToString("N")
)
$installRoot = Join-Path $validationRoot "application"
$dataRoot = Join-Path $validationRoot "user-data"

$representativeFiles = @{
    "config\settings.yaml" = "settings-preservation-sentinel"
    "config\target-companies.yaml" = "company-config-preservation-sentinel"
    "profiles\profile_example\profile.yaml" = "profile-preservation-sentinel"
    "resumes\profile_example\resume.md" = "resume-preservation-sentinel"
    "data\job_radar.sqlite3" = "database-preservation-sentinel"
    "reports\latest.html" = "report-preservation-sentinel"
    "backups\before-upgrade.zip" = "backup-preservation-sentinel"
    "runtime\schedule.json" = "schedule-preservation-sentinel"
    "runtime\credential-reference.txt" = "credential-reference-only"
}

function Get-UserDataHashes {
    param([string]$Root)

    $hashes = @{}
    Get-ChildItem -LiteralPath $Root -File -Recurse | ForEach-Object {
        $relativePath = $_.FullName.Substring($Root.Length + 1)
        $hashes[$relativePath] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
    }
    return $hashes
}

function Assert-HashesEqual {
    param(
        [hashtable]$Expected,
        [hashtable]$Actual,
        [string]$Stage
    )

    if ($Expected.Count -ne $Actual.Count) {
        throw "$Stage changed the number of user-owned files."
    }
    foreach ($path in $Expected.Keys) {
        if (-not $Actual.ContainsKey($path) -or $Actual[$path] -ne $Expected[$path]) {
            throw "$Stage changed user-owned data: $path"
        }
    }
}

function Invoke-Setup {
    $process = Start-Process -FilePath $resolvedInstaller -ArgumentList (
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/NOICONS",
        "/DIR=$installRoot"
    ) -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Installer returned exit code $($process.ExitCode)."
    }
}

try {
    foreach ($relativePath in $representativeFiles.Keys) {
        $path = Join-Path $dataRoot $relativePath
        New-Item -ItemType Directory -Path (Split-Path $path) -Force | Out-Null
        Set-Content -LiteralPath $path -Value $representativeFiles[$relativePath] -Encoding UTF8
    }
    $before = Get-UserDataHashes -Root $dataRoot

    Invoke-Setup
    if (-not (Test-Path -LiteralPath (
        Join-Path $installRoot "LICENSE"
    ) -PathType Leaf)) {
        throw "Initial install did not include LICENSE."
    }
    if (-not (Test-Path -LiteralPath (
        Join-Path $installRoot "PRIVACY.md"
    ) -PathType Leaf)) {
        throw "Initial install did not include the privacy notice."
    }
    if (-not (Test-Path -LiteralPath (
        Join-Path $installRoot "SECURITY.md"
    ) -PathType Leaf)) {
        throw "Initial install did not include the security policy."
    }
    if (-not (Test-Path -LiteralPath (
        Join-Path $installRoot "THIRD_PARTY_LICENSES.md"
    ) -PathType Leaf)) {
        throw "Initial install did not include third-party notices."
    }
    if (-not (Test-Path -LiteralPath (
        Join-Path $installRoot "dependency-license-report.json"
    ) -PathType Leaf)) {
        throw "Initial install did not include the dependency license report."
    }
    Assert-HashesEqual -Expected $before -Actual (
        Get-UserDataHashes -Root $dataRoot
    ) -Stage "Initial install"

    Invoke-Setup
    if (-not (Test-Path -LiteralPath (
        Join-Path $installRoot "LICENSE"
    ) -PathType Leaf)) {
        throw "Repair or upgrade did not preserve LICENSE."
    }
    if (-not (Test-Path -LiteralPath (
        Join-Path $installRoot "PRIVACY.md"
    ) -PathType Leaf)) {
        throw "Repair or upgrade did not preserve the privacy notice."
    }
    if (-not (Test-Path -LiteralPath (
        Join-Path $installRoot "SECURITY.md"
    ) -PathType Leaf)) {
        throw "Repair or upgrade did not preserve the security policy."
    }
    if (-not (Test-Path -LiteralPath (
        Join-Path $installRoot "THIRD_PARTY_LICENSES.md"
    ) -PathType Leaf)) {
        throw "Repair or upgrade did not preserve third-party notices."
    }
    if (-not (Test-Path -LiteralPath (
        Join-Path $installRoot "dependency-license-report.json"
    ) -PathType Leaf)) {
        throw "Repair or upgrade did not preserve the dependency license report."
    }
    Assert-HashesEqual -Expected $before -Actual (
        Get-UserDataHashes -Root $dataRoot
    ) -Stage "Repair or upgrade"

    $uninstaller = Join-Path $installRoot "unins000.exe"
    $uninstall = Start-Process -FilePath $uninstaller -ArgumentList (
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART"
    ) -WindowStyle Hidden -Wait -PassThru
    if ($uninstall.ExitCode -ne 0) {
        throw "Uninstaller returned exit code $($uninstall.ExitCode)."
    }
    Assert-HashesEqual -Expected $before -Actual (
        Get-UserDataHashes -Root $dataRoot
    ) -Stage "Uninstall"
    if (Test-Path -LiteralPath (Join-Path $installRoot "Junior.exe")) {
        throw "Uninstall left Junior.exe behind."
    }

    Write-Host "Windows install, repair/upgrade, and uninstall preservation passed."
}
finally {
    if (Test-Path -LiteralPath $validationRoot) {
        Remove-Item -LiteralPath $validationRoot -Recurse -Force
    }
}
