"""Verify the starter catalog is useful without taking ownership from users."""

from pathlib import Path

from job_radar.database import connect_database
from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import upsert_employer_source
from job_radar.first_run_service import needs_first_run_setup
from job_radar.starter_catalog_service import (
    seed_starter_catalog,
    starter_catalog_entries,
)
from job_radar.storage import initialize_database


def test_catalog_contains_fifty_complete_supported_sources() -> None:
    entries = starter_catalog_entries()

    assert len(entries) == 50
    assert len({entry["employer_id"] for entry in entries}) == 50
    assert len({entry["source_identifier"] for entry in entries}) == 50
    assert all(entry["source_config"] for entry in entries)


def test_seed_is_idempotent_and_does_not_end_first_run(tmp_path: Path) -> None:
    database_path = initialize_database(tmp_path / "junior.sqlite3")

    assert seed_starter_catalog(database_path) == 50
    assert seed_starter_catalog(database_path) == 0
    assert needs_first_run_setup(database_path) is True
    with connect_database(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM employer_sources"
        ).fetchone()[0] == 50
        assert connection.execute(
            "SELECT COUNT(*) FROM profile_company_associations"
        ).fetchone()[0] == 0


def test_seed_preserves_user_source_and_does_not_restore_deleted_seed(
    tmp_path: Path,
) -> None:
    database_path = initialize_database(tmp_path / "junior.sqlite3")
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="starter_google",
            name="User-managed Google",
            source_type="greenhouse",
            source_config={"source_slug": "user-google"},
        ),
    )

    assert seed_starter_catalog(database_path) == 49
    with connect_database(database_path) as connection:
        row = connection.execute(
            "SELECT name, catalog_origin FROM employer_sources WHERE employer_id = ?",
            ("starter_google",),
        ).fetchone()
        assert row == ("User-managed Google", "user")
        connection.execute(
            "DELETE FROM employer_sources WHERE employer_id = ?",
            ("starter_affirm",),
        )

    assert seed_starter_catalog(database_path) == 0
    with connect_database(database_path) as connection:
        assert connection.execute(
            "SELECT 1 FROM employer_sources WHERE employer_id = ?",
            ("starter_affirm",),
        ).fetchone() is None
    assert needs_first_run_setup(database_path) is False
