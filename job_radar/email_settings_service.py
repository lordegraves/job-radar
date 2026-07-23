"""Validate and atomically save email settings without writing the password."""

import os
import smtplib
import socket
import ssl
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from job_radar.config import ConfigError, load_settings, load_yaml_file
from job_radar.credential_store import (
    CredentialStoreError,
    delete_credential,
    get_credential,
    store_credential,
)


TLS_MODES = {"starttls", "ssl", "none"}
PROVIDER_DEFAULTS = {
    "gmail": ("smtp.gmail.com", 587, "starttls"),
    "outlook": ("smtp-mail.outlook.com", 587, "starttls"),
}


@dataclass(frozen=True)
class EmailSettingsForm:
    """Represent safe form values without containing the credential."""

    enabled: bool
    provider: str
    sender: str
    sender_name: str
    recipients: tuple[str, ...]
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_tls_mode: str
    credential_saved: bool
    credential_status: str


class EmailSettingsError(ValueError):
    """Explain an email setup problem without exposing credential values."""


def load_email_settings_form(settings_path: str | Path) -> EmailSettingsForm:
    """Load the current safe email fields and credential availability."""

    email = load_settings(settings_path).email
    credential_saved = False
    if email.smtp_credential_key:
        try:
            credential_saved = get_credential(email.smtp_credential_key) is not None
        except CredentialStoreError:
            credential_saved = False
    elif email.smtp_password_env:
        credential_saved = bool(os.environ.get(email.smtp_password_env))
    return EmailSettingsForm(
        enabled=email.enabled,
        provider=email.smtp_provider,
        sender=email.sender,
        sender_name=email.sender_name,
        recipients=email.recipients,
        smtp_host=email.smtp_host,
        smtp_port=email.smtp_port,
        smtp_username=email.smtp_username,
        smtp_tls_mode=email.smtp_tls_mode,
        credential_saved=credential_saved,
        credential_status=_credential_status(email, credential_saved),
    )


def save_email_settings(
    settings_path: str | Path,
    *,
    enabled: bool,
    provider: str,
    sender: str,
    sender_name: str,
    recipients_text: str,
    smtp_host: str,
    smtp_port_text: str,
    smtp_username: str,
    smtp_tls_mode: str,
    credential: str,
) -> EmailSettingsForm:
    """Validate and atomically replace only the email settings section."""

    path = Path(settings_path)
    data = load_yaml_file(path)
    existing = load_settings(path).email
    recipients = _parse_recipients(recipients_text)
    smtp_host, port, smtp_tls_mode = _provider_settings(
        provider,
        smtp_host,
        smtp_port_text,
        smtp_tls_mode,
    )
    if smtp_tls_mode not in TLS_MODES:
        raise EmailSettingsError("Choose a supported email security mode.")

    credential_key = existing.smtp_credential_key
    password_env = existing.smtp_password_env
    previous_credential = None
    if credential:
        credential_key = f"smtp:{smtp_username.strip().lower()}"
        password_env = ""
        try:
            previous_credential = get_credential(credential_key)
        except CredentialStoreError as error:
            raise EmailSettingsError(str(error)) from error

    data["email"] = {
        "enabled": enabled,
        "sender": sender.strip(),
        "sender_name": sender_name.strip(),
        "recipients": list(recipients),
        "smtp_host": smtp_host.strip(),
        "smtp_port": port,
        "smtp_username": smtp_username.strip(),
        "smtp_password_env": password_env,
        "smtp_credential_key": credential_key,
        "smtp_provider": provider,
        "smtp_tls_mode": smtp_tls_mode,
    }
    temporary_path = _validated_temporary_settings(path, data)
    try:
        if credential:
            store_credential(credential_key, credential)
        os.replace(temporary_path, path)
    except (CredentialStoreError, OSError) as error:
        _restore_credential(credential_key, previous_credential, credential)
        temporary_path.unlink(missing_ok=True)
        raise EmailSettingsError(
            "Junior could not save email settings. The previous settings remain active."
        ) from error
    return load_email_settings_form(path)


def test_email_connection(
    settings_path: str | Path,
    *,
    provider: str,
    smtp_host: str,
    smtp_port_text: str,
    smtp_username: str,
    smtp_tls_mode: str,
    credential: str,
) -> str:
    """Test SMTP authentication without sending an email or exposing errors."""

    email = load_settings(settings_path).email
    host, port, tls_mode = _provider_settings(
        provider, smtp_host, smtp_port_text, smtp_tls_mode
    )
    password = credential
    if not password and email.smtp_credential_key:
        try:
            password = get_credential(email.smtp_credential_key) or ""
        except CredentialStoreError:
            return "Secure credential storage is unavailable"
    if not password and email.smtp_password_env:
        password = os.environ.get(email.smtp_password_env, "")
    if not password:
        return "Credential not configured"
    try:
        if tls_mode == "ssl":
            with smtplib.SMTP_SSL(host, port, timeout=15) as smtp:
                smtp.login(smtp_username.strip(), password)
        else:
            with smtplib.SMTP(host, port, timeout=15) as smtp:
                if tls_mode == "starttls":
                    smtp.starttls()
                smtp.login(smtp_username.strip(), password)
    except smtplib.SMTPAuthenticationError:
        return "Authentication failed"
    except ssl.SSLError:
        return "TLS negotiation failed"
    except (socket.gaierror, ConnectionError, TimeoutError, OSError):
        return "Server unreachable"
    except smtplib.SMTPException:
        return "TLS negotiation failed"
    return "Connection successful"


def _validated_temporary_settings(
    settings_path: Path,
    data: dict[str, Any],
) -> Path:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(
        prefix=f".{settings_path.name}.",
        suffix=".tmp",
        dir=settings_path.parent,
        text=True,
    )
    temporary_path = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as file:
            yaml.safe_dump(data, file, sort_keys=False)
            file.flush()
            os.fsync(file.fileno())
        load_settings(temporary_path)
    except (ConfigError, OSError, yaml.YAMLError) as error:
        temporary_path.unlink(missing_ok=True)
        raise EmailSettingsError(str(error)) from error
    return temporary_path


def _restore_credential(
    credential_key: str,
    previous_credential: str | None,
    new_credential: str,
) -> None:
    if not new_credential or not credential_key:
        return
    try:
        if previous_credential is None:
            delete_credential(credential_key)
        else:
            store_credential(credential_key, previous_credential)
    except CredentialStoreError:
        pass


def _parse_recipients(value: str) -> tuple[str, ...]:
    recipients = tuple(
        item.strip()
        for line in value.replace(",", "\n").splitlines()
        if (item := line.strip())
    )
    if any("@" not in item or " " in item for item in recipients):
        raise EmailSettingsError("Enter valid recipient email addresses.")
    return recipients


def _parse_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise EmailSettingsError("SMTP port must be a number.") from error
    if not 1 <= port <= 65535:
        raise EmailSettingsError("SMTP port must be between 1 and 65535.")
    return port


def _provider_settings(
    provider: str,
    host: str,
    port_text: str,
    tls_mode: str,
) -> tuple[str, int, str]:
    if provider in PROVIDER_DEFAULTS:
        return PROVIDER_DEFAULTS[provider]
    if provider != "custom":
        raise EmailSettingsError("Choose Gmail, Outlook, or Custom SMTP.")
    if tls_mode not in TLS_MODES:
        raise EmailSettingsError("Choose a supported email security mode.")
    if not host.strip():
        raise EmailSettingsError("Enter the SMTP server.")
    return host.strip(), _parse_port(port_text), tls_mode


def _credential_status(email, available: bool) -> str:
    if email.smtp_credential_key:
        return (
            "Stored securely in the operating system credential manager"
            if available
            else "No saved operating-system credential is available"
        )
    if email.smtp_password_env:
        return f"Using environment variable: {email.smtp_password_env}"
    return "No credential configured"
