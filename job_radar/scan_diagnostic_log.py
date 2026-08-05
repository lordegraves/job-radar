"""Record bounded, privacy-safe scan events without storing job or profile data."""

import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from time import monotonic

from job_radar import __build__, __version__

DIAGNOSTIC_LOG_NAME = "junior-diagnostics.log"
LAST_SCAN_LOG_NAME = "junior-last-scan.log"
MAX_DIAGNOSTIC_LOG_BYTES = 1_000_000
MAX_RETAINED_LOG_BYTES = 750_000
_SAFE_FIELDS = {
    "scan_run_id",
    "trigger",
    "stage",
    "company_number",
    "company_id",
    "companies_requested",
    "companies_scanned",
    "source_type",
    "jobs_found",
    "jobs_stored",
    "jobs_omitted",
    "jobs_new",
    "jobs_seen",
    "jobs_changed",
    "jobs_reused",
    "jobs_decided",
    "jobs_actionable",
    "jobs_not_actionable",
    "omitted_critical_gap",
    "omitted_practical_mismatch",
    "omitted_profile_exclusion",
    "omitted_other_fit",
    "collector_errors",
    "top_matches",
    "potential_top_matches",
    "review_needed",
    "location_outliers",
    "report_status",
    "email_status",
    "failure_category",
    "failure_reason",
    "elapsed_seconds",
    "company_elapsed_seconds",
    "company_queue_seconds",
    "phase_elapsed_seconds",
    "jobs_llm_reviewed",
    "jobs_llm_reused",
    "llm_failures",
}
_RUN_LOGS: dict[int, str] = {}
_RUN_LOG_LOCK = Lock()


def start_scan_diagnostics(
    logs_path: str | Path,
    *,
    scan_run_id: int,
    trigger: str,
    companies_requested: int,
) -> float:
    """Start a fresh last-scan log and return its monotonic start time."""

    started = monotonic()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    with _RUN_LOG_LOCK:
        _RUN_LOGS[scan_run_id] = (
            f"junior-scan-run-{scan_run_id}-{stamp}.log"
        )
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
        "schema_version": 1,
        "application_version": __version__,
        "application_build": __build__,
        "subsystem": "scan",
        "severity": _event_severity(event, fields),
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
        scan_run_id = fields.get("scan_run_id")
        if isinstance(scan_run_id, int):
            with _RUN_LOG_LOCK:
                run_name = _RUN_LOGS.get(scan_run_id)
            if run_name:
                with (directory / run_name).open(
                    "a", encoding="utf-8", newline="\n"
                ) as stream:
                    stream.write(line)
    except OSError:
        # Diagnostics must never make a scan fail.
        return False
    return True


def _event_severity(event: str, fields: dict[str, object]) -> str:
    if event.endswith("_failed") or fields.get("failure_category"):
        return "error"
    if fields.get("collector_errors"):
        return "warning"
    return "info"


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
