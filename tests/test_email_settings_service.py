"""Verify email setup validates and atomically saves only safe settings."""

from pathlib import Path
import smtplib
import ssl

import yaml

from job_radar.config import load_settings
from job_radar.email_settings_service import (
    save_email_settings,
    test_email_connection as check_email_connection,
)
from job_radar.web_app import create_app


def _write_settings(path: Path) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(
        """
database_path: data/junior.sqlite3
reports_path: reports
logs_path: logs
future_setting:
  preserved: true
email:
  enabled: false
  smtp_password_env: ""
  smtp_credential_key: ""
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_save_email_settings_preserves_unknowns_and_excludes_secret(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    _write_settings(settings_path)
    saved: dict[str, str] = {}
    monkeypatch.setattr(
        "job_radar.email_settings_service.get_credential",
        lambda reference: None,
    )
    monkeypatch.setattr(
        "job_radar.email_settings_service.store_credential",
        lambda reference, secret: saved.update(
            reference=reference, secret=secret
        ),
    )

    form = save_email_settings(
        settings_path,
        enabled=True,
        provider="gmail",
        sender="user@example.com",
        sender_name="Junior User",
        recipients_text="first@example.com\nsecond@example.com",
        smtp_host="smtp.example.com",
        smtp_port_text="587",
        smtp_username="user@example.com",
        smtp_tls_mode="starttls",
        credential="fictional-credential",
    )

    text = settings_path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert "fictional-credential" not in text
    assert data["future_setting"] == {"preserved": True}
    assert data["email"]["smtp_credential_key"] == "smtp:user@example.com"
    assert data["email"]["smtp_provider"] == "gmail"
    assert data["email"]["smtp_host"] == "smtp.gmail.com"
    assert data["email"]["smtp_password_env"] == ""
    assert saved == {
        "reference": "smtp:user@example.com",
        "secret": "fictional-credential",
    }
    assert form.credential_saved is False
    assert load_settings(settings_path).email.enabled is True


def test_email_setup_page_saves_through_service(tmp_path: Path, monkeypatch) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    _write_settings(settings_path)
    monkeypatch.setattr(
        "job_radar.email_settings_service.get_credential",
        lambda reference: None,
    )
    monkeypatch.setattr(
        "job_radar.email_settings_service.store_credential",
        lambda reference, secret: None,
    )
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    client = app.test_client()

    page = client.get("/settings?section=email")
    saved = client.post(
        "/settings/email",
        data={
            "enabled": "yes",
            "provider": "gmail",
            "sender": "user@example.com",
            "sender_name": "Junior User",
            "recipients": "user@example.com",
            "smtp_host": "smtp.example.com",
            "smtp_port": "587",
            "smtp_username": "user@example.com",
            "smtp_tls_mode": "starttls",
            "credential": "fictional-credential",
        },
        follow_redirects=True,
    )

    assert page.status_code == 200
    assert "Email" in page.get_data(as_text=True)
    normalized_page = " ".join(page.get_data(as_text=True).split())
    assert 'id="email-settings"' in normalized_page
    assert 'id="email-settings" open' in normalized_page
    assert normalized_page.count("data-preserve-settings-scroll") >= 3
    assert (
        "sessionStorage.setItem(settingsScrollKey, String(window.scrollY))"
        in page.get_data(as_text=True)
    )
    assert "Gmail" in page.get_data(as_text=True)
    assert "Outlook" in page.get_data(as_text=True)
    assert "Custom SMTP" in page.get_data(as_text=True)
    assert "Test connection" in page.get_data(as_text=True)
    assert "Send test email" in page.get_data(as_text=True)
    assert "View email activity" in page.get_data(as_text=True)
    assert "Email settings saved." in saved.get_data(as_text=True)
    assert "fictional-credential" not in settings_path.read_text(encoding="utf-8")


class _SuccessfulSMTP:
    def __init__(self, host, port, timeout):
        self.started_tls = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        return None


class _AuthenticationFailureSMTP(_SuccessfulSMTP):
    def login(self, username, password):
        raise smtplib.SMTPAuthenticationError(535, b"private response")


class _TlsFailureSMTP(_SuccessfulSMTP):
    def starttls(self):
        raise ssl.SSLError("private TLS response")


class _UnreachableSMTP:
    def __init__(self, host, port, timeout):
        raise OSError("private network response")


def test_connection_reports_simple_success_and_authentication_results(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    _write_settings(settings_path)
    monkeypatch.setattr("smtplib.SMTP", _SuccessfulSMTP)

    success = check_email_connection(
        settings_path,
        provider="gmail",
        smtp_host="",
        smtp_port_text="",
        smtp_username="user@example.com",
        smtp_tls_mode="",
        credential="fictional-credential",
    )
    monkeypatch.setattr("smtplib.SMTP", _AuthenticationFailureSMTP)
    failure = check_email_connection(
        settings_path,
        provider="outlook",
        smtp_host="",
        smtp_port_text="",
        smtp_username="user@example.com",
        smtp_tls_mode="",
        credential="fictional-credential",
    )

    assert success == "Connection successful"
    assert failure == "Authentication failed"
    assert "private response" not in failure


def test_connection_sanitizes_tls_and_unreachable_results(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    _write_settings(settings_path)
    arguments = {
        "settings_path": settings_path,
        "provider": "gmail",
        "smtp_host": "",
        "smtp_port_text": "",
        "smtp_username": "user@example.com",
        "smtp_tls_mode": "",
        "credential": "fictional-credential",
    }
    monkeypatch.setattr("smtplib.SMTP", _TlsFailureSMTP)
    tls_result = check_email_connection(**arguments)
    monkeypatch.setattr("smtplib.SMTP", _UnreachableSMTP)
    unreachable_result = check_email_connection(**arguments)

    assert tls_result == "TLS negotiation failed"
    assert unreachable_result == "Server unreachable"
    assert "private" not in tls_result
    assert "private" not in unreachable_result


def test_connection_reports_missing_credential_as_not_configured(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    _write_settings(settings_path)

    result = check_email_connection(
        settings_path,
        provider="gmail",
        smtp_host="",
        smtp_port_text="",
        smtp_username="user@example.com",
        smtp_tls_mode="",
        credential="",
    )

    assert result == "Credential not configured"


def test_connection_route_shows_session_scoped_status_card(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    _write_settings(settings_path)
    monkeypatch.setattr(
        "job_radar.web_routes.settings.test_email_connection",
        lambda *args, **kwargs: "Authentication failed",
    )
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    client = app.test_client()

    response = client.post(
        "/settings/email/test",
        data={
            "provider": "gmail",
            "smtp_host": "",
            "smtp_port": "",
            "smtp_username": "user@example.com",
            "smtp_tls_mode": "",
            "credential": "",
        },
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Authentication failed" in html
    assert "The username or password was rejected." in html
    assert "Gmail" in html
    assert "Today at" in html


def test_email_setup_sends_latest_report_with_saved_settings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    _write_settings(settings_path)
    reports_path = tmp_path / "reports"
    reports_path.mkdir()
    (reports_path / "target-email-preview.txt").write_text(
        "Subject: Latest report\n\nSummary\n",
        encoding="utf-8",
    )
    (reports_path / "target-scan.html").write_text(
        "<html>Report</html>",
        encoding="utf-8",
    )
    captured = {}

    def fake_send(email_settings, *, preview_path, report_path):
        captured.update(
            email_settings=email_settings,
            preview_path=preview_path,
            report_path=report_path,
        )
        return type("Result", (), {"sent": True, "message": "Email sent"})()

    monkeypatch.setattr(
        "job_radar.web_routes.settings.send_generated_scan_report",
        fake_send,
    )
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    client = app.test_client()

    response = client.post(
        "/settings/email/send-latest",
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert captured["email_settings"].enabled is False
    assert captured["preview_path"] == (
        reports_path / "target-email-preview.txt"
    )
    assert captured["report_path"] == reports_path / "target-scan.html"
    assert "Scan summary sent" in html
    assert "attached the full HTML report" in html


def test_email_setup_sends_safe_diagnostic_test_and_records_activity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    _write_settings(settings_path)
    captured = {}

    def fake_send(email_settings):
        captured["email_settings"] = email_settings
        return type("Result", (), {"sent": True, "message": "Email sent"})()

    monkeypatch.setattr(
        "job_radar.web_routes.settings.send_email_diagnostic_test",
        fake_send,
    )
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    client = app.test_client()

    response = client.post(
        "/settings/email/send-test",
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert captured["email_settings"].enabled is False
    assert "Diagnostic email sent" in html
    assert "Junior sent the diagnostic test email." in html
    email_log = tmp_path / "logs" / "junior-email.log"
    assert email_log.is_file()
    content = email_log.read_text(encoding="utf-8")
    assert "email_diagnostic_message" in content
    assert "successful" in content
    assert "@" not in content
