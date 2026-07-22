"""Tests tracker database creation, migration, and record updates in temporary data."""

import sqlite3
from pathlib import Path

from job_radar.storage import initialize_database
from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import create_profile
from job_radar.tracker.tracker_models import ApplicationRecord
from job_radar.tracker.tracker_storage import (
    get_application,
    initialize_tracker_tables,
    list_applications,
    update_application_status,
    upsert_application,
)


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


def count_rows(database_path: Path, table_name: str) -> int:
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(f"SELECT COUNT(*) FROM {table_name}")
    return int(cursor.fetchone()[0])


def test_tracker_records_are_isolated_by_profile(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)
    first_profile = ManagedProfile(
        profile_id="profile_11111111",
        display_name="First synthetic profile",
    )
    second_profile = ManagedProfile(
        profile_id="profile_22222222",
        display_name="Second synthetic profile",
    )
    create_profile(database_path, first_profile)
    create_profile(database_path, second_profile)
    shared_job_id = "jr-shared-role-12345678"

    upsert_application(
        database_path,
        make_application_record(job_radar_id=shared_job_id, notes="First owner"),
        profile_id=first_profile.profile_id,
    )
    upsert_application(
        database_path,
        make_application_record(job_radar_id=shared_job_id, notes="Second owner"),
        profile_id=second_profile.profile_id,
    )

    first_records = list_applications(
        database_path,
        profile_id=first_profile.profile_id,
    )
    second_records = list_applications(
        database_path,
        profile_id=second_profile.profile_id,
    )

    assert [record.notes for record in first_records] == ["First owner"]
    assert [record.notes for record in second_records] == ["Second owner"]
    assert count_rows(database_path, "application_tracker") == 2


def make_application_record(
    job_radar_id: str = "jr-example-ai-12345678",
    status: str = "review_needed",
    notes: str | None = "Initial review needed.",
) -> ApplicationRecord:
    return ApplicationRecord(
        job_radar_id=job_radar_id,
        company_name="Example AI",
        role_title="Senior Site Reliability Engineer",
        source_url="https://example.com/jobs/senior-sre",
        status=status,
        follow_up_on=None,
        outcome=None,
        notes=notes,
    )


