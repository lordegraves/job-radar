from job_radar.email_sender import send_email_report


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


def test_send_email_report_refuses_when_password_env_missing(monkeypatch) -> None:
    monkeypatch.delenv("JOB_RADAR_SMTP_PASSWORD", raising=False)

    result = send_email_report(
        email_settings={
            "enabled": True,
            "sender": "clayton@example.com",
            "sender_name": "",
            "recipients": ["clayton@example.com"],
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_username": "clayton@example.com",
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
            "sender": "clayton@example.com",
            "sender_name": "",
            "recipients": ["clayton@example.com"],
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_username": "clayton@example.com",
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
    assert smtp.login_username == "clayton@example.com"
    assert smtp.login_password == "not-a-real-password"
    assert smtp.sent_message["Subject"] == "Job Radar Report"
    assert smtp.sent_message["From"] == "clayton@example.com"
    assert smtp.sent_message["To"] == "clayton@example.com"
    assert "Report body" in smtp.sent_message.get_content()


def test_send_email_report_sends_with_ssl(monkeypatch) -> None:
    FakeSMTP.instances = []
    monkeypatch.setenv("JOB_RADAR_SMTP_PASSWORD", "not-a-real-password")
    monkeypatch.setattr("smtplib.SMTP_SSL", FakeSMTP)

    result = send_email_report(
        email_settings={
            "enabled": True,
            "sender": "clayton@example.com",
            "sender_name": "",
            "recipients": ["clayton@example.com"],
            "smtp_host": "smtp.example.com",
            "smtp_port": 465,
            "smtp_username": "clayton@example.com",
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
    assert smtp.login_username == "clayton@example.com"
    assert smtp.login_password == "not-a-real-password"
    assert smtp.sent_message["Subject"] == "Job Radar Report"


def test_send_email_report_sends_without_tls_for_local_relay(monkeypatch) -> None:
    FakeSMTP.instances = []
    monkeypatch.setenv("JOB_RADAR_SMTP_PASSWORD", "not-a-real-password")
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    result = send_email_report(
        email_settings={
            "enabled": True,
            "sender": "clayton@example.com",
            "sender_name": "",
            "recipients": ["clayton@example.com"],
            "smtp_host": "localhost",
            "smtp_port": 1025,
            "smtp_username": "clayton@example.com",
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
            "sender": "clayton@example.com",
            "sender_name": "Job Radar",
            "recipients": ["clayton@example.com"],
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_username": "clayton@example.com",
            "smtp_password_env": "JOB_RADAR_SMTP_PASSWORD",
            "smtp_tls_mode": "starttls",
        },
        subject="Job Radar Report",
        body="Report body",
    )

    smtp = FakeSMTP.instances[0]

    assert result.sent is True
    assert result.message == "Email sent"
    assert smtp.sent_message["From"] == "Job Radar <clayton@example.com>"


def test_send_email_report_attaches_markdown_report(monkeypatch, tmp_path) -> None:
    FakeSMTP.instances = []
    monkeypatch.setenv("JOB_RADAR_SMTP_PASSWORD", "not-a-real-password")
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    report_path = tmp_path / "live-test.md"
    report_path.write_text("# Job Radar Report\n\nReport details.\n", encoding="utf-8")

    result = send_email_report(
        email_settings={
            "enabled": True,
            "sender": "clayton@example.com",
            "sender_name": "Job Radar",
            "recipients": ["clayton@example.com"],
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_username": "clayton@example.com",
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
            "sender": "clayton@example.com",
            "sender_name": "Job Radar",
            "recipients": ["clayton@example.com"],
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_username": "clayton@example.com",
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
            "sender": "clayton@example.com",
            "sender_name": "Job Radar",
            "recipients": ["clayton@example.com"],
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_username": "clayton@example.com",
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