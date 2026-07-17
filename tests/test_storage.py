import sqlite3
from pathlib import Path

from job_radar.database import connect_database
from job_radar.history_models import JobHistoryRecord
from job_radar.storage import (
    complete_scan_run,
    fail_scan_run,
    fetch_active_scan_run,
    fetch_latest_scan_run,
    initialize_database,
    record_scan_error,
    record_scan_run,
    start_scan_run,
    update_scan_run_progress,
    upsert_job_history_record,
    upsert_job_posting,
)
from job_radar.models import JobPosting


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


def test_initialize_database_backs_up_existing_database_before_migration(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE legacy_marker (
                value TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO legacy_marker (value)
            VALUES (?)
            """,
            ("before migration",),
        )

    initialize_database(database_path)

    backup_directory = tmp_path / "backups"
    backup_paths = list(
        backup_directory.glob(
            "job_radar.sqlite3.pre-migration-v1-v3-*.bak"
        )
    )

    assert len(backup_paths) == 1

    with sqlite3.connect(backup_paths[0]) as connection:
        marker_value = connection.execute(
            "SELECT value FROM legacy_marker"
        ).fetchone()[0]
        migration_table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            AND name = 'schema_migrations'
            """
        ).fetchone()

    assert marker_value == "before migration"
    assert migration_table is None

    initialize_database(database_path)

    backup_paths_after_second_initialization = list(
        backup_directory.glob(
            "job_radar.sqlite3.pre-migration-v1-v3-*.bak"
        )
    )

    assert len(backup_paths_after_second_initialization) == 1


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
        "job_history",
        "application_tracker",
        "schema_migrations",
    ]

    for table_name in expected_tables:
        assert table_exists(database_path, table_name)


