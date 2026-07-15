import sqlite3
from pathlib import Path


def connect_database(database_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(Path(database_path))
    connection.execute("PRAGMA foreign_keys = ON")
    return connection