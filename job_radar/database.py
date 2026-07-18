"""Open SQLite connections with Job Radar's required safety settings.

All database services use this helper so SQLite foreign-key rules are enforced
consistently instead of depending on each caller to remember the setting.
"""

import sqlite3
from pathlib import Path


def connect_database(database_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(Path(database_path))
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
