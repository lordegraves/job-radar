from pathlib import Path

from job_radar.models import JobPosting
from job_radar.tracker.service import (
    build_application_record_from_posting,
    track_application_from_posting,
    track_application_from_posting_if_missing,
)
from job_radar.tracker.storage import get_application, initialize_tracker_tables


def make_posting() -> JobPosting:
    return JobPosting(
        company_key="stack_av",
        company_name="Stack AV",
        source_type="greenhouse",
        source_job_id="123",
        source_url="https://example.com/jobs/senior-sre",
        title="Senior Site Reliability Engineer",
        location="Remote",
        description="Own Linux infrastructure and production reliability.",
        canonical_key="stack-av:senior-site-reliability-engineer:remote",
        content_hash="hash-stack-av-sre",
    )


def test_build_application_record_from_posting_uses_job_identity() -> None:
    posting = make_posting()

    record = build_application_record_from_posting(
        posting,
        status="applied",
        follow_up_on="2026-07-10",
        outcome=None,
        notes="Applied through company site.",
    )

    assert record.job_radar_id == posting.job_radar_id
    assert record.company_name == "Stack AV"
    assert record.role_title == "Senior Site Reliability Engineer"
    assert record.source_url == "https://example.com/jobs/senior-sre"
    assert record.status == "applied"
    assert record.follow_up_on == "2026-07-10"
    assert record.outcome is None
    assert record.notes == "Applied through company site."


def test_track_application_from_posting_inserts_application(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_tracker_tables(database_path)
    posting = make_posting()

    result = track_application_from_posting(
        str(database_path),
        posting,
        status="review_needed",
        notes="Review before applying.",
    )
    application = get_application(database_path, posting.job_radar_id)

    assert result == "new"
    assert application is not None
    assert application.job_radar_id == posting.job_radar_id
    assert application.company_name == "Stack AV"
    assert application.role_title == "Senior Site Reliability Engineer"
    assert application.status == "review_needed"
    assert application.notes == "Review before applying."


def test_track_application_from_posting_updates_existing_application(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_tracker_tables(database_path)
    posting = make_posting()

    first_result = track_application_from_posting(
        str(database_path),
        posting,
        status="review_needed",
        notes="Initial review.",
    )
    second_result = track_application_from_posting(
        str(database_path),
        posting,
        status="applied",
        follow_up_on="2026-07-10",
        notes="Applied through company site.",
    )
    application = get_application(database_path, posting.job_radar_id)

    assert first_result == "new"
    assert second_result == "updated"
    assert application is not None
    assert application.status == "applied"
    assert application.follow_up_on == "2026-07-10"
    assert application.notes == "Applied through company site."


def test_track_application_from_posting_if_missing_inserts_missing_application(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_tracker_tables(database_path)
    posting = make_posting()

    result = track_application_from_posting_if_missing(
        str(database_path),
        posting,
        status="review_needed",
        notes="Added from scan.",
    )
    application = get_application(database_path, posting.job_radar_id)

    assert result == "new"
    assert application is not None
    assert application.status == "review_needed"
    assert application.notes == "Added from scan."


def test_track_application_from_posting_if_missing_does_not_overwrite_existing_application(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_tracker_tables(database_path)
    posting = make_posting()

    first_result = track_application_from_posting(
        str(database_path),
        posting,
        status="applied",
        follow_up_on="2026-07-10",
        notes="Already applied.",
    )
    second_result = track_application_from_posting_if_missing(
        str(database_path),
        posting,
        status="review_needed",
        notes="Added from later scan.",
    )
    application = get_application(database_path, posting.job_radar_id)

    assert first_result == "new"
    assert second_result == "existing"
    assert application is not None
    assert application.status == "applied"
    assert application.follow_up_on == "2026-07-10"
    assert application.notes == "Already applied."
