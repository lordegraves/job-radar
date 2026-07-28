"""Download and verify an official Junior installer before launching it."""

import hashlib
import hmac
import json
import os
import re
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from job_radar import __build__, __version__
from job_radar.update_check_service import UpdateCheckResult

MAX_INSTALLER_BYTES = 250 * 1024 * 1024
MAX_CHECKSUM_BYTES = 16 * 1024


class UpdateInstallError(RuntimeError):
    """Describe an updater failure without exposing internal exception text."""


def download_verified_update(
    update: UpdateCheckResult,
    destination: Path,
    *,
    request_get: Callable[..., Any] = requests.get,
) -> Path:
    """Download the exact published installer and verify its SHA-256 digest."""

    if not (
        update.status == "available"
        and update.installer_name
        and update.installer_url
        and update.checksum_url
    ):
        raise UpdateInstallError(
            "This release does not include a complete verified Windows update."
        )
    installer_name = Path(update.installer_name).name
    if installer_name != update.installer_name or not installer_name.endswith(
        ".exe"
    ):
        raise UpdateInstallError("Junior rejected an unsafe installer name.")

    destination.mkdir(parents=True, exist_ok=True)
    installer_path = destination / installer_name
    partial_path = installer_path.with_suffix(".exe.part")
    try:
        checksum_response = request_get(
            update.checksum_url,
            headers={"User-Agent": "Junior updater"},
            timeout=15,
        )
        checksum_response.raise_for_status()
        checksum_text = _bounded_content(
            checksum_response,
            MAX_CHECKSUM_BYTES,
        ).decode("utf-8")
        expected_digest = _digest_for_file(checksum_text, installer_name)

        installer_response = request_get(
            update.installer_url,
            headers={"User-Agent": "Junior updater"},
            timeout=60,
            stream=True,
        )
        installer_response.raise_for_status()
        digest = hashlib.sha256()
        total = 0
        with partial_path.open("wb") as output:
            for chunk in installer_response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_INSTALLER_BYTES:
                    raise UpdateInstallError(
                        "The downloaded installer exceeded Junior's safety limit."
                    )
                digest.update(chunk)
                output.write(chunk)
        if total == 0 or not hmac.compare_digest(
            digest.hexdigest(),
            expected_digest,
        ):
            raise UpdateInstallError(
                "The downloaded installer did not match its published checksum."
            )
        partial_path.replace(installer_path)
        return installer_path
    except UpdateInstallError:
        partial_path.unlink(missing_ok=True)
        raise
    except (OSError, requests.RequestException, UnicodeError) as error:
        partial_path.unlink(missing_ok=True)
        raise UpdateInstallError(
            "Junior could not safely download and verify the update."
        ) from error


