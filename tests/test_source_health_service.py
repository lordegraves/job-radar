"""Verify current source health is not contradicted by older scan evidence."""

from pathlib import Path

from job_radar.database import connect_database
from job_radar.employer_admin_service import create_employer
from job_radar.employer_connection_service import record_scan_connection_result
from job_radar.source_health_service import build_source_health_items
from job_radar.storage import record_scan_error, record_scan_run


def test_newer_successful_test_clears_older_scan_warning_tone(tmp_path: Path) -> None:
    database_path = tmp_path / "junior.sqlite3"
    employer = create_employer(
        database_path,
        name="Example Company",
        source_type="greenhouse",
        source_config={"source_slug": "example-company"},
        notes="",
    ).employer
    scan_run_id = record_scan_run(
        database_path,
        generated_at="2026-08-06 10:00:00",
        companies_enabled=1,
        jobs_collected=0,
        actionable_jobs_stored=0,
        jobs_not_actionable=0,
        jobs_new=0,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=1,
        top_matches_count=0,
        review_needed_count=0,
    )
    error_id = record_scan_error(
        database_path,
        scan_run_id=scan_run_id,
        company_key=employer.employer_id,
        source_type="greenhouse",
        error_type="network_failure",
        error_message="The source could not be reached during the scan.",
    )
    with connect_database(database_path) as connection:
        connection.execute(
            "UPDATE scan_errors SET created_at = ? WHERE id = ?",
            ("2026-08-06 10:00:00", error_id),
        )

    record_scan_connection_result(database_path, employer.employer_id, job_count=3)
    with connect_database(database_path) as connection:
        connection.execute(
            """
            UPDATE employer_sources
            SET last_connection_test_at = ?, last_connection_success_at = ?
            WHERE employer_id = ?
            """,
            ("2026-08-06 11:00:00", "2026-08-06 11:00:00", employer.employer_id),
        )

    item = build_source_health_items(database_path)[0]

    assert item.state == "success"
    assert item.tone == "success"
    assert item.latest_scan_state == "Warning before latest source test"
