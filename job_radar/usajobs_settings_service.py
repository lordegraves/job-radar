"""Manage USAJOBS API identity while keeping its key in the OS keyring."""

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Any

import requests
import yaml

from job_radar.config import ConfigError, load_settings, load_yaml_file
from job_radar.credential_store import (
    CredentialStoreError,
    delete_credential,
    get_credential,
    store_credential,
)


USAJOBS_CREDENTIAL_REFERENCE = "usajobs:authorization-key"
USAJOBS_SEARCH_URL = "https://data.usajobs.gov/api/Search"


class UsaJobsSettingsError(ValueError):
    """Explain a safe, user-correctable USAJOBS configuration problem."""


@dataclass(frozen=True)
class UsaJobsSettingsForm:
    contact_email: str
    credential_saved: bool

    @property
    def status(self) -> str:
        if self.contact_email and self.credential_saved:
            return "Configured"
        return "API access required"


def load_usajobs_settings_form(settings_path: str | Path) -> UsaJobsSettingsForm:
    settings = load_settings(settings_path).usajobs
    saved = False
    if settings.credential_key:
        try:
            saved = bool(get_credential(settings.credential_key))
        except CredentialStoreError:
            saved = False
    return UsaJobsSettingsForm(
        contact_email=settings.contact_email,
        credential_saved=saved,
    )


def save_usajobs_settings(
    settings_path: str | Path,
    *,
    contact_email: str,
    authorization_key: str,
) -> UsaJobsSettingsForm:
    """Atomically save the public identity and keep the secret in keyring."""

    email = contact_email.strip()
    if not email or "@" not in email or email.startswith("@") or email.endswith("@"):
        raise UsaJobsSettingsError("Enter the email address registered with USAJOBS.")
    path = Path(settings_path)
    current = load_settings(path).usajobs
    reference = current.credential_key or USAJOBS_CREDENTIAL_REFERENCE
    try:
        previous = get_credential(reference)
    except CredentialStoreError as error:
        raise UsaJobsSettingsError(str(error)) from error
    if not authorization_key.strip() and not previous:
        raise UsaJobsSettingsError("Enter the authorization key issued by USAJOBS.")

    data = load_yaml_file(path)
    data["usajobs"] = {
        "contact_email": email,
        "credential_key": reference,
    }
    temporary = _validated_temporary_settings(path, data)
    try:
        if authorization_key.strip():
            store_credential(reference, authorization_key.strip())
        os.replace(temporary, path)
    except (CredentialStoreError, OSError) as error:
        if authorization_key.strip():
            try:
                if previous:
                    store_credential(reference, previous)
                else:
                    delete_credential(reference)
            except CredentialStoreError:
                pass
        temporary.unlink(missing_ok=True)
        raise UsaJobsSettingsError(
            "Junior could not save USAJOBS access. The previous settings remain active."
        ) from error
    return load_usajobs_settings_form(path)


def remove_usajobs_settings(settings_path: str | Path) -> UsaJobsSettingsForm:
    """Remove the keyring secret and its non-secret settings reference."""

    path = Path(settings_path)
    current = load_settings(path).usajobs
    previous = None
    if current.credential_key:
        try:
            previous = get_credential(current.credential_key)
        except CredentialStoreError as error:
            raise UsaJobsSettingsError(str(error)) from error
    data = load_yaml_file(path)
    data["usajobs"] = {"contact_email": "", "credential_key": ""}
    temporary = _validated_temporary_settings(path, data)
    try:
        if current.credential_key:
            delete_credential(current.credential_key)
        os.replace(temporary, path)
    except (CredentialStoreError, OSError) as error:
        if current.credential_key and previous:
            try:
                store_credential(current.credential_key, previous)
            except CredentialStoreError:
                pass
        temporary.unlink(missing_ok=True)
        raise UsaJobsSettingsError(
            "Junior could not remove USAJOBS access. Try again before scanning."
        ) from error
    return load_usajobs_settings_form(path)


def test_usajobs_settings(settings_path: str | Path) -> str:
    """Verify saved API access with one bounded public search request."""

    settings = load_settings(settings_path).usajobs
    if not settings.contact_email or not settings.credential_key:
        raise UsaJobsSettingsError(
            "Save the USAJOBS contact email and authorization key before testing."
        )
    try:
        key = get_credential(settings.credential_key)
    except CredentialStoreError as error:
        raise UsaJobsSettingsError(str(error)) from error
    if not key:
        raise UsaJobsSettingsError(
            "The USAJOBS authorization key is not available. Save it again in Settings."
        )
    try:
        response = requests.get(
            USAJOBS_SEARCH_URL,
            headers={
                "Host": "data.usajobs.gov",
                "User-Agent": settings.contact_email,
                "Authorization-Key": key,
            },
            params={"ResultsPerPage": 1, "Keyword": "JuniorCredentialCheck"},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        raise UsaJobsSettingsError(
            "USAJOBS did not accept the saved API access. Check the registered email and key."
        ) from error
    if not isinstance(payload, dict) or not isinstance(payload.get("SearchResult"), dict):
        raise UsaJobsSettingsError(
            "USAJOBS returned an unexpected response. The saved values were not changed."
        )
    return "USAJOBS API access is working."


def _validated_temporary_settings(
    settings_path: Path,
    data: dict[str, Any],
) -> Path:
    descriptor, name = tempfile.mkstemp(
        prefix=f".{settings_path.name}.",
        suffix=".tmp",
        dir=settings_path.parent,
        text=True,
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            yaml.safe_dump(data, stream, sort_keys=False)
            stream.flush()
            os.fsync(stream.fileno())
        load_settings(temporary)
    except (ConfigError, OSError, yaml.YAMLError) as error:
        temporary.unlink(missing_ok=True)
        raise UsaJobsSettingsError(str(error)) from error
    return temporary
