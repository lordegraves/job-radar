"""Check email readiness and send reports without storing SMTP credentials."""

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from job_radar.credential_store import CredentialStoreError, get_credential


@dataclass(frozen=True)
class EmailSendResult:
    sent: bool
    message: str


@dataclass(frozen=True)
class EmailReadiness:
    ready: bool
    message: str


def get_email_readiness(
    email_settings: Mapping[str, Any],
) -> EmailReadiness:
    """Report whether email can be sent without attempting an SMTP connection."""

    if not email_settings.get("enabled", False):
        return EmailReadiness(
            ready=False,
            message="Disabled",
        )

    credential_key = email_settings.get("smtp_credential_key", "")
    if credential_key:
        try:
            credential = get_credential(credential_key)
        except CredentialStoreError:
            return EmailReadiness(
                ready=False,
                message="Enabled, but secure credential storage is unavailable",
            )
        return EmailReadiness(
            ready=credential is not None,
            message=(
                "Ready to send"
                if credential is not None
                else "Enabled, but the saved credential is unavailable"
            ),
        )

    password_env = email_settings.get("smtp_password_env", "")
    if not password_env:
        return EmailReadiness(
            ready=False,
            message="Enabled, but no credential reference is configured",
        )

    if not os.environ.get(password_env):
        return EmailReadiness(
            ready=False,
            message=f"Enabled, but credential is unavailable: {password_env}",
        )

    return EmailReadiness(
        ready=True,
        message="Ready to send",
    )


def send_email_report(
    email_settings: Mapping[str, Any],
    subject: str,
    body: str,
    html_body: str | None = None,
    attachment_path: str | Path | None = None,
) -> EmailSendResult:
    if not email_settings.get("enabled", False):
        return EmailSendResult(
            sent=False,
            message="Email sending disabled by settings",
        )

    credential_key = email_settings.get("smtp_credential_key", "")
    password_env = email_settings.get("smtp_password_env", "")
    if credential_key:
        try:
            password = get_credential(credential_key)
        except CredentialStoreError:
            return EmailSendResult(
                sent=False,
                message="Secure credential storage is unavailable",
            )
    else:
        password = os.environ.get(password_env)

    if not password:
        return EmailSendResult(
            sent=False,
            message=(
                "Saved email credential is unavailable"
                if credential_key
                else "Email password environment variable is not set: "
                f"{password_env}"
            ),
        )

    try:
        message = _build_email_message(
            sender=email_settings["sender"],
            sender_name=email_settings.get("sender_name", ""),
            recipients=email_settings["recipients"],
            subject=subject,
            body=body,
            html_body=html_body,
            attachment_path=attachment_path,
        )

        _send_smtp_message(
            email_settings=email_settings,
            message=message,
            password=password,
        )
    except (OSError, smtplib.SMTPException):
        return EmailSendResult(
            sent=False,
            message=(
                "Email could not be sent. Review Email Settings or open "
                "System Health for safe troubleshooting details."
            ),
        )

    return EmailSendResult(
        sent=True,
        message="Email sent",
    )


def send_generated_scan_report(
    email_settings: Mapping[str, Any],
    *,
    preview_path: str | Path,
    report_path: str | Path,
) -> EmailSendResult:
    """Send the latest durable scan outputs without starting another scan."""

    preview = Path(preview_path)
    report = Path(report_path)
    if not preview.is_file() or not report.is_file():
        return EmailSendResult(
            sent=False,
            message=(
                "No complete scan report is available. Run a scan before "
                "sending its summary."
            ),
        )

    try:
        preview_text = preview.read_text(encoding="utf-8")
        report_html = report.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return EmailSendResult(
            sent=False,
            message=(
                "The latest scan report could not be read. Run a new scan, "
                "then try again."
            ),
        )

    subject_line, separator, body = preview_text.partition("\n")
    if not separator or not subject_line.startswith("Subject: "):
        return EmailSendResult(
            sent=False,
            message=(
                "The latest scan summary is incomplete. Run a new scan, "
                "then try again."
            ),
        )

    return send_email_report(
        email_settings=email_settings,
        subject=subject_line.removeprefix("Subject: ").strip(),
        body=body.lstrip(),
        html_body=report_html,
        attachment_path=report,
    )


def _build_email_message(
    sender: str,
    sender_name: str,
    recipients: list[str],
    subject: str,
    body: str,
    html_body: str | None = None,
    attachment_path: str | Path | None = None,
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = _format_sender(sender=sender, sender_name=sender_name)
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(body)

    if html_body is not None:
        message.add_alternative(html_body, subtype="html")

    if attachment_path is not None:
        _attach_text_file(message=message, attachment_path=attachment_path)

    return message


def _format_sender(sender: str, sender_name: str) -> str:
    if not sender_name:
        return sender

    return formataddr((sender_name, sender))


def _attach_text_file(message: EmailMessage, attachment_path: str | Path) -> None:
    path = Path(attachment_path)
    content = path.read_text(encoding="utf-8")

    message.add_attachment(
        content,
        subtype=_get_text_attachment_subtype(path),
        filename=path.name,
    )


def _get_text_attachment_subtype(path: Path) -> str:
    if path.suffix.lower() in {".html", ".htm"}:
        return "html"

    if path.suffix.lower() == ".md":
        return "markdown"

    return "plain"


def _send_smtp_message(
    email_settings: Mapping[str, Any],
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
    email_settings: Mapping[str, Any],
    message: EmailMessage,
    password: str,
) -> None:
    smtp.login(email_settings["smtp_username"], password)
    smtp.send_message(message)
