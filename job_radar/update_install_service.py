"""Download and verify an official Junior installer before launching it."""

from collections.abc import Callable
import hashlib
import hmac
from pathlib import Path
import re
import subprocess
from typing import Any

import requests

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
    popen: Callable[..., Any] = subprocess.Popen,
) -> None:
    """Start the verified installer without invoking a command shell."""

    try:
        popen(
            [
                str(installer_path),
                "/SILENT",
                "/CLOSEAPPLICATIONS",
                "/NORESTART",
                "/AUTOLAUNCH",
            ],
            close_fds=True,
        )
    except OSError as error:
        raise UpdateInstallError(
            "Junior verified the update but Windows could not start the installer."
        ) from error


def _bounded_content(response: Any, maximum: int) -> bytes:
    content = response.content
    if not isinstance(content, bytes) or len(content) > maximum:
        raise UpdateInstallError("Junior rejected an invalid checksum file.")
    return content


def _digest_for_file(checksum_text: str, installer_name: str) -> str:
    pattern = re.compile(
        rf"^(?P<digest>[0-9a-fA-F]{{64}})\s+\*?{re.escape(installer_name)}$",
        re.MULTILINE,
    )
    match = pattern.search(checksum_text)
    if match is None:
        raise UpdateInstallError(
            "The release checksum does not identify the expected installer."
        )
    return match.group("digest").lower()
