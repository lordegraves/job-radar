import sqlite3
from pathlib import Path

from job_radar.storage import initialize_database


def table_exists(database_path: Path, table_name: str) -> bool:
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            AND name = ?
            """,
            (table_name,),
        )
        return cursor.fetchone() is not None


def test_initialize_database_creates_database_file(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"

    result = initialize_database(database_path)

    assert result == database_path
    assert database_path.exists()


def test_initialize_database_creates_expected_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"

    initialize_database(database_path)

    expected_tables = [
        "companies",
        "job_postings",
        "job_status",
        "scan_runs",
        "scan_errors",
        "job_seen_events",
    ]

    for table_name in expected_tables:
        assert table_exists(database_path, table_name)


def test_initialize_database_can_run_more_than_once(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"

    initialize_database(database_path)
    initialize_database(database_path)

    assert database_path.exists()
    assert table_exists(database_path, "companies")