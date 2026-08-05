"""Write bounded structured diagnostics without copying user-owned content."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from job_radar import __build__, __version__


MAX_LOG_BYTES = 2_000_000
MAX_RETAINED_BYTES = 1_500_000
_PROCESS_STAMP = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
_WRITE_LOCK = Lock()
_LOG_NAMES = {
    "database": f"junior-database-{_PROCESS_STAMP}.log",
    "errors": f"junior-errors-{_PROCESS_STAMP}.log",
    "user_actions": f"junior-user-actions-{_PROCESS_STAMP}.log",
}


def operational_log_name(kind: str) -> str:
    """Return the timestamped filename owned by one application process."""

    return _LOG_NAMES[kind]


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

    if kind not in _LOG_NAMES:
        raise ValueError(f"unsupported operational log kind: {kind}")
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "schema_version": 1,
        "application_version": __version__,
        "application_build": __build__,
        "severity": severity,
        "subsystem": subsystem,
        "event": event,
    }
    payload.update(_safe_values(fields or {}))
    try:
        directory = Path(logs_path)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / _LOG_NAMES[kind]
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
    with path.open("rb") as stream:
        stream.seek(-MAX_RETAINED_BYTES, 2)
        retained = stream.read()
    first_newline = retained.find(b"\n")
    if first_newline >= 0:
        retained = retained[first_newline + 1 :]
    path.write_bytes(retained)