def test_initialize_database_can_run_more_than_once(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"

    initialize_database(database_path)
    initialize_database(database_path)

    assert database_path.exists()
    assert table_exists(database_path, "companies")

    with sqlite3.connect(database_path) as connection:
        migration_rows = connection.execute(
            """
            SELECT version, name
            FROM schema_migrations
            ORDER BY version
            """
        ).fetchall()

    assert migration_rows == [
        (1, "baseline current schema"),
        (2, "backfill companies for stored jobs"),
        (3, "add durable scan lifecycle fields"),
    ]


def test_initialize_database_backfills_companies_for_existing_jobs(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)
    upsert_job_posting(database_path, make_posting())

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DELETE FROM companies")
        connection.execute(
            "DELETE FROM schema_migrations WHERE version = 2"
        )

    initialize_database(database_path)

    with connect_database(database_path) as connection:
        company_row = connection.execute(
            """
            SELECT company_key, name, source_type
            FROM companies
            WHERE company_key = ?
            """,
            ("example_ai",),
        ).fetchone()

        foreign_key_errors = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

    assert company_row == (
        "example_ai",
        "example_ai",
        "greenhouse",
    )
    assert foreign_key_errors == []


def test_scan_run_lifecycle_records_progress_completion_and_errors(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)

    scan_run_id = start_scan_run(
        database_path,
        requested_at="2026-07-15T14:00:00+00:00",
        companies_requested=3,
        companies_enabled=3,
    )

    assert update_scan_run_progress(
        database_path,
        scan_run_id=scan_run_id,
        current_stage="collection",
        companies_scanned=2,
        jobs_found=25,
        collector_errors=1,
    )

    error_id = record_scan_error(
        database_path,
        scan_run_id=scan_run_id,
        company_key="example_ai",
        source_type="greenhouse",
        error_type="collector_error",
        error_message="temporary API failure",
    )

    assert complete_scan_run(
        database_path,
        scan_run_id=scan_run_id,
        generated_at="2026-07-15T14:05:00+00:00",
        finished_at="2026-07-15T14:05:00+00:00",
        companies_scanned=3,
        jobs_collected=40,
        actionable_jobs_stored=4,
        jobs_not_actionable=36,
        jobs_new=2,
        jobs_seen=1,
        jobs_changed=1,
        collector_errors=1,
        top_matches_count=1,
        review_needed_count=3,
        report_status="completed",
        email_status="not_requested",
    )

    with connect_database(database_path) as connection:
        connection.row_factory = sqlite3.Row
        scan_row = connection.execute(
            "SELECT * FROM scan_runs WHERE id = ?",
            (scan_run_id,),
        ).fetchone()
        error_row = connection.execute(
            "SELECT * FROM scan_errors WHERE id = ?",
            (error_id,),
        ).fetchone()

    assert scan_row is not None
    assert scan_row["requested_at"] == "2026-07-15T14:00:00+00:00"
    assert scan_row["started_at"] == "2026-07-15T14:00:00+00:00"
    assert scan_row["finished_at"] == "2026-07-15T14:05:00+00:00"
    assert scan_row["status"] == "completed_with_warnings"
    assert scan_row["current_stage"] == "completed"
    assert scan_row["failure_summary"] is None
    assert scan_row["report_status"] == "completed"
    assert scan_row["email_status"] == "not_requested"
    assert scan_row["companies_requested"] == 3
    assert scan_row["companies_scanned"] == 3
    assert scan_row["jobs_found"] == 40
    assert scan_row["jobs_collected"] == 40
    assert scan_row["collector_errors"] == 1
    assert error_row is not None
    assert error_row["scan_run_id"] == scan_run_id
    assert error_row["company_key"] == "example_ai"
    assert error_row["error_type"] == "collector_error"
    assert error_row["error_message"] == "temporary API failure"


def test_scan_run_lifecycle_records_failure(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)

    scan_run_id = start_scan_run(
        database_path,
        requested_at="2026-07-15T15:00:00+00:00",
        companies_requested=4,
        companies_enabled=4,
        current_stage="configuration",
    )

    assert fail_scan_run(
        database_path,
        scan_run_id=scan_run_id,
        finished_at="2026-07-15T15:00:10+00:00",
        failed_stage="configuration",
        failure_summary="scoring configuration is invalid",
    )

    row = get_scan_run_row(database_path)

    assert row["status"] == "failed"
    assert row["current_stage"] == "configuration"
    assert row["failure_summary"] == "scoring configuration is invalid"
    assert row["finished_at"] == "2026-07-15T15:00:10+00:00"


def test_record_scan_run_inserts_scan_summary(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)

    scan_run_id = record_scan_run(
        database_path=database_path,
        generated_at="2026-07-02T14:00:00+00:00",
        companies_enabled=62,
        jobs_collected=9833,
        actionable_jobs_stored=10,
        jobs_not_actionable=9823,
        jobs_new=1,
        jobs_seen=8,
        jobs_changed=1,
        collector_errors=1,
        top_matches_count=3,
        review_needed_count=7,
    )

    row = get_scan_run_row(database_path)

    assert scan_run_id == 1
    assert count_rows(database_path, "scan_runs") == 1
    assert row["generated_at"] == "2026-07-02T14:00:00+00:00"
    assert row["finished_at"] == "2026-07-02T14:00:00+00:00"
    assert row["status"] == "completed"
    assert row["companies_requested"] == 62
    assert row["companies_scanned"] == 62
    assert row["companies_enabled"] == 62
    assert row["jobs_found"] == 9833
    assert row["jobs_collected"] == 9833
    assert row["actionable_jobs_stored"] == 10
    assert row["jobs_not_actionable"] == 9823
    assert row["jobs_new"] == 1
    assert row["jobs_seen"] == 8
    assert row["jobs_changed"] == 1
    assert row["collector_errors"] == 1
    assert row["errors_count"] == 1
    assert row["top_matches_count"] == 3
    assert row["review_needed_count"] == 7

def make_posting(description: str = "Build Linux infrastructure.") -> JobPosting:
    return JobPosting(
        company_key="example_ai",
        company_name="Example AI",
        source_type="greenhouse",
        source_job_id="123",
        source_url="https://boards.greenhouse.io/exampleai/jobs/123",
        title="Senior Infrastructure Engineer",
        location="Remote",
        description=description,
        canonical_key="example-ai:senior-infrastructure-engineer:remote",
        content_hash=f"hash-{description}",
    )


def count_rows(database_path: Path, table_name: str) -> int:
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(f"SELECT COUNT(*) FROM {table_name}")
        return int(cursor.fetchone()[0])


def get_scan_run_row(database_path: Path) -> sqlite3.Row:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT * FROM scan_runs").fetchone()

        assert row is not None
        return row


def get_job_row(database_path: Path) -> sqlite3.Row:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM job_postings WHERE canonical_key = ?",
            ("example-ai:senior-infrastructure-engineer:remote",),
        ).fetchone()

        assert row is not None
        return row


def test_upsert_job_posting_inserts_new_job_company_and_status(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)

    result = upsert_job_posting(database_path, make_posting())

    assert result == "new"
    assert count_rows(database_path, "companies") == 1
    assert count_rows(database_path, "job_postings") == 1
    assert count_rows(database_path, "job_status") == 1


