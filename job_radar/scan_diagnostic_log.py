"""Record bounded, privacy-safe scan events without storing job or profile data."""

from datetime import UTC, datetime
import json
from pathlib import Path
from time import monotonic


DIAGNOSTIC_LOG_NAME = "junior-diagnostics.log"
LAST_SCAN_LOG_NAME = "junior-last-scan.log"
MAX_DIAGNOSTIC_LOG_BYTES = 1_000_000
MAX_RETAINED_LOG_BYTES = 750_000
_SAFE_FIELDS = {
    "scan_run_id",
    "trigger",
    "stage",
    "company_number",
    "companies_requested",
    "companies_scanned",
    "source_type",
    "jobs_found",
    "jobs_stored",
    "jobs_omitted",
    "jobs_new",
    "jobs_seen",
    "jobs_changed",
    "collector_errors",
    "top_matches",
    "potential_top_matches",
    "review_needed",
    "location_outliers",
    "report_status",
    "email_status",
    "failure_category",
    "elapsed_seconds",
}


def start_scan_diagnostics(
    logs_path: str | Path,
    *,
    scan_run_id: int,
    trigger: str,
    companies_requested: int,
) -> float:
    """Start a fresh last-scan log and return its monotonic start time."""

    started = monotonic()
    _write_event(
        logs_path,
        event="scan_started",
        replace_last_scan=True,
        scan_run_id=scan_run_id,
        trigger=trigger,
        stage="configuration",
        companies_requested=companies_requested,
    )
    return started


def record_scan_diagnostic(
    logs_path: str | Path,
    *,
    event: str,
    **fields: object,
) -> bool:
    """Append only explicitly approved operational fields."""

    return _write_event(logs_path, event=event, **fields)


def elapsed_seconds(started: float) -> float:
    """Return a stable, human-readable elapsed duration."""

    return round(max(0.0, monotonic() - started), 3)


def _write_event(
    logs_path: str | Path,
    *,
    event: str,
    replace_last_scan: bool = False,
    **fields: object,
) -> bool:
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": event,
        **{key: value for key, value in fields.items() if key in _SAFE_FIELDS},
    }
    line = json.dumps(payload, sort_keys=True) + "\n"
    try:
        directory = Path(logs_path)
        directory.mkdir(parents=True, exist_ok=True)
        general_path = directory / DIAGNOSTIC_LOG_NAME
        _bound_existing_log(general_path)
        with general_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line)

        last_scan_path = directory / LAST_SCAN_LOG_NAME
        mode = "w" if replace_last_scan else "a"
        with last_scan_path.open(mode, encoding="utf-8", newline="\n") as stream:
            stream.write(line)
    except OSError:
        # Diagnostics must never make a scan fail.
        return False
    return True


def _bound_existing_log(path: Path) -> None:
    if not path.is_file() or path.stat().st_size < MAX_DIAGNOSTIC_LOG_BYTES:
        return
    with path.open("rb") as stream:
        stream.seek(-MAX_RETAINED_LOG_BYTES, 2)
        retained = stream.read()
    first_newline = retained.find(b"\n")
    if first_newline >= 0:
        retained = retained[first_newline + 1 :]
    path.write_bytes(retained)
