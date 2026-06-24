import sqlite3
from pathlib import Path

from job_radar.storage import initialize_database, upsert_job_posting
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


def get_job_row(database_path: Path) -> sqlite3.Row:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM job_postings WHERE canonical_key = ?",
            ("example-ai:senior-infrastructure-engineer:remote",),
        ).fetchone()

        assert row is not None
        return row


def test_upsert_job_posting_inserts_new_job_and_status(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)

    result = upsert_job_posting(database_path, make_posting())

    assert result == "new"
    assert count_rows(database_path, "job_postings") == 1
    assert count_rows(database_path, "job_status") == 1


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