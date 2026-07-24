"""Check for a newer stable Junior release without changing the installation."""

from collections.abc import Callable
from dataclasses import asdict, dataclass
import re
from typing import Any
from urllib.parse import urlparse

import requests


LATEST_RELEASE_API = (
    "https://api.github.com/repos/lordegraves/job-radar/releases/latest"
)
_VERSION_PATTERN = re.compile(
    r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$"
)


@dataclass(frozen=True)
class UpdateCheckResult:
    """Contain only safe, user-facing update information."""

    status: str
    message: str
    available_version: str | None = None
    release_url: str | None = None

    def as_session_value(self) -> dict[str, str | None]:
        return asdict(self)


def check_for_stable_update(
    installed_version: str,
    *,
    request_get: Callable[..., Any] = requests.get,
) -> UpdateCheckResult:
    """Read GitHub's latest stable release without downloading or installing it."""

    try:
        response = request_get(
            LATEST_RELEASE_API,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"Junior/{installed_version}",
            },
            timeout=5,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return UpdateCheckResult(
            status="unavailable",
            message=(
                "Junior could not check for updates right now. Your installed "
                "version and data were not changed."
            ),
        )

    available_version = _normalized_version(payload.get("tag_name"))
    release_url = _safe_release_url(payload.get("html_url"))
    installed = _version_tuple(installed_version)
    available = _version_tuple(available_version)
    if available is None or release_url is None:
        return UpdateCheckResult(
            status="unavailable",
            message=(
                "Junior received release information it could not verify. Your "
                "installed version and data were not changed."
            ),
        )
    if installed is None:
        return UpdateCheckResult(
            status="unknown",
            message=(
                f"Junior found stable release {available_version}, but this "
                "development build cannot be compared with it."
            ),
            available_version=available_version,
            release_url=release_url,
        )
    if available > installed:
        return UpdateCheckResult(
            status="available",
            message=(
                f"Junior {available_version} is available. Junior will not "
                "download or install it automatically."
            ),
            available_version=available_version,
            release_url=release_url,
        )
    return UpdateCheckResult(
        status="current",
        message=f"Junior {installed_version} is the latest stable release.",
        available_version=available_version,
        release_url=release_url,
    )


def _normalized_version(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = _VERSION_PATTERN.fullmatch(value.strip())
    if match is None:
        return None
    return ".".join(
        (match.group("major"), match.group("minor"), match.group("patch"))
    )


def _version_tuple(value: str | None) -> tuple[int, int, int] | None:
    normalized = _normalized_version(value)
    if normalized is None:
        return None
    major, minor, patch = normalized.split(".")
    return int(major), int(minor), int(patch)


def _safe_release_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "github.com"
        or not parsed.path.startswith("/lordegraves/job-radar/releases/tag/")
    ):
        return None
    return value
