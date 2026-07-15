from pathlib import Path

from job_radar.scan_progress import build_scan_progress_view
from job_radar.storage import (
    complete_scan_run,
    fail_scan_run,
    fetch_latest_scan_run,
    initialize_database,
    start_scan_run,
    update_scan_run_progress,
)


def test_build_scan_progress_view_returns_none_without_scan() -> None:
    assert build_scan_progress_view(None) is None


def test_build_scan_progress_view_calculates_collection_progress(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)

    scan_run_id = start_scan_run(
        database_path,
        requested_at="2026-07-15T18:00:00+00:00",
        companies_requested=4,
        companies_enabled=4,
        current_stage="collection",
    )
    update_scan_run_progress(
        database_path,
        scan_run_id=scan_run_id,
        current_stage="collection",
        companies_scanned=2,
        jobs_found=25,
        collector_errors=1,
    )

    view = build_scan_progress_view(
        fetch_latest_scan_run(database_path)
    )

    assert view is not None
    assert view.status == "running"
    assert view.status_label == "Running"
    assert view.stage_label == "Collecting company jobs"
    assert view.progress_percent == 45
    assert view.companies_requested == 4
    assert view.companies_scanned == 2
    assert view.jobs_found == 25
    assert view.collector_errors == 1
    assert view.is_running
    assert not view.is_terminal
    assert not view.succeeded


def test_build_scan_progress_view_marks_completed_scan_at_100_percent(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)

    scan_run_id = start_scan_run(
        database_path,
        requested_at="2026-07-15T19:00:00+00:00",
        companies_requested=2,
        companies_enabled=2,
    )
    complete_scan_run(
        database_path,
        scan_run_id=scan_run_id,
        generated_at="2026-07-15T19:05:00+00:00",
        finished_at="2026-07-15T19:05:00+00:00",
        companies_scanned=2,
        jobs_collected=30,
        actionable_jobs_stored=3,
        jobs_not_actionable=27,
        jobs_new=3,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=0,
        top_matches_count=1,
        review_needed_count=2,
        report_status="completed",
        email_status="not_requested",
    )

    view = build_scan_progress_view(
        fetch_latest_scan_run(database_path)
    )

    assert view is not None
    assert view.status == "completed"
    assert view.status_label == "Completed"
    assert view.stage_label == "Scan completed"
    assert view.progress_percent == 100
    assert not view.is_running
    assert view.is_terminal
    assert view.succeeded


def test_build_scan_progress_view_preserves_failed_stage(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)

    scan_run_id = start_scan_run(
        database_path,
        requested_at="2026-07-15T20:00:00+00:00",
        companies_requested=3,
        companies_enabled=3,
        current_stage="report_generation",
    )
    fail_scan_run(
        database_path,
        scan_run_id=scan_run_id,
        finished_at="2026-07-15T20:03:00+00:00",
        failed_stage="report_generation",
        failure_summary="report writer failed",
        companies_scanned=3,
        jobs_found=40,
    )

    view = build_scan_progress_view(
        fetch_latest_scan_run(database_path)
    )

    assert view is not None
    assert view.status == "failed"
    assert view.status_label == "Failed"
    assert view.stage_label == "Generating reports"
    assert view.progress_percent == 92
    assert view.failure_summary == "report writer failed"
    assert not view.is_running
    assert view.is_terminal
    assert not view.succeeded
