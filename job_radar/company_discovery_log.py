"""Write bounded, privacy-safe diagnostics for interactive company discovery."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from job_radar.operational_event_log import record_operational_event

_SAFE_FIELDS = {
    "attempt_id",
    "candidate_host",
    "candidate_number",
    "job_count",
    "page_number",
    "queue_depth",
    "document_bytes",
    "outcome",
    "source_type",
    "stage",
    "submission_type",
    "submitted_host",
    "final_status",
    "company_created",
    "company_assigned",
    "elapsed_seconds",
}


def record_company_discovery_event(
    logs_path: str | Path,
    stage: str,
    fields: Mapping[str, object],
) -> bool:
    """Append one allowlisted event without URLs, user data, or exceptions."""

    safe_fields = {
            key: value
            for key, value in fields.items()
            if key in _SAFE_FIELDS and isinstance(value, (bool, float, int, str))
        }
    safe_fields["stage"] = stage
    return record_operational_event(
        logs_path,
        kind="application",
        subsystem="company_discovery",
        event="company_discovery",
        severity=_event_severity(fields),
        fields=safe_fields,
    )


def _event_severity(fields: Mapping[str, object]) -> str:
    outcome = str(fields.get("outcome") or "").lower()
    if outcome in {"failed", "rejected", "unsupported"}:
        return "error"
    if outcome in {"not_found", "timeout", "inconclusive"}:
        return "warning"
    return "info"