def launch_windows_installer(
    installer_path: Path,
    *,
    application_path: Path | None = None,
    result_path: Path | None = None,
    log_path: Path | None = None,
    expected_build: str = "the new build",
    parent_process_id: int | None = None,
    popen: Callable[..., Any] = subprocess.Popen,
) -> None:
    """Start a detached handoff that waits for Junior to close first."""

    process_id = parent_process_id or os.getpid()
    executable_path = application_path or Path(os.path.abspath(os.sys.executable))
    update_result_path = result_path or installer_path.with_name(
        "last-update-result.json"
    )
    update_result_path.parent.mkdir(parents=True, exist_ok=True)
    update_log_path = log_path or (
        update_result_path.parent.parent / "logs" / "junior-update.log"
    )
    update_log_path.parent.mkdir(parents=True, exist_ok=True)
    _append_update_event(
        update_log_path,
        event="update_handoff_prepared",
        status="starting",
        expected_build=expected_build,
    )
    helper_path = installer_path.with_name("junior-update-handoff.ps1")
    confirmation_path = installer_path.with_name(
        "junior-update-handoff.started"
    )
    confirmation_path.unlink(missing_ok=True)
    powershell_path = (
        Path(os.environ.get("SystemRoot", r"C:\Windows"))
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )
    helper_script = """\
param(
    [Parameter(Mandatory = $true)][int]$ParentProcessId,
    [Parameter(Mandatory = $true)][string]$InstallerPath,
    [Parameter(Mandatory = $true)][string]$HelperPath,
    [Parameter(Mandatory = $true)][string]$ConfirmationPath,
    [Parameter(Mandatory = $true)][string]$ApplicationPath,
    [Parameter(Mandatory = $true)][string]$ResultPath,
    [Parameter(Mandatory = $true)][string]$LogPath,
    [Parameter(Mandatory = $true)][string]$ExpectedBuild,
    [Parameter(Mandatory = $true)][string]$ApplicationVersion
)

function Write-SafeUpdateEvent {
    param(
        [Parameter(Mandatory = $true)][string]$EventName,
        [Parameter(Mandatory = $true)][string]$Status,
        [string]$Detail = ''
    )
    $Payload = @{
        application_build = $ExpectedBuild
        application_version = $ApplicationVersion
        event = $EventName
        schema_version = 1
        severity = $(if ($Status -eq 'failed') { 'error' } else { 'info' })
        status = $Status
        subsystem = 'update'
        timestamp = (Get-Date).ToUniversalTime().ToString('o')
    }
    if ($Detail) {
        $Payload.detail = $Detail
    }
    $Payload | ConvertTo-Json -Compress | Add-Content -LiteralPath $LogPath -Encoding UTF8
}

try {
    Set-Content -LiteralPath $ConfirmationPath -Value 'started' -Encoding UTF8
    Write-SafeUpdateEvent -EventName 'update_waiting_for_junior' -Status 'in_progress'
    # A packaged desktop launch can briefly include more than one Junior
    # process. Wait for the requested process and every remaining Junior
    # process so Setup never races a process still holding the executable.
    $ShutdownDeadline = (Get-Date).AddSeconds(45)
    while (
        (Get-Process -Id $ParentProcessId -ErrorAction SilentlyContinue) -or
        (Get-Process -Name 'Junior' -ErrorAction SilentlyContinue)
    ) {
        if ((Get-Date) -ge $ShutdownDeadline) {
            @{
                status = 'error'
                message = 'Junior could not close cleanly, so the update was not installed. Your existing installation and data were not changed.'
            } | ConvertTo-Json -Compress | Set-Content -LiteralPath $ResultPath -Encoding UTF8
            Write-SafeUpdateEvent -EventName 'update_waiting_for_junior' -Status 'failed' -Detail 'Junior did not close within 45 seconds.'
            if (Test-Path -LiteralPath $ApplicationPath) {
                Start-Process -FilePath $ApplicationPath
            }
            return
        }
        Start-Sleep -Milliseconds 250
    }
    # Give Windows a brief moment to release the desktop executable after the
    # verified parent process exits. Setup must never force-close Junior.
    Start-Sleep -Milliseconds 1000
    Write-SafeUpdateEvent -EventName 'update_installer_started' -Status 'in_progress'
    $Installer = Start-Process -FilePath $InstallerPath -ArgumentList @(
        '/SILENT',
        '/NORESTART',
        '/NOCLOSEAPPLICATIONS'
    ) -PassThru -Wait
    if ($Installer.ExitCode -eq 0) {
        $Result = @{
            status = 'success'
            message = "Junior was updated successfully to $ExpectedBuild."
        }
        Write-SafeUpdateEvent -EventName 'update_installer_finished' -Status 'success' -Detail 'Installer exit code 0.'
    }
    else {
        $Result = @{
            status = 'error'
            message = "The Junior update failed with installer exit code $($Installer.ExitCode). Your existing data was not removed."
        }
        Write-SafeUpdateEvent -EventName 'update_installer_finished' -Status 'failed' -Detail "Installer exit code $($Installer.ExitCode)."
    }
    $Result | ConvertTo-Json -Compress | Set-Content -LiteralPath $ResultPath -Encoding UTF8
    # The handoff owns restart ordering so the durable update result is in
    # place before the newly installed application reads it.
    if (Test-Path -LiteralPath $ApplicationPath) {
        Start-Process -FilePath $ApplicationPath
        Write-SafeUpdateEvent -EventName 'update_relaunch' -Status 'success'
    }
}
catch {
    @{
        status = 'error'
        message = 'Windows could not complete the Junior update. Your existing data was not removed.'
    } | ConvertTo-Json -Compress | Set-Content -LiteralPath $ResultPath -Encoding UTF8
    Write-SafeUpdateEvent -EventName 'update_handoff_failed' -Status 'failed' -Detail 'Windows could not complete the update handoff.'
    if (Test-Path -LiteralPath $ApplicationPath) {
        Start-Process -FilePath $ApplicationPath
    }
}
finally {
    Start-Sleep -Milliseconds 500
    Remove-Item -LiteralPath $ConfirmationPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $HelperPath -Force -ErrorAction SilentlyContinue
}
"""
    try:
        helper_path.write_text(helper_script, encoding="utf-8")
        helper_process = popen(
            [
                str(powershell_path),
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(helper_path),
                "-ParentProcessId",
                str(process_id),
                "-InstallerPath",
                str(installer_path),
                "-HelperPath",
                str(helper_path),
                "-ConfirmationPath",
                str(confirmation_path),
                "-ApplicationPath",
                str(executable_path),
                "-ResultPath",
                str(update_result_path),
                "-LogPath",
                str(update_log_path),
                "-ExpectedBuild",
                expected_build,
                "-ApplicationVersion",
                __version__,
            ],
            close_fds=True,
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_NO_WINDOW
            ),
        )
        confirmation_deadline = time.monotonic() + 3.0
        while (
            not confirmation_path.is_file()
            and time.monotonic() < confirmation_deadline
        ):
            if (
                helper_process is not None
                and helper_process.poll() is not None
            ):
                break
            time.sleep(0.05)
        if not confirmation_path.is_file():
            _append_update_event(
                update_log_path,
                event="update_handoff_launch_failed",
                status="failed",
                expected_build=expected_build,
            )
            helper_path.unlink(missing_ok=True)
            confirmation_path.unlink(missing_ok=True)
            raise UpdateInstallError(
                "Junior verified the update, but Windows did not start the "
                "installer handoff. Junior will remain open and your "
                "existing installation and data were not changed."
            )
    except OSError as error:
        _append_update_event(
            update_log_path,
            event="update_handoff_launch_failed",
            status="failed",
            expected_build=expected_build,
        )
        helper_path.unlink(missing_ok=True)
        confirmation_path.unlink(missing_ok=True)
        raise UpdateInstallError(
            "Junior verified the update but Windows could not prepare the "
            "installer handoff."
        ) from error


def _append_update_event(
    log_path: Path,
    *,
    event: str,
    status: str,
    expected_build: str,
) -> None:
    """Record only allowlisted updater state without paths or error text."""

    payload = {
        "schema_version": 1,
        "application_version": __version__,
        "application_build": __build__,
        "subsystem": "update",
        "severity": "error" if status == "failed" else "info",
        "event": event,
        "status": status,
        "expected_build": expected_build,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    with log_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, sort_keys=True) + "\n")


def _bounded_content(response: Any, maximum: int) -> bytes:
    content = response.content
    if not isinstance(content, bytes) or len(content) > maximum:
        raise UpdateInstallError("Junior rejected an invalid checksum file.")
    return content


def _digest_for_file(checksum_text: str, installer_name: str) -> str:
    pattern = re.compile(
        rf"^(?P<digest>[0-9a-fA-F]{{64}})\s+\*?{re.escape(installer_name)}\r?$",
        re.MULTILINE,
    )
    match = pattern.search(checksum_text)
    if match is None:
        raise UpdateInstallError(
            "The release checksum does not identify the expected installer."
        )
    return match.group("digest").lower()
