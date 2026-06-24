from job_radar.email_sender import send_email_report


def test_send_email_report_refuses_when_disabled() -> None:
    result = send_email_report(
        email_settings={
            "enabled": False,
            "sender": "",
            "recipients": [],
            "smtp_host": "",
            "smtp_port": 587,
        },
        subject="Job Radar Report",
        body="Report body",
    )

    assert result.sent is False
    assert result.message == "Email sending disabled by settings"


def test_send_email_report_does_not_send_when_enabled_but_not_implemented() -> None:
    result = send_email_report(
        email_settings={
            "enabled": True,
            "sender": "clayton@example.com",
            "recipients": ["clayton@example.com"],
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
        },
        subject="Job Radar Report",
        body="Report body",
    )

    assert result.sent is False
    assert (
        result.message
        == "Email sending is enabled, but SMTP delivery is not implemented yet"
    )