"""Open SQLite connections with Job Radar's required safety settings.

All database services use this helper so SQLite foreign-key rules are enforced
consistently instead of depending on each caller to remember the setting.
"""

import sqlite3
from pathlib import Path


class JuniorConnection(sqlite3.Connection):
    """Commit or roll back a context-managed transaction, then close its file."""

    def __exit__(self, *exc_info: object) -> bool:
        try:
            return bool(super().__exit__(*exc_info))
        finally:
            # sqlite3.Connection's normal context manager ends the transaction
            # but leaves the database handle open. Junior services consistently
            # use ``with connect_database(...)`` and expect that boundary to
            # release Windows file locks and long-running process resources.
            self.close()


def connect_database(database_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        Path(database_path),
        factory=JuniorConnection,
    )
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
