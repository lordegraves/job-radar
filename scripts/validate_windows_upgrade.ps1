# Verify install, repair/upgrade, and uninstall never change user-owned files.

[CmdletBinding()]
param(
    [string]$InstallerPath = (
        Join-Path $PSScriptRoot "..\artifacts\installer\Junior-Setup-0.2.0-RC6-build-1.6.exe"
    ),
    [string]$PreviousInstallerPath = (
        Join-Path $PSScriptRoot "..\artifacts\installer\Junior-Setup-0.2.0-SP5-build-1.12.exe"
    ),
    [switch]$KeepValidationFilesOnFailure
)

$ErrorActionPreference = "Stop"
$resolvedInstaller = (Resolve-Path -LiteralPath $InstallerPath).Path
$resolvedPreviousInstaller = (
    Resolve-Path -LiteralPath $PreviousInstallerPath
).Path
$validationRoot = Join-Path $env:TEMP (
    "junior-installer-validation-" + [guid]::NewGuid().ToString("N")
)
$installRoot = Join-Path $validationRoot "application"
$dataRoot = Join-Path $validationRoot "user-data"
$startupDataRoot = Join-Path $validationRoot "startup-user-data"
$priorDataRoot = $env:JOB_RADAR_DATA_DIR
$priorPath = $env:PATH
$juniorProcess = $null
$validationPassed = $false

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
    param([string]$SetupPath)

    $process = Start-Process -FilePath $SetupPath -ArgumentList (
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/NOCLOSEAPPLICATIONS",
        "/NORESTARTAPPLICATIONS",
        "/NOICONS",
        "/DIR=$installRoot"
    ) -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Installer returned exit code $($process.ExitCode)."
    }
}

function Get-AvailablePort {
    $listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Loopback,
        0
    )
    $listener.Start()
    try {
        return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    }
    finally {
        $listener.Stop()
    }
}

function Assert-PackagedApplicationStarts {
    $juniorExecutable = Join-Path $installRoot "Junior.exe"
    $port = Get-AvailablePort
    # Preservation sentinels are intentionally not valid Junior configuration
    # files. Start the upgraded package against a separate empty workspace so
    # this check measures packaged startup rather than sentinel parsing.
    $env:JOB_RADAR_DATA_DIR = $startupDataRoot
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    $script:juniorProcess = Start-Process -FilePath $juniorExecutable -ArgumentList (
        "--no-browser",
        "--port",
        "$port"
    ) -WorkingDirectory $validationRoot -WindowStyle Hidden -PassThru

    $deadline = (Get-Date).AddSeconds(30)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        if ($script:juniorProcess.HasExited) {
            throw "The upgraded Windows application stopped before becoming ready."
        }
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/" `
                -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                $ready = $true
                break
            }
        }
        catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $ready) {
        throw "The upgraded Windows application did not become ready."
    }
    Stop-Process -Id $script:juniorProcess.Id -Force
    $script:juniorProcess.WaitForExit()
    $script:juniorProcess = $null
}

function Remove-ValidationRoot {
    # Windows can retain a short-lived handle to a packaged extension after the
    # process exits. Retry only this isolated test directory so cleanup timing
    # cannot mask the result of the upgrade validation.
    for ($attempt = 1; $attempt -le 10; $attempt++) {
        try {
            Remove-Item -LiteralPath $validationRoot -Recurse -Force
            return
        }
        catch {
            if ($attempt -eq 10) {
                throw
            }
            Start-Sleep -Milliseconds 500
        }
    }
}

try {
    foreach ($relativePath in $representativeFiles.Keys) {
        $path = Join-Path $dataRoot $relativePath
        New-Item -ItemType Directory -Path (Split-Path $path) -Force | Out-Null
        Set-Content -LiteralPath $path -Value $representativeFiles[$relativePath] -Encoding UTF8
    }
    $before = Get-UserDataHashes -Root $dataRoot

    Invoke-Setup -SetupPath $resolvedPreviousInstaller
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

    Invoke-Setup -SetupPath $resolvedInstaller
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
    Assert-PackagedApplicationStarts

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
    $validationPassed = $true
}
finally {
    if ($null -ne $juniorProcess -and -not $juniorProcess.HasExited) {
        Stop-Process -Id $juniorProcess.Id -Force
    }
    $env:JOB_RADAR_DATA_DIR = $priorDataRoot
    $env:PATH = $priorPath
    if (
        (Test-Path -LiteralPath $validationRoot) -and
        ($validationPassed -or -not $KeepValidationFilesOnFailure)
    ) {
        Remove-ValidationRoot
    }
    elseif (Test-Path -LiteralPath $validationRoot) {
        Write-Host "Preserved failed validation files at: $validationRoot"
    }
}
