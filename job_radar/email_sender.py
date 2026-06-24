from dataclasses import dataclass
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

    return EmailSendResult(
        sent=False,
        message="Email sending is enabled, but SMTP delivery is not implemented yet",
    )