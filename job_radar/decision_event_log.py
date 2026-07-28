"""Record bounded, privacy-safe job-decision events for troubleshooting."""

import json
from datetime import UTC, datetime
from pathlib import Path

from job_radar import __build__, __version__

DECISION_LOG_NAME = "junior-actions.log"
MAX_DECISION_LOG_BYTES = 1_000_000
MAX_RETAINED_LOG_BYTES = 750_000


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
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "schema_version": 1,
        "application_version": __version__,
        "application_build": __build__,
        "subsystem": "job_decision",
        "severity": "error" if status == "failed" else "info",
        "event": event,
        "status": status,
        "job_id": job_radar_id,
        "source_view": source_view,
        "prior_state": prior_state,
        "target_state": target_state,
        "reason_code": reason_code,
        "item_count": item_count,
    }
    try:
        directory = Path(logs_path)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / DECISION_LOG_NAME
        _bound_existing_log(path)
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(payload, sort_keys=True) + "\n")
    except OSError:
        # Troubleshooting output must never turn a saved decision into an error.
        return False
    return True


def _bound_existing_log(path: Path) -> None:
    if not path.is_file() or path.stat().st_size < MAX_DECISION_LOG_BYTES:
        return
    with path.open("rb") as stream:
        stream.seek(-MAX_RETAINED_LOG_BYTES, 2)
        retained = stream.read()
    first_newline = retained.find(b"\n")
    if first_newline >= 0:
        retained = retained[first_newline + 1 :]
    path.write_bytes(retained)
