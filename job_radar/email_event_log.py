"""Record bounded email test and delivery outcomes without private data."""

import json
from datetime import UTC, datetime
from pathlib import Path

from job_radar import __build__, __version__

EMAIL_LOG_NAME = "junior-email.log"
MAX_EMAIL_LOG_BYTES = 1_000_000
MAX_RETAINED_LOG_BYTES = 750_000
_SAFE_PROVIDERS = {"gmail", "outlook", "custom"}


def record_email_event(
    logs_path: str | Path,
    *,
    event: str,
    outcome: str,
    provider: str,
    reason_code: str,
) -> bool:
    """Append only safe operational fields and never block an email action."""

    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "schema_version": 1,
        "application_version": __version__,
        "application_build": __build__,
        "subsystem": "email",
        "severity": "info" if outcome == "successful" else "warning",
        "event": event,
        "outcome": outcome,
        "provider": (
            provider if provider in _SAFE_PROVIDERS else "not_configured"
        ),
        "reason_code": reason_code,
    }
    try:
        directory = Path(logs_path)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / EMAIL_LOG_NAME
        _bound_existing_log(path)
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(payload, sort_keys=True) + "\n")
    except OSError:
        # A troubleshooting log must never turn a test or send into an error.
        return False
    return True


def _bound_existing_log(path: Path) -> None:
    if not path.is_file() or path.stat().st_size < MAX_EMAIL_LOG_BYTES:
        return
    with path.open("rb") as stream:
        stream.seek(-MAX_RETAINED_LOG_BYTES, 2)
        retained = stream.read()
    first_newline = retained.find(b"\n")
    if first_newline >= 0:
        retained = retained[first_newline + 1 :]
    path.write_bytes(retained)