def test_connect_database_enforces_foreign_keys(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)

    with connect_database(database_path) as connection:
        foreign_keys_enabled = connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0]

        assert foreign_keys_enabled == 1

        try:
            connection.execute(
                """
                INSERT INTO job_status (
                    job_posting_id,
                    status
                )
                VALUES (?, ?)
                """,
                (999999, "new"),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError(
                "Foreign-key enforcement allowed an orphaned job-status record."
            )


def test_upsert_job_posting_returns_seen_for_same_content(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)

    first = upsert_job_posting(database_path, make_posting())
    second = upsert_job_posting(database_path, make_posting())

    assert first == "new"
    assert second == "seen"
    assert count_rows(database_path, "job_postings") == 1
    assert count_rows(database_path, "job_status") == 1


def test_upsert_job_posting_returns_changed_for_different_content(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)

    first = upsert_job_posting(database_path, make_posting())
    second = upsert_job_posting(
        database_path,
        make_posting(description="Build Linux and Kubernetes infrastructure."),
    )

    row = get_job_row(database_path)

    assert first == "new"
    assert second == "changed"
    assert count_rows(database_path, "job_postings") == 1
    assert count_rows(database_path, "job_status") == 1
    assert row["description"] == "Build Linux and Kubernetes infrastructure."
    assert row["last_changed_at"] is not None

def test_upsert_job_posting_treats_same_title_location_with_different_source_ids_as_different_jobs(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)

    first_posting = JobPosting(
        company_key="anthropic",
        company_name="Anthropic",
        source_type="greenhouse",
        source_job_id="111",
        source_url="https://job-boards.greenhouse.io/anthropic/jobs/111",
        title="Account Executive",
        location="Remote",
        description="First posting.",
        canonical_key="anthropic:account-executive:remote",
        content_hash="hash-111",
    )

    second_posting = JobPosting(
        company_key="anthropic",
        company_name="Anthropic",
        source_type="greenhouse",
        source_job_id="222",
        source_url="https://job-boards.greenhouse.io/anthropic/jobs/222",
        title="Account Executive",
        location="Remote",
        description="Second posting.",
        canonical_key="anthropic:account-executive:remote",
        content_hash="hash-222",
    )

    first_result = upsert_job_posting(database_path, first_posting)
    second_result = upsert_job_posting(database_path, second_posting)

    assert first_result == "new"
    assert second_result == "new"
    assert count_rows(database_path, "job_postings") == 2
    assert count_rows(database_path, "job_status") == 2


def test_upsert_job_posting_tracks_new_seen_and_changed_counts_across_scan_passes(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)

    first_scan_postings = [
        make_posting(description="Build Linux infrastructure."),
        JobPosting(
            company_key="example_ai",
            company_name="Example AI",
            source_type="greenhouse",
            source_job_id="456",
            source_url="https://boards.greenhouse.io/exampleai/jobs/456",
            title="Senior Kubernetes Engineer",
            location="Remote",
            description="Build Kubernetes infrastructure.",
            canonical_key="example-ai:senior-kubernetes-engineer:remote",
            content_hash="hash-kubernetes",
        ),
    ]

    first_scan_results = [
        upsert_job_posting(database_path, posting)
        for posting in first_scan_postings
    ]

    second_scan_results = [
        upsert_job_posting(database_path, posting)
        for posting in first_scan_postings
    ]

    assert first_scan_results.count("new") == 2
    assert first_scan_results.count("seen") == 0
    assert first_scan_results.count("changed") == 0

    assert second_scan_results.count("new") == 0
    assert second_scan_results.count("seen") == 2
    assert second_scan_results.count("changed") == 0

    assert count_rows(database_path, "job_postings") == 2
    assert count_rows(database_path, "job_status") == 2


def test_upsert_job_posting_tracks_changed_count_when_content_changes(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)

    first_scan_postings = [
        make_posting(description="Build Linux infrastructure."),
        JobPosting(
            company_key="example_ai",
            company_name="Example AI",
            source_type="greenhouse",
            source_job_id="456",
            source_url="https://boards.greenhouse.io/exampleai/jobs/456",
            title="Senior Kubernetes Engineer",
            location="Remote",
            description="Build Kubernetes infrastructure.",
            canonical_key="example-ai:senior-kubernetes-engineer:remote",
            content_hash="hash-kubernetes",
        ),
    ]

    second_scan_postings = [
        make_posting(description="Build Linux infrastructure."),
        JobPosting(
            company_key="example_ai",
            company_name="Example AI",
            source_type="greenhouse",
            source_job_id="456",
            source_url="https://boards.greenhouse.io/exampleai/jobs/456",
            title="Senior Kubernetes Engineer",
            location="Remote",
            description="Build Kubernetes and GPU infrastructure.",
            canonical_key="example-ai:senior-kubernetes-engineer:remote",
            content_hash="hash-kubernetes-gpu",
        ),
    ]

    first_scan_results = [
        upsert_job_posting(database_path, posting)
        for posting in first_scan_postings
    ]

    second_scan_results = [
        upsert_job_posting(database_path, posting)
        for posting in second_scan_postings
    ]

    assert first_scan_results.count("new") == 2
    assert first_scan_results.count("seen") == 0
    assert first_scan_results.count("changed") == 0

    assert second_scan_results.count("new") == 0
    assert second_scan_results.count("seen") == 1
    assert second_scan_results.count("changed") == 1

    assert count_rows(database_path, "job_postings") == 2
    assert count_rows(database_path, "job_status") == 2



def make_job_history_record(
    company: str = "Example AI",
    role: str = "Senior Infrastructure Engineer",
    status: str = "Rejected - No Interview",
    notes: str = "Form rejection.",
) -> JobHistoryRecord:
    return JobHistoryRecord(
        history_type="pipeline",
        company=company,
        role=role,
        source="LinkedIn",
        ats_platform="Greenhouse",
        work_arrangement="Remote",
        location="Remote",
        comp_range="$160k-$200k",
        event_date="2026-06-01",
        status=status,
        outcome_category="Rejected No Interview",
        recruiter_contact="Unknown",
        technical_match="Very Strong",
        hiring_probability="Low",
        skills_signals="Linux, HPC, Infrastructure",
        primary_blocker="Generic Remote Competition",
        secondary_blocker=None,
        revisit="No",
        include_in_job_radar=True,
        import_key="pipeline:example-ai:senior-infrastructure-engineer",
        notes=notes,
    )


def get_job_history_row(database_path: Path) -> sqlite3.Row:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT *
            FROM job_history
            WHERE import_key = ?
            """,
            ("pipeline:example-ai:senior-infrastructure-engineer",),
        ).fetchone()

        assert row is not None
        return row


def test_upsert_job_history_record_inserts_new_record(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)

    result = upsert_job_history_record(database_path, make_job_history_record())
    row = get_job_history_row(database_path)

    assert result == "new"
    assert count_rows(database_path, "job_history") == 1
    assert row["history_type"] == "pipeline"
    assert row["company"] == "Example AI"
    assert row["role"] == "Senior Infrastructure Engineer"
    assert row["technical_match"] == "Very Strong"
    assert row["include_in_job_radar"] == 1


def test_upsert_job_history_record_updates_existing_record(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)

    first_result = upsert_job_history_record(
        database_path,
        make_job_history_record(notes="Original note."),
    )
    second_result = upsert_job_history_record(
        database_path,
        make_job_history_record(
            status="Rejected - After Interview",
            notes="Updated after recruiter screen.",
        ),
    )
    row = get_job_history_row(database_path)

    assert first_result == "new"
    assert second_result == "updated"
    assert count_rows(database_path, "job_history") == 1
    assert row["status"] == "Rejected - After Interview"
    assert row["notes"] == "Updated after recruiter screen."


def test_fetch_scan_runs_returns_none_when_no_scan_exists(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)

    assert fetch_active_scan_run(database_path) is None
    assert fetch_latest_scan_run(database_path) is None


def test_fetch_scan_runs_returns_active_and_latest_scan(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)

    scan_run_id = start_scan_run(
        database_path,
        requested_at="2026-07-15T16:00:00+00:00",
        companies_requested=4,
        companies_enabled=4,
        current_stage="collection",
    )
    update_scan_run_progress(
        database_path,
        scan_run_id=scan_run_id,
        current_stage="collection",
        companies_scanned=2,
        jobs_found=20,
    )

    active_row = fetch_active_scan_run(database_path)
    latest_row = fetch_latest_scan_run(database_path)

    assert active_row is not None
    assert latest_row is not None
    assert active_row["id"] == scan_run_id
    assert latest_row["id"] == scan_run_id
    assert active_row["status"] == "running"
    assert active_row["companies_scanned"] == 2


def test_fetch_active_scan_run_excludes_terminal_scan(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)

    scan_run_id = start_scan_run(
        database_path,
        requested_at="2026-07-15T17:00:00+00:00",
        companies_requested=1,
        companies_enabled=1,
    )
    fail_scan_run(
        database_path,
        scan_run_id=scan_run_id,
        finished_at="2026-07-15T17:01:00+00:00",
        failed_stage="configuration",
        failure_summary="invalid configuration",
    )

    latest_row = fetch_latest_scan_run(database_path)

    assert fetch_active_scan_run(database_path) is None
    assert latest_row is not None
    assert latest_row["id"] == scan_run_id
    assert latest_row["status"] == "failed"
