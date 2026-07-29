"""Tests guarded email delivery using fake SMTP connections and credentials."""

from pathlib import Path

from job_radar.email_sender import (
    get_email_readiness,
    send_email_report,
    send_generated_scan_report,
)


class FakeSMTP:
    instances = []

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.started_tls = False
        self.login_username = None
        self.login_password = None
        self.sent_message = None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.login_username = username
        self.login_password = password

    def send_message(self, message):
        self.sent_message = message


def test_get_email_readiness_reports_disabled() -> None:
    readiness = get_email_readiness(
        {
            "enabled": False,
            "smtp_password_env": "",
        }
    )

    assert readiness.ready is False
    assert readiness.message == "Disabled"


def test_get_email_readiness_reports_missing_credential(monkeypatch) -> None:
    monkeypatch.delenv("JOB_RADAR_SMTP_PASSWORD", raising=False)

    readiness = get_email_readiness(
        {
            "enabled": True,
            "smtp_password_env": "JOB_RADAR_SMTP_PASSWORD",
        }
    )

    assert readiness.ready is False
    assert (
        readiness.message
        == "Enabled, but credential is unavailable: JOB_RADAR_SMTP_PASSWORD"
    )


def test_get_email_readiness_reports_ready(monkeypatch) -> None:
    monkeypatch.setenv("JOB_RADAR_SMTP_PASSWORD", "not-a-real-password")

    readiness = get_email_readiness(
        {
            "enabled": True,
            "smtp_password_env": "JOB_RADAR_SMTP_PASSWORD",
        }
    )

    assert readiness.ready is True
    assert readiness.message == "Ready to send"


def test_send_email_report_refuses_when_disabled() -> None:
    result = send_email_report(
        email_settings={
            "enabled": False,
            "sender": "",
            "sender_name": "",
            "recipients": [],
            "smtp_host": "",
            "smtp_port": 587,
            "smtp_username": "",
            "smtp_password_env": "",
            "smtp_tls_mode": "starttls",
        },
        subject="Job Radar Report",
        body="Report body",
    )

    assert result.sent is False
    assert result.message == "Email sending disabled by settings"


def test_send_generated_scan_report_requires_complete_outputs(
    tmp_path: Path,
) -> None:
    result = send_generated_scan_report(
        {"enabled": False},
        preview_path=tmp_path / "missing-preview.txt",
        report_path=tmp_path / "missing-report.html",
    )

    assert result.sent is False
    assert result.message == (
        "No complete scan report is available. Run a scan before sending "
        "its summary."
    )


def test_send_generated_scan_report_uses_preview_and_html_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    preview_path = tmp_path / "target-email-preview.txt"
    report_path = tmp_path / "target-scan.html"
    preview_path.write_text(
        "Subject: Latest Junior report\n\nPlain-language summary\n",
        encoding="utf-8",
    )
    report_path.write_text("<html>Full report</html>", encoding="utf-8")
    captured = {}

    def fake_send_email_report(**kwargs):
        captured.update(kwargs)
        return type("Result", (), {"sent": True, "message": "Email sent"})()

    monkeypatch.setattr(
        "job_radar.email_sender.send_email_report",
        fake_send_email_report,
    )

    result = send_generated_scan_report(
        {"enabled": True},
        preview_path=preview_path,
        report_path=report_path,
    )

    assert result.sent is True
    assert captured["subject"] == "Latest Junior report"
    assert captured["body"] == "Plain-language summary\n"
    assert captured["html_body"] == "<html>Full report</html>"
    assert captured["attachment_path"] == report_path


def test_send_email_report_refuses_when_password_env_missing(monkeypatch) -> None:
    monkeypatch.delenv("JOB_RADAR_SMTP_PASSWORD", raising=False)

    result = send_email_report(
        email_settings={
            "enabled": True,
            "sender": "user@example.com",
            "sender_name": "",
            "recipients": ["user@example.com"],
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_username": "user@example.com",
            "smtp_password_env": "JOB_RADAR_SMTP_PASSWORD",
            "smtp_tls_mode": "starttls",
        },
        subject="Job Radar Report",
        body="Report body",
    )

    assert result.sent is False
    assert (
        result.message
        == "Email password environment variable is not set: JOB_RADAR_SMTP_PASSWORD"
    )


def test_send_email_report_sends_with_starttls(monkeypatch) -> None:
    FakeSMTP.instances = []
    monkeypatch.setenv("JOB_RADAR_SMTP_PASSWORD", "not-a-real-password")
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    result = send_email_report(
        email_settings={
            "enabled": True,
            "sender": "user@example.com",
            "sender_name": "",
            "recipients": ["user@example.com"],
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_username": "user@example.com",
            "smtp_password_env": "JOB_RADAR_SMTP_PASSWORD",
            "smtp_tls_mode": "starttls",
        },
        subject="Job Radar Report",
        body="Report body",
    )

    smtp = FakeSMTP.instances[0]

    assert result.sent is True
    assert result.message == "Email sent"
    assert smtp.host == "smtp.example.com"
    assert smtp.port == 587
    assert smtp.started_tls is True
    assert smtp.login_username == "user@example.com"
    assert smtp.login_password == "not-a-real-password"
    assert smtp.sent_message["Subject"] == "Job Radar Report"
    assert smtp.sent_message["From"] == "user@example.com"
    assert smtp.sent_message["To"] == "user@example.com"
    assert "Report body" in smtp.sent_message.get_content()