def test_initialize_tracker_tables_creates_application_tracker_table(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"

    result = initialize_tracker_tables(database_path)

    assert result == database_path
    assert database_path.exists()
    assert table_exists(database_path, "application_tracker")


def test_initialize_tracker_tables_can_run_after_main_database_init(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"

    initialize_database(database_path)
    initialize_tracker_tables(database_path)

    assert table_exists(database_path, "job_postings")
    assert table_exists(database_path, "application_tracker")


def test_initialize_tracker_tables_can_run_more_than_once(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"

    initialize_tracker_tables(database_path)
    initialize_tracker_tables(database_path)

    assert table_exists(database_path, "application_tracker")


def test_initialize_tracker_tables_adds_activity_date_columns_to_existing_table(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE application_tracker (
                job_radar_id TEXT PRIMARY KEY,
                company_name TEXT NOT NULL,
                role_title TEXT NOT NULL,
                source_url TEXT,
                status TEXT NOT NULL DEFAULT 'review_needed',
                follow_up_on TEXT,
                outcome TEXT,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    initialize_tracker_tables(database_path)

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(application_tracker)")
        }

    assert "applied_on" in columns
    assert "last_activity_on" in columns


def test_initialize_tracker_tables_repairs_posting_url_tracker_ids(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_tracker_tables(database_path)

    upsert_application(
        database_path,
        ApplicationRecord(
            job_radar_id="posting-url:https://example.com/manual-lead",
            company_name="ManualCo",
            role_title="Senior Infrastructure Engineer",
            source_url="https://example.com/manual-lead",
            status="Applied",
        ),
    )

    initialize_tracker_tables(database_path)

    applications = list_applications(database_path)

    assert len(applications) == 1
    assert applications[0].job_radar_id.startswith(
        "jr_manual_manualco_senior_infrastructure_engineer_"
    )
    assert not applications[0].job_radar_id.startswith("posting-url:")
    assert applications[0].source_url == "https://example.com/manual-lead"


def test_upsert_application_inserts_new_application(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_tracker_tables(database_path)

    result = upsert_application(database_path, make_application_record())
    application = get_application(database_path, "jr-example-ai-12345678")

    assert result == "new"
    assert count_rows(database_path, "application_tracker") == 1
    assert application is not None
    assert application.job_radar_id == "jr-example-ai-12345678"
    assert application.company_name == "Example AI"
    assert application.role_title == "Senior Site Reliability Engineer"
    assert application.status == "review_needed"
    assert application.notes == "Initial review needed."
    assert application.applied_on is None
    assert application.last_activity_on is None


def test_upsert_application_updates_existing_application(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_tracker_tables(database_path)

    first_result = upsert_application(database_path, make_application_record())
    second_result = upsert_application(
        database_path,
        make_application_record(
            status="applied",
            notes="Applied through company careers page.",
        ),
    )
    application = get_application(database_path, "jr-example-ai-12345678")

    assert first_result == "new"
    assert second_result == "updated"
    assert count_rows(database_path, "application_tracker") == 1
    assert application is not None
    assert application.status == "applied"
    assert application.notes == "Applied through company careers page."


def test_upsert_application_stores_activity_dates(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_tracker_tables(database_path)

    result = upsert_application(
        database_path,
        ApplicationRecord(
            job_radar_id="jr-example-ai-12345678",
            company_name="Example AI",
            role_title="Senior Site Reliability Engineer",
            source_url="https://example.com/jobs/senior-sre",
            status="applied",
            applied_on="2026-07-03",
            last_activity_on="2026-07-05",
        ),
    )
    application = get_application(database_path, "jr-example-ai-12345678")

    assert result == "new"
    assert application is not None
    assert application.applied_on == "2026-07-03"
    assert application.last_activity_on == "2026-07-05"


def test_update_application_status_updates_existing_record(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_tracker_tables(database_path)
    upsert_application(database_path, make_application_record())

    result = update_application_status(
        database_path,
        job_radar_id="jr-example-ai-12345678",
        status="follow_up_due",
        follow_up_on="2026-07-10",
        outcome=None,
        notes="Follow up with recruiter.",
        applied_on="2026-07-03",
        last_activity_on="2026-07-05",
    )
    application = get_application(database_path, "jr-example-ai-12345678")

    assert result is True
    assert application is not None
    assert application.status == "follow_up_due"
    assert application.follow_up_on == "2026-07-10"
    assert application.applied_on == "2026-07-03"
    assert application.last_activity_on == "2026-07-05"
    assert application.notes == "Follow up with recruiter."


def test_update_application_status_preserves_existing_activity_dates_when_omitted(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_tracker_tables(database_path)
    upsert_application(
        database_path,
        ApplicationRecord(
            job_radar_id="jr-example-ai-12345678",
            company_name="Example AI",
            role_title="Senior Site Reliability Engineer",
            source_url="https://example.com/jobs/senior-sre",
            status="applied",
            applied_on="2026-07-03",
            last_activity_on="2026-07-05",
        ),
    )

    result = update_application_status(
        database_path,
        job_radar_id="jr-example-ai-12345678",
        status="interviewing",
        notes="Recruiter replied.",
    )
    application = get_application(database_path, "jr-example-ai-12345678")

    assert result is True
    assert application is not None
    assert application.status == "interviewing"
    assert application.applied_on == "2026-07-03"
    assert application.last_activity_on == "2026-07-05"
    assert application.notes == "Recruiter replied."


def test_update_application_status_returns_false_for_missing_record(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_tracker_tables(database_path)

    result = update_application_status(
        database_path,
        job_radar_id="jr-missing-00000000",
        status="applied",
    )

    assert result is False


def test_list_applications_returns_application_records(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_tracker_tables(database_path)

    upsert_application(
        database_path,
        make_application_record(
            job_radar_id="jr-example-ai-11111111",
            status="applied",
        ),
    )
    upsert_application(
        database_path,
        ApplicationRecord(
            job_radar_id="jr-example-mobility-22222222",
            company_name="Example Mobility",
            role_title="Senior Site Reliability Engineer",
            source_url="https://example.com/jobs/example-mobility-sre",
            status="review_needed",
        ),
    )

    applications = list_applications(database_path)

    assert len(applications) == 2
    assert {application.job_radar_id for application in applications} == {
        "jr-example-ai-11111111",
        "jr-example-mobility-22222222",
    }
    assert all(
        isinstance(application, ApplicationRecord)
        for application in applications
    )

