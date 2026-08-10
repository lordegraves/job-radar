"""Record bounded, privacy-safe job-decision events for troubleshooting."""

from pathlib import Path

from job_radar.operational_event_log import record_operational_event


def record_decision_event(
    logs_path: str | Path,
    *,
    event: str,
    status: str,
    job_radar_id: str | None,
    source_view: str,
    prior_state: str | None = None,
    target_state: str | None = None,
    reason_code: str | None = None,
    item_count: int = 1,
) -> bool:
    """Append safe fields without ever blocking the user's requested action."""
    return record_operational_event(
        logs_path,
        kind="application",
        subsystem="job_decision",
        event=event,
        severity="error" if status == "failed" else "info",
        fields={
            "status": status,
            "job_id": job_radar_id,
            "source_view": source_view,
            "prior_state": prior_state,
            "target_state": target_state,
            "reason_code": reason_code,
            "item_count": item_count,
        },
    )