def test_send_email_report_sends_with_ssl(monkeypatch) -> None:
    FakeSMTP.instances = []
    monkeypatch.setenv("JOB_RADAR_SMTP_PASSWORD", "not-a-real-password")
    monkeypatch.setattr("smtplib.SMTP_SSL", FakeSMTP)

    result = send_email_report(
        email_settings={
            "enabled": True,
            "sender": "user@example.com",
            "sender_name": "",
            "recipients": ["user@example.com"],
            "smtp_host": "smtp.example.com",
            "smtp_port": 465,
            "smtp_username": "user@example.com",
            "smtp_password_env": "JOB_RADAR_SMTP_PASSWORD",
            "smtp_tls_mode": "ssl",
        },
        subject="Job Radar Report",
        body="Report body",
    )

    smtp = FakeSMTP.instances[0]

    assert result.sent is True
    assert result.message == "Email sent"
    assert smtp.host == "smtp.example.com"
    assert smtp.port == 465
    assert smtp.started_tls is False
    assert smtp.login_username == "user@example.com"
    assert smtp.login_password == "not-a-real-password"
    assert smtp.sent_message["Subject"] == "Job Radar Report"


def test_send_email_report_sends_without_tls_for_local_relay(monkeypatch) -> None:
    FakeSMTP.instances = []
    monkeypatch.setenv("JOB_RADAR_SMTP_PASSWORD", "not-a-real-password")
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    result = send_email_report(
        email_settings={
            "enabled": True,
            "sender": "user@example.com",
            "sender_name": "",
            "recipients": ["user@example.com"],
            "smtp_host": "localhost",
            "smtp_port": 1025,
            "smtp_username": "user@example.com",
            "smtp_password_env": "JOB_RADAR_SMTP_PASSWORD",
            "smtp_tls_mode": "none",
        },
        subject="Job Radar Report",
        body="Report body",
    )

    smtp = FakeSMTP.instances[0]

    assert result.sent is True
    assert result.message == "Email sent"
    assert smtp.host == "localhost"
    assert smtp.port == 1025
    assert smtp.started_tls is False

def test_send_email_report_uses_sender_display_name(monkeypatch) -> None:
    FakeSMTP.instances = []
    monkeypatch.setenv("JOB_RADAR_SMTP_PASSWORD", "not-a-real-password")
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    result = send_email_report(
        email_settings={
            "enabled": True,
            "sender": "user@example.com",
            "sender_name": "Job Radar",
            "recipients": ["user@example.com"],
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_username": "user@example.com",
            "smtp_password_env": "JOB_RADAR_SMTP_PASSWORD",
            "smtp_tls_mode": "starttls",
        },
        subject="Job Radar Report",
        body="Report body",
    )

    smtp = FakeSMTP.instances[0]

    assert result.sent is True
    assert result.message == "Email sent"
    assert smtp.sent_message["From"] == "Job Radar <user@example.com>"


def test_send_email_report_attaches_markdown_report(monkeypatch, tmp_path) -> None:
    FakeSMTP.instances = []
    monkeypatch.setenv("JOB_RADAR_SMTP_PASSWORD", "not-a-real-password")
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    report_path = tmp_path / "live-test.md"
    report_path.write_text("# Job Radar Report\n\nReport details.\n", encoding="utf-8")

    result = send_email_report(
        email_settings={
            "enabled": True,
            "sender": "user@example.com",
            "sender_name": "Job Radar",
            "recipients": ["user@example.com"],
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_username": "user@example.com",
            "smtp_password_env": "JOB_RADAR_SMTP_PASSWORD",
            "smtp_tls_mode": "starttls",
        },
        subject="Job Radar Report",
        body="Report body",
        attachment_path=report_path,
    )

    smtp = FakeSMTP.instances[0]
    attachments = list(smtp.sent_message.iter_attachments())

    assert result.sent is True
    assert result.message == "Email sent"
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "live-test.md"
    assert attachments[0].get_content_type() == "text/markdown"
    assert "# Job Radar Report" in attachments[0].get_content()


def test_send_email_report_sends_html_alternative(monkeypatch) -> None:
    FakeSMTP.instances = []
    monkeypatch.setenv("JOB_RADAR_SMTP_PASSWORD", "not-a-real-password")
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    result = send_email_report(
        email_settings={
            "enabled": True,
            "sender": "user@example.com",
            "sender_name": "Job Radar",
            "recipients": ["user@example.com"],
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_username": "user@example.com",
            "smtp_password_env": "JOB_RADAR_SMTP_PASSWORD",
            "smtp_tls_mode": "starttls",
        },
        subject="Job Radar Report",
        body="Plain text body",
        html_body="<html><body><p>HTML body</p></body></html>",
    )

    smtp = FakeSMTP.instances[0]
    html_part = smtp.sent_message.get_body(preferencelist=("html",))

    assert result.sent is True
    assert result.message == "Email sent"
    assert html_part is not None
    assert "HTML body" in html_part.get_content()


def test_send_email_report_attaches_html_report(monkeypatch, tmp_path) -> None:
    FakeSMTP.instances = []
    monkeypatch.setenv("JOB_RADAR_SMTP_PASSWORD", "not-a-real-password")
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    report_path = tmp_path / "live-test.html"
    report_path.write_text(
        "<!doctype html><html><body>Report details.</body></html>",
        encoding="utf-8",
    )

    result = send_email_report(
        email_settings={
            "enabled": True,
            "sender": "user@example.com",
            "sender_name": "Job Radar",
            "recipients": ["user@example.com"],
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_username": "user@example.com",
            "smtp_password_env": "JOB_RADAR_SMTP_PASSWORD",
            "smtp_tls_mode": "starttls",
        },
        subject="Job Radar Report",
        body="Report body",
        attachment_path=report_path,
    )

    smtp = FakeSMTP.instances[0]
    attachments = list(smtp.sent_message.iter_attachments())

    assert result.sent is True
    assert result.message == "Email sent"
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "live-test.html"
    assert attachments[0].get_content_type() == "text/html"
    assert "Report details." in attachments[0].get_content()
