"""Detect a genuinely new installation without misclassifying existing data."""

from pathlib import Path

from job_radar.database import connect_database
from job_radar.storage import initialize_database


def needs_first_run_setup(database_path: str | Path) -> bool:
    """Return true only when no user-created or imported records exist."""

    db_path = initialize_database(database_path)
    tables = (
        "profiles",
        "application_tracker",
        "job_history",
        "job_postings",
    )
    with connect_database(db_path) as connection:
        regular_tables_empty = all(
            connection.execute(
                f"SELECT 1 FROM {table_name} LIMIT 1"
            ).fetchone()
            is None
            for table_name in tables
        )
        user_employers_empty = connection.execute(
            "SELECT 1 FROM employer_sources "
            "WHERE catalog_origin <> 'starter' LIMIT 1"
        ).fetchone() is None
        return regular_tables_empty and user_employers_empty
