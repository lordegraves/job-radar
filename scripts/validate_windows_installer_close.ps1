# Verify a manual repair closes only the isolated Junior process holding its files.

[CmdletBinding()]
param(
    [string]$CompilerPath
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$sourceScript = Join-Path $projectRoot "packaging\windows\junior-installer.iss"
$validationRoot = Join-Path $env:TEMP (
    "junior-close-validation-" + [guid]::NewGuid().ToString("N")
)
$installRoot = Join-Path $validationRoot "application"
$dataRoot = Join-Path $validationRoot "user-data"
$validationScript = Join-Path $validationRoot "junior-installer-close-test.iss"
$validationInstaller = Join-Path $validationRoot "Junior-Close-Test.exe"
$priorDataRoot = $env:JOB_RADAR_DATA_DIR
$juniorProcess = $null
$uninstaller = $null

if (-not $CompilerPath) {
    $CompilerPath = @(
        (Join-Path $projectRoot ".tools\innosetup-7.0.2\ISCC.exe"),
        "${env:ProgramFiles}\Inno Setup 7\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    ) | Where-Object {
        $_ -and (Test-Path -LiteralPath $_ -PathType Leaf)
    } | Select-Object -First 1
}
if (-not $CompilerPath) {
    throw "Inno Setup ISCC.exe was not found."
}

function Invoke-ValidationSetup {
    param([switch]$CloseApplications)

    $closeArgument = if ($CloseApplications) {
        "/CLOSEAPPLICATIONS"
    }
    else {
        "/NOCLOSEAPPLICATIONS"
    }
    $setup = Start-Process -FilePath $validationInstaller -ArgumentList (
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/LOG=$validationRoot\setup.log",
        $closeArgument,
        "/NORESTARTAPPLICATIONS",
        "/NOICONS",
        "/DIR=$installRoot"
    ) -WindowStyle Hidden -Wait -PassThru
    if ($setup.ExitCode -ne 0) {
        if (Test-Path -LiteralPath (Join-Path $validationRoot "setup.log")) {
            Get-Content -LiteralPath (Join-Path $validationRoot "setup.log") `
                -Tail 35 | Write-Host
        }
        throw "Validation installer returned exit code $($setup.ExitCode)."
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

try {
    New-Item -ItemType Directory -Path $validationRoot -Force | Out-Null
    $validationGuid = [guid]::NewGuid().ToString().ToUpperInvariant()
    $scriptText = Get-Content -LiteralPath $sourceScript -Raw
    $scriptText = $scriptText.Replace(
        "CB6B32BA-8BC0-4CC0-A14D-0C12864035B1",
        $validationGuid
    )
    $scriptText = $scriptText.Replace(
        "OutputDir=..\..\artifacts\installer",
        "OutputDir=$validationRoot"
    )
    $scriptText = $scriptText.Replace(
        "OutputBaseFilename=Junior-Setup-{#AppVersion}-{#BuildSlug}",
        "OutputBaseFilename=Junior-Close-Test"
    )
    $scriptText = $scriptText.Replace("..\..\", "$projectRoot\")
    Set-Content -LiteralPath $validationScript -Value $scriptText -Encoding UTF8

    & $CompilerPath $validationScript | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $validationInstaller)) {
        throw "The validation-only installer did not build."
    }

    Invoke-ValidationSetup
    $marker = Join-Path $dataRoot "preservation-marker.txt"
    New-Item -ItemType Directory -Path $dataRoot -Force | Out-Null
    Set-Content -LiteralPath $marker -Value "preserve" -Encoding UTF8

    $env:JOB_RADAR_DATA_DIR = $dataRoot
    $port = Get-AvailablePort
    $juniorExecutable = Join-Path $installRoot "Junior.exe"
    $juniorProcess = Start-Process -FilePath $juniorExecutable -ArgumentList (
        "--port",
        "$port"
    ) -WorkingDirectory $validationRoot -WindowStyle Hidden -PassThru

    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        if ($juniorProcess.HasExited) {
            throw "The isolated Junior process stopped before the repair test."
        }
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/" `
                -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                break
            }
        }
        catch {
            Start-Sleep -Milliseconds 250
        }
    }

    Invoke-ValidationSetup -CloseApplications
    $juniorProcess.WaitForExit(15000) | Out-Null
    if (-not $juniorProcess.HasExited) {
        throw "Setup did not close the isolated running Junior process."
    }
    $juniorProcess = $null
    if ((Get-Content -LiteralPath $marker -Raw).Trim() -ne "preserve") {
        throw "The repair changed isolated user-owned data."
    }

    $uninstaller = Join-Path $installRoot "unins000.exe"
    $uninstall = Start-Process -FilePath $uninstaller -ArgumentList (
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART"
    ) -WindowStyle Hidden -Wait -PassThru
    if ($uninstall.ExitCode -ne 0) {
        throw "Validation uninstall returned exit code $($uninstall.ExitCode)."
    }
    Write-Host "Windows installer clean-close validation passed."
}
finally {
    if ($null -ne $juniorProcess -and -not $juniorProcess.HasExited) {
        Stop-Process -Id $juniorProcess.Id -Force
    }
    $env:JOB_RADAR_DATA_DIR = $priorDataRoot
    if (Test-Path -LiteralPath $validationRoot) {
        Remove-Item -LiteralPath $validationRoot -Recurse -Force
    }
}
