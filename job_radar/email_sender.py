import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any


@dataclass(frozen=True)
class EmailSendResult:
    sent: bool
    message: str


def send_email_report(
    email_settings: dict[str, Any],
    subject: str,
    body: str,
) -> EmailSendResult:
    if not email_settings.get("enabled", False):
        return EmailSendResult(
            sent=False,
            message="Email sending disabled by settings",
        )

    password_env = email_settings["smtp_password_env"]
    password = os.environ.get(password_env)

    if not password:
        return EmailSendResult(
            sent=False,
            message=f"Email password environment variable is not set: {password_env}",
        )

    message = _build_email_message(
        sender=email_settings["sender"],
        recipients=email_settings["recipients"],
        subject=subject,
        body=body,
    )

    try:
        _send_smtp_message(
            email_settings=email_settings,
            message=message,
            password=password,
        )
    except (OSError, smtplib.SMTPException) as error:
        return EmailSendResult(
            sent=False,
            message=f"Email send failed: {error}",
        )

    return EmailSendResult(
        sent=True,
        message="Email sent",
    )


def _build_email_message(
    sender: str,
    recipients: list[str],
    subject: str,
    body: str,
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(body)

    return message


def _send_smtp_message(
    email_settings: dict[str, Any],
    message: EmailMessage,
    password: str,
) -> None:
    tls_mode = email_settings["smtp_tls_mode"]

    if tls_mode == "ssl":
        with smtplib.SMTP_SSL(
            email_settings["smtp_host"],
            email_settings["smtp_port"],
        ) as smtp:
            _login_and_send(smtp, email_settings, message, password)
        return

    with smtplib.SMTP(
        email_settings["smtp_host"],
        email_settings["smtp_port"],
    ) as smtp:
        if tls_mode == "starttls":
            smtp.starttls()

        _login_and_send(smtp, email_settings, message, password)


def _login_and_send(
    smtp,
    email_settings: dict[str, Any],
    message: EmailMessage,
    password: str,
) -> None:
    smtp.login(email_settings["smtp_username"], password)
    smtp.send_message(message)