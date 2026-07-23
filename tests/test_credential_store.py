"""Verify secrets stay behind the operating-system credential-store boundary."""

import pytest
from keyring.errors import KeyringError, PasswordDeleteError

from job_radar.credential_store import (
    CredentialStoreError,
    delete_credential,
    get_credential,
    store_credential,
)
from job_radar.email_sender import get_email_readiness, send_email_report


class FakeCredentialBackend:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if self.values.pop((service, username), None) is None:
            raise PasswordDeleteError("missing")


class FailingCredentialBackend(FakeCredentialBackend):
    def get_password(self, service: str, username: str) -> str | None:
        raise KeyringError("private backend failure")


def test_credential_round_trip_uses_backend_without_returning_secret_on_save() -> None:
    backend = FakeCredentialBackend()

    result = store_credential(
        "smtp:user@example.com",
        "fictional-secret",
        backend=backend,
    )

    assert result is None
    assert get_credential(
        "smtp:user@example.com", backend=backend
    ) == "fictional-secret"
    assert delete_credential(
        "smtp:user@example.com", backend=backend
    ) is True
    assert delete_credential(
        "smtp:user@example.com", backend=backend
    ) is False


def test_backend_failure_is_sanitized() -> None:
    with pytest.raises(
        CredentialStoreError,
        match="credential manager is unavailable",
    ) as captured:
        get_credential(
            "smtp:user@example.com",
            backend=FailingCredentialBackend(),
        )

    assert "private backend failure" not in str(captured.value)


def test_email_can_use_non_secret_keyring_reference(monkeypatch) -> None:
    monkeypatch.setattr(
        "job_radar.email_sender.get_credential",
        lambda reference: "fictional-credential",
    )
    captured: dict[str, str] = {}

    def fake_send(*, email_settings, message, password):
        captured["password"] = password

    monkeypatch.setattr("job_radar.email_sender._send_smtp_message", fake_send)
    settings = {
        "enabled": True,
        "sender": "user@example.com",
        "sender_name": "junior",
        "recipients": ["user@example.com"],
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "user@example.com",
        "smtp_password_env": "",
        "smtp_credential_key": "smtp:user@example.com",
        "smtp_tls_mode": "starttls",
    }

    readiness = get_email_readiness(settings)
    result = send_email_report(settings, "Test report", "Test body")

    assert readiness.ready is True
    assert result.sent is True
    assert captured["password"] == "fictional-credential"
