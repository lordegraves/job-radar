"""Write bounded structured diagnostics without copying user-owned content."""

from __future__ import annotations

import json
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from job_radar import __build__, __version__


APPLICATION_LOG_NAME = "junior-application.log"
APPLICATION_PREVIOUS_LOG_NAME = "junior-application.log.previous"
MAX_LOG_BYTES = 2_000_000
_WRITE_LOCK = Lock()
_SUPPORTED_KINDS = {"database", "errors", "user_actions", "application"}
_OPERATION_ID: ContextVar[str | None] = ContextVar(
    "junior_diagnostic_operation_id",
    default=None,
)


def set_diagnostic_operation_id(operation_id: str | None) -> None:
    """Correlate all safe events emitted while one task is running."""

    _OPERATION_ID.set(operation_id)


def operational_log_name(kind: str) -> str:
    """Return the timestamped filename owned by one application process."""

    if kind not in _SUPPORTED_KINDS:
        raise ValueError(f"unsupported operational log kind: {kind}")
    return APPLICATION_LOG_NAME


def record_operational_event(
    logs_path: str | Path,
    *,
    kind: str,
    subsystem: str,
    event: str,
    severity: str = "info",
    fields: dict[str, object] | None = None,
) -> bool:
    """Append an already-sanitized event and never interrupt product work."""

    if kind not in _SUPPORTED_KINDS:
        raise ValueError(f"unsupported operational log kind: {kind}")
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "schema_version": 1,
        "application_version": __version__,
        "application_build": __build__,
        "severity": severity,
        "subsystem": subsystem,
        "event": event,
        "category": kind,
    }
    operation_id = _OPERATION_ID.get()
    if operation_id:
        payload["operation_id"] = operation_id
    payload.update(_safe_values(fields or {}))
    try:
        directory = Path(logs_path)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / APPLICATION_LOG_NAME
        with _WRITE_LOCK:
            _bound_existing_log(path)
            with path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(payload, sort_keys=True) + "\n")
    except OSError:
        return False
    return True


def inferred_logs_path(database_path: str | Path) -> Path:
    """Locate the sibling logs directory used by normal Junior workspaces."""

    database = Path(database_path).resolve()
    if database.parent.name.casefold() == "data":
        return database.parent.parent / "logs"
    return database.parent / "logs"


def _safe_values(fields: dict[str, object]) -> dict[str, object]:
    safe: dict[str, object] = {}
    for key, value in fields.items():
        if value is None or isinstance(value, (bool, int, float, str)):
            safe[key] = value
        elif isinstance(value, (list, tuple)) and all(
            isinstance(item, (bool, int, float, str)) for item in value
        ):
            safe[key] = list(value)
    return safe


def _bound_existing_log(path: Path) -> None:
    if not path.is_file() or path.stat().st_size < MAX_LOG_BYTES:
        return
    previous = path.with_name(APPLICATION_PREVIOUS_LOG_NAME)
    path.replace(previous)
