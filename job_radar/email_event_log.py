"""Record bounded email test and delivery outcomes without private data."""

from pathlib import Path

from job_radar.operational_event_log import record_operational_event
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

    return record_operational_event(
        logs_path,
        kind="application",
        subsystem="email",
        event=event,
        severity="info" if outcome == "successful" else "warning",
        fields={
            "outcome": outcome,
            "provider": (
                provider if provider in _SAFE_PROVIDERS else "not_configured"
            ),
            "reason_code": reason_code,
        },
    )
