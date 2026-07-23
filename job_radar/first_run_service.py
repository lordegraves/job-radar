"""Detect a genuinely new installation without misclassifying existing data."""

from pathlib import Path

from job_radar.database import connect_database
from job_radar.storage import initialize_database


def needs_first_run_setup(database_path: str | Path) -> bool:
    """Return true only when no user-created or imported records exist."""

    db_path = initialize_database(database_path)
    tables = (
        "profiles",
        "employer_sources",
        "application_tracker",
        "job_history",
        "job_postings",
    )
    with connect_database(db_path) as connection:
        return all(
            connection.execute(
                f"SELECT 1 FROM {table_name} LIMIT 1"
            ).fetchone()
            is None
            for table_name in tables
        )
