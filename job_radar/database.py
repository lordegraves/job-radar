"""Open SQLite connections with Junior's required safety settings.

All database services use this helper so SQLite foreign-key rules are enforced
consistently instead of depending on each caller to remember the setting.
"""

import sqlite3
import sys
from pathlib import Path
from time import monotonic

from job_radar.operational_event_log import (
    inferred_logs_path,
    record_operational_event,
)


class JuniorConnection(sqlite3.Connection):
    """Commit or roll back a context-managed transaction, then close its file."""

    diagnostic_database_path: Path | None = None
    diagnostic_operation: str = "unknown"
    diagnostic_started: float = 0.0
    diagnostic_recorded: bool = False

    def __exit__(self, *exc_info: object) -> bool:
        try:
            result = bool(super().__exit__(*exc_info))
            self._record_database_event(
                "transaction_rolled_back" if exc_info[0] else "transaction_completed",
                error_type=(
                    getattr(exc_info[0], "__name__", None) if exc_info[0] else None
                ),
            )
            return result
        finally:
            # sqlite3.Connection's normal context manager ends the transaction
            # but leaves the database handle open. Junior services consistently
            # use ``with connect_database(...)`` and expect that boundary to
            # release Windows file locks and long-running process resources.
            self.close()

    def close(self) -> None:
        if not self.diagnostic_recorded:
            self._record_database_event("connection_closed")
        super().close()

    def _record_database_event(
        self,
        event: str,
        *,
        error_type: str | None = None,
    ) -> None:
        database_path = self.diagnostic_database_path
        if database_path is None:
            return
        elapsed_seconds = max(0.0, monotonic() - self.diagnostic_started)
        rows_changed = self.total_changes
        # Fast read-only connections are routine during a scan. Recording every
        # one would hide useful database activity and add avoidable disk writes.
        if error_type is None and rows_changed == 0 and elapsed_seconds < 0.05:
            self.diagnostic_recorded = True
            return
        self.diagnostic_recorded = True
        record_operational_event(
            inferred_logs_path(database_path),
            kind="database",
            subsystem="database",
            event=event,
            severity="error" if error_type else "info",
            fields={
                "operation": self.diagnostic_operation,
                "elapsed_seconds": round(elapsed_seconds, 4),
                "rows_changed": rows_changed,
                "error_type": error_type,
            },
        )


def connect_database(database_path: str | Path) -> sqlite3.Connection:
    caller = sys._getframe(1)
    operation = f"{caller.f_globals.get('__name__', 'unknown')}.{caller.f_code.co_name}"
    connection = sqlite3.connect(
        Path(database_path),
        factory=JuniorConnection,
    )
    connection.diagnostic_database_path = Path(database_path).resolve()
    connection.diagnostic_operation = operation
    connection.diagnostic_started = monotonic()
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
