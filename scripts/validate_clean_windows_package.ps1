# Validate the installed Windows executable without Python or repository state.

[CmdletBinding()]
param(
    [string]$InstallerPath = (
        Join-Path $PSScriptRoot "..\artifacts\installer\Junior-Setup-0.2.0-RC6-build-1.19.exe"
    )
)

$ErrorActionPreference = "Stop"
$resolvedInstaller = (Resolve-Path -LiteralPath $InstallerPath).Path
$validationRoot = Join-Path $env:TEMP (
    "junior-clean-windows-" + [guid]::NewGuid().ToString("N")
)
$installRoot = Join-Path $validationRoot "application"
$dataRoot = Join-Path $validationRoot "user-data"
$priorDataRoot = $env:JOB_RADAR_DATA_DIR
$priorPath = $env:PATH
$juniorProcess = $null

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

try {
    New-Item -ItemType Directory -Path $validationRoot | Out-Null
    $install = Start-Process -FilePath $resolvedInstaller -ArgumentList (
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/NOICONS",
        "/DIR=$installRoot"
    ) -WindowStyle Hidden -Wait -PassThru
    if ($install.ExitCode -ne 0) {
        throw "Clean Windows installation failed with exit code $($install.ExitCode)."
    }

    $juniorExecutable = Join-Path $installRoot "Junior.exe"
    if (-not (Test-Path -LiteralPath $juniorExecutable -PathType Leaf)) {
        throw "The clean Windows installation did not contain Junior.exe."
    }
    if (-not (Test-Path -LiteralPath (
        Join-Path $installRoot "LICENSE"
    ) -PathType Leaf)) {
        throw "The clean Windows installation did not contain LICENSE."
    }
    if (-not (Test-Path -LiteralPath (
        Join-Path $installRoot "PRIVACY.md"
    ) -PathType Leaf)) {
        throw "The clean Windows installation did not contain the privacy notice."
    }
    if (-not (Test-Path -LiteralPath (
        Join-Path $installRoot "SECURITY.md"
    ) -PathType Leaf)) {
        throw "The clean Windows installation did not contain the security policy."
    }
    if (-not (Test-Path -LiteralPath (
        Join-Path $installRoot "THIRD_PARTY_LICENSES.md"
    ) -PathType Leaf)) {
        throw "The clean Windows installation did not contain third-party notices."
    }
    if (-not (Test-Path -LiteralPath (
        Join-Path $installRoot "dependency-license-report.json"
    ) -PathType Leaf)) {
        throw "The clean Windows installation did not contain the dependency license report."
    }

    $port = Get-AvailablePort
    $env:JOB_RADAR_DATA_DIR = $dataRoot
    # The packaged executable must not inherit repository Python or developer
    # tools. Windows system paths remain available for operating-system DLLs.
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    $juniorProcess = Start-Process -FilePath $juniorExecutable -ArgumentList (
        "--no-browser",
        "--port",
        "$port"
    ) -WorkingDirectory $validationRoot -WindowStyle Hidden -PassThru

    $url = "http://127.0.0.1:$port/"
    $deadline = (Get-Date).AddSeconds(30)
    $page = $null
    while ((Get-Date) -lt $deadline) {
        if ($juniorProcess.HasExited) {
            throw "The packaged Windows application stopped before becoming ready."
        }
        try {
            $page = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
            break
        }
        catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if ($null -eq $page -or $page.StatusCode -ne 200) {
        throw "The packaged Windows application did not become ready."
    }
    if ($page.Content -notmatch "Welcome to junior") {
        throw "A clean packaged launch did not open guided setup."
    }
    if (-not (Test-Path -LiteralPath (
        Join-Path $dataRoot "data\job_radar.sqlite3"
    ) -PathType Leaf)) {
        throw "A clean packaged launch did not create its isolated database."
    }

    Stop-Process -Id $juniorProcess.Id -Force
    $juniorProcess.WaitForExit()
    $juniorProcess = $null

    $sentinel = Join-Path $dataRoot "clean-package-sentinel.txt"
    Set-Content -LiteralPath $sentinel -Value "preserve" -Encoding UTF8

    $uninstaller = Join-Path $installRoot "unins000.exe"
    $uninstall = Start-Process -FilePath $uninstaller -ArgumentList (
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART"
    ) -WindowStyle Hidden -Wait -PassThru
    if ($uninstall.ExitCode -ne 0) {
        throw "Clean Windows uninstall failed with exit code $($uninstall.ExitCode)."
    }
    if (Test-Path -LiteralPath $juniorExecutable) {
        throw "Clean Windows uninstall left Junior.exe behind."
    }
    if ((Get-Content -LiteralPath $sentinel -Raw).Trim() -ne "preserve") {
        throw "Clean Windows uninstall changed isolated user data."
    }

    Write-Host "Clean Windows package validation passed."
}
finally {
    if ($null -ne $juniorProcess -and -not $juniorProcess.HasExited) {
        Stop-Process -Id $juniorProcess.Id -Force
    }
    $env:JOB_RADAR_DATA_DIR = $priorDataRoot
    $env:PATH = $priorPath
    if (Test-Path -LiteralPath $validationRoot) {
        Remove-Item -LiteralPath $validationRoot -Recurse -Force
    }
}
