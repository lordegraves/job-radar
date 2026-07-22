"""Tests application workflow rules and safe movement between tracker and history."""

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from job_radar.history_models import JobHistoryRecord
from job_radar.models import JobPosting
from job_radar.storage import initialize_database, upsert_job_history_record
from job_radar.tracker.tracker_models import ApplicationRecord
from job_radar.tracker.tracker_service import (
    build_application_record_from_history_record,
    build_application_record_from_posting,
    get_application_workflow_state,
    should_track_history_record,
    track_application_from_posting,
    track_application_from_posting_if_missing,
    update_history_record_workflow,
    update_tracker_application_workflow,
)
from job_radar.tracker.tracker_storage import get_application, initialize_tracker_tables


def make_posting() -> JobPosting:
    return JobPosting(
        company_key="example_mobility",
        company_name="Example Mobility",
        source_type="greenhouse",
        source_job_id="123",
        source_url="https://example.com/jobs/senior-sre",
        title="Senior Site Reliability Engineer",
        location="Remote",
        description="Own Linux infrastructure and production reliability.",
        canonical_key="example-mobility:senior-site-reliability-engineer:remote",
        content_hash="hash-example-mobility-sre",
    )


def make_history_record(
    *,
    job_radar_id: str | None = "jr-example-ai-12345678",
    import_key: str = "job-radar-id:jr-example-ai-12345678",
    decision: str = "Applied",
    outcome: str | None = "Pending / In Progress",
    posting_url: str | None = "https://example.com/jobs/senior-sre",
    notes: str | None = "Imported from spreadsheet.",
) -> JobHistoryRecord:
    return JobHistoryRecord(
        history_type="Pipeline",
        company="Example AI",
        role="Senior Site Reliability Engineer",
        source="Job Radar",
        ats_platform=None,
        work_arrangement=None,
        location=None,
        comp_range=None,
        event_date="2026-07-03",
        status=decision,
        outcome_category=outcome,
        recruiter_contact=None,
        technical_match=None,
        hiring_probability=None,
        skills_signals=None,
        primary_blocker=None,
        secondary_blocker=None,
        revisit=None,
        include_in_job_radar=True,
        import_key=import_key,
        notes=notes,
        job_radar_id=job_radar_id,
        posting_url=posting_url,
        lead_source="Job Radar",
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
    assert record.company_name == "Example Mobility"
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
    assert application.company_name == "Example Mobility"
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


def test_should_track_history_record_tracks_active_application() -> None:
    record = make_history_record(
        decision="Applied",
        outcome="Pending / In Progress",
    )

    assert should_track_history_record(record) is True


def test_should_track_history_record_does_not_track_passed_job() -> None:
    record = make_history_record(
        decision="Passed",
        outcome="N/A",
    )

    assert should_track_history_record(record) is False


def test_should_track_history_record_does_not_track_rejected_application() -> None:
    record = make_history_record(
        decision="Applied",
        outcome="Rejected - No Interview",
    )

    assert should_track_history_record(record) is False


def test_should_track_history_record_tracks_active_outcomes() -> None:
    active_outcomes = [
        "Pending / In Progress",
        "Interview Scheduled",
        "Interview Completed",
        "Waiting For Feedback",
        "Offer",
        "Dormant",
        "N/A",
    ]

    for outcome in active_outcomes:
        record = make_history_record(
            decision="Applied",
            outcome=outcome,
        )

        assert should_track_history_record(record) is True


def test_should_track_history_record_routes_history_outcomes_to_history() -> None:
    history_outcomes = [
        "Closed Before Application",
        "Rejected - No Interview",
        "Rejected - After Interview",
        "Withdrawn",
    ]

    for outcome in history_outcomes:
        record = make_history_record(
            decision="Applied",
            outcome=outcome,
        )

        assert should_track_history_record(record) is False


def test_should_track_history_record_rejects_noncanonical_outcome_aliases() -> None:
    alias_outcomes = [
        "n a",
        "na",
        "Alive Until Declared Dead",
    ]

    for outcome in alias_outcomes:
        record = make_history_record(
            decision="Applied",
            outcome=outcome,
        )

        assert should_track_history_record(record) is False


def test_should_track_history_record_routes_revisit_to_history() -> None:
    record = make_history_record(
        decision="Revisit",
        outcome="N/A",
    )

    assert should_track_history_record(record) is False


def test_build_application_record_from_history_record_uses_job_radar_id() -> None:
    record = make_history_record(
        decision="Applied",
        outcome="Pending / In Progress",
    )

    application = build_application_record_from_history_record(record)

    assert application.job_radar_id == "jr-example-ai-12345678"
    assert application.company_name == "Example AI"
    assert application.role_title == "Senior Site Reliability Engineer"
    assert application.source_url == "https://example.com/jobs/senior-sre"
    assert application.status == "Applied"
    assert application.outcome == "Pending / In Progress"
    assert application.notes == "Imported from spreadsheet."
    assert application.applied_on == "2026-07-03"
    assert application.last_activity_on == "2026-07-03"


def test_build_application_record_from_history_record_keeps_human_notes() -> None:
    record = make_history_record(
        decision="Applied",
        outcome="Pending / In Progress",
        notes="Recruiter replied.",
    )

    application = build_application_record_from_history_record(record)

    assert application.notes == "Recruiter replied."


def test_build_application_record_from_history_record_drops_generated_report_notes() -> None:
    record = make_history_record(
        decision="Applied",
        outcome="Pending / In Progress",
        notes=(
            "- Score: 120 - Why it is a top match: score 120 meets "
            "top-match threshold 120 - Why this matched: linux, infrastructure "
            "- Technical match: Very Strong - Resume evidence: Linux infrastructure"
        ),
    )

    application = build_application_record_from_history_record(record)

    assert application.notes is None


def test_build_application_record_from_history_record_maps_interview_outcome() -> None:
    record = make_history_record(
        decision="Applied",
        outcome="Interview Scheduled",
    )

    application = build_application_record_from_history_record(record)

    assert application.status == "Applied"
    assert application.outcome == "Interview Scheduled"


def test_build_application_record_from_history_record_maps_offer_outcome() -> None:
    record = make_history_record(
        decision="Applied",
        outcome="Offer",
    )

    application = build_application_record_from_history_record(record)

    assert application.status == "Applied"
    assert application.outcome == "Offer"


def test_build_application_record_from_history_record_maps_dormant_outcome() -> None:
    record = make_history_record(
        decision="Applied",
        outcome="Dormant",
    )

    application = build_application_record_from_history_record(record)

    assert application.status == "Applied"
    assert application.outcome == "Dormant"


def test_build_application_record_from_history_record_generates_manual_id() -> None:
    record = make_history_record(
        job_radar_id=None,
        import_key="posting-url:https://example.com/manual-lead",
        decision="Applied",
        outcome=None,
        posting_url="https://example.com/manual-lead",
    )

    application = build_application_record_from_history_record(record)

    assert application.job_radar_id.startswith(
        "jr_manual_example_ai_senior_site_reliability_engineer_"
    )
    assert not application.job_radar_id.startswith("posting-url:")
    assert application.status == "Applied"
    assert application.source_url == "https://example.com/manual-lead"


def test_should_track_history_record_does_not_track_rejected_after_interview() -> None:
    record = make_history_record(
        decision="Applied",
        outcome="Rejected - After Interview",
    )

    assert should_track_history_record(record) is False


def test_get_application_workflow_state_marks_due_follow_up() -> None:
    application = build_application_record_from_posting(
        make_posting(),
        status="applied",
        follow_up_on="2026-07-04",
    )

    assert (
        get_application_workflow_state(
            application,
            today=date(2026, 7, 5),
        )
        == "follow_up_due"
    )


def test_get_application_workflow_state_marks_future_follow_up_scheduled() -> None:
    application = build_application_record_from_posting(
        make_posting(),
        status="applied",
        follow_up_on="2026-07-10",
    )

    assert (
        get_application_workflow_state(
            application,
            today=date(2026, 7, 5),
        )
        == "follow_up_scheduled"
    )


def test_get_application_workflow_state_marks_invalid_follow_up_for_review() -> None:
    application = build_application_record_from_posting(
        make_posting(),
        status="applied",
        follow_up_on="not-a-date",
    )

    assert (
        get_application_workflow_state(
            application,
            today=date(2026, 7, 5),
        )
        == "needs_date_review"
    )


def test_get_application_workflow_state_marks_active_pipeline() -> None:
    application = build_application_record_from_posting(
        make_posting(),
        status="Applied",
        outcome="Interview Scheduled",
    )

    assert (
        get_application_workflow_state(
            application,
            today=date(2026, 7, 5),
        )
        == "active_pipeline"
    )


def test_get_application_workflow_state_marks_rejected_applications_closed() -> None:
    application = build_application_record_from_posting(
        make_posting(),
        status="rejected",
    )

    assert (
        get_application_workflow_state(
            application,
            today=date(2026, 7, 5),
        )
        == "closed"
    )


def test_get_application_workflow_state_marks_withdrawn_applications_closed() -> None:
    application = build_application_record_from_posting(
        make_posting(),
        status="withdrawn",
    )

    assert (
        get_application_workflow_state(
            application,
            today=date(2026, 7, 5),
        )
        == "closed"
    )


def test_get_application_workflow_state_marks_waiting_applications() -> None:
    application = build_application_record_from_posting(
        make_posting(),
        status="applied",
    )

    assert (
        get_application_workflow_state(
            application,
            today=date(2026, 7, 5),
        )
        == "waiting"
    )


def test_get_application_workflow_state_marks_dormant_outcome_as_dormant() -> None:
    application = build_application_record_from_posting(
        make_posting(),
        status="Applied",
        outcome="Dormant",
    )

    assert (
        get_application_workflow_state(
            application,
            today=date(2026, 7, 5),
        )
        == "dormant"
    )


def test_get_application_workflow_state_marks_recent_activity_waiting() -> None:
    application = build_application_record_from_posting(
        make_posting(),
        status="applied",
    )
    application = ApplicationRecord(
        **{
            **application.__dict__,
            "last_activity_on": "2026-06-20",
        }
    )

    assert (
        get_application_workflow_state(
            application,
            today=date(2026, 7, 5),
        )
        == "waiting"
    )


def test_get_application_workflow_state_marks_month_old_activity_dormant() -> None:
    application = build_application_record_from_posting(
        make_posting(),
        status="applied",
    )
    application = ApplicationRecord(
        **{
            **application.__dict__,
            "last_activity_on": "2026-05-20",
        }
    )

    assert (
        get_application_workflow_state(
            application,
            today=date(2026, 7, 5),
        )
        == "dormant"
    )


def test_get_application_workflow_state_marks_old_activity_stale() -> None:
    application = build_application_record_from_posting(
        make_posting(),
        status="applied",
    )
    application = ApplicationRecord(
        **{
            **application.__dict__,
            "last_activity_on": "2026-03-01",
        }
    )

    assert (
        get_application_workflow_state(
            application,
            today=date(2026, 7, 5),
        )
        == "stale"
    )


def test_get_application_workflow_state_marks_very_old_activity_presumed_closed() -> None:
    application = build_application_record_from_posting(
        make_posting(),
        status="applied",
    )
    application = ApplicationRecord(
        **{
            **application.__dict__,
            "last_activity_on": "2026-01-01",
        }
    )

    assert (
        get_application_workflow_state(
            application,
            today=date(2026, 7, 5),
        )
        == "presumed_closed"
    )


def test_get_application_workflow_state_uses_applied_on_when_last_activity_missing() -> None:
    application = build_application_record_from_posting(
        make_posting(),
        status="applied",
    )
    application = ApplicationRecord(
        **{
            **application.__dict__,
            "applied_on": "2026-03-01",
        }
    )

    assert (
        get_application_workflow_state(
            application,
            today=date(2026, 7, 5),
        )
        == "stale"
    )


def test_get_application_workflow_state_marks_invalid_activity_date_for_review() -> None:
    application = build_application_record_from_posting(
        make_posting(),
        status="applied",
    )
    application = ApplicationRecord(
        **{
            **application.__dict__,
            "last_activity_on": "not-a-date",
        }
    )

    assert (
        get_application_workflow_state(
            application,
            today=date(2026, 7, 5),
        )
        == "needs_date_review"
    )


def test_get_application_workflow_state_marks_future_activity_date_for_review() -> None:
    application = build_application_record_from_posting(
        make_posting(),
        status="applied",
    )
    application = ApplicationRecord(
        **{
            **application.__dict__,
            "last_activity_on": "2026-07-10",
        }
    )

    assert (
        get_application_workflow_state(
            application,
            today=date(2026, 7, 5),
        )
        == "needs_date_review"
    )


def test_update_tracker_application_workflow_moves_record_to_history(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)
    posting = make_posting()

    track_application_from_posting(
        str(database_path),
        posting,
        status="Applied",
        outcome="Pending / In Progress",
    )

    result = update_tracker_application_workflow(
        str(database_path),
        job_radar_id=posting.job_radar_id,
        status="Applied",
        outcome="Rejected - No Interview",
        last_activity_on="2026-07-15",
        notes="Application rejected.",
    )

    with sqlite3.connect(database_path) as connection:
        tracker_count = connection.execute(
            "SELECT COUNT(*) FROM application_tracker"
        ).fetchone()[0]
        history_count = connection.execute(
            "SELECT COUNT(*) FROM job_history"
        ).fetchone()[0]

    assert result == "moved_to_history"
    assert tracker_count == 0
    assert history_count == 1


def test_update_tracker_application_workflow_rolls_back_failed_move(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)
    posting = make_posting()

    track_application_from_posting(
        str(database_path),
        posting,
        status="Applied",
        outcome="Pending / In Progress",
    )

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_tracker_delete
            BEFORE DELETE ON application_tracker
            BEGIN
                SELECT RAISE(ABORT, 'forced tracker delete failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError):
        update_tracker_application_workflow(
            str(database_path),
            job_radar_id=posting.job_radar_id,
            status="Applied",
            outcome="Rejected - No Interview",
            last_activity_on="2026-07-15",
        )

    with sqlite3.connect(database_path) as connection:
        tracker_count = connection.execute(
            "SELECT COUNT(*) FROM application_tracker"
        ).fetchone()[0]
        history_count = connection.execute(
            "SELECT COUNT(*) FROM job_history"
        ).fetchone()[0]

    assert tracker_count == 1
    assert history_count == 0


def test_update_history_record_workflow_moves_record_to_tracker(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)
    record = make_history_record(
        decision="Applied",
        outcome="Rejected - No Interview",
    )
    upsert_job_history_record(database_path, record)

    result = update_history_record_workflow(
        str(database_path),
        import_key=record.import_key,
        company=record.company,
        role=record.role,
        source=record.source,
        event_date=record.event_date,
        status="Applied",
        outcome="Pending / In Progress",
        notes="Application reopened.",
    )

    with sqlite3.connect(database_path) as connection:
        tracker_count = connection.execute(
            "SELECT COUNT(*) FROM application_tracker"
        ).fetchone()[0]
        history_count = connection.execute(
            "SELECT COUNT(*) FROM job_history"
        ).fetchone()[0]

    assert result == "moved_to_tracker"
    assert tracker_count == 1
    assert history_count == 0


def test_update_history_record_workflow_rolls_back_failed_move(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    initialize_database(database_path)
    record = make_history_record(
        decision="Applied",
        outcome="Rejected - No Interview",
    )
    upsert_job_history_record(database_path, record)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_history_delete
            BEFORE DELETE ON job_history
            BEGIN
                SELECT RAISE(ABORT, 'forced history delete failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError):
        update_history_record_workflow(
            str(database_path),
            import_key=record.import_key,
            company=record.company,
            role=record.role,
            source=record.source,
            event_date=record.event_date,
            status="Applied",
            outcome="Pending / In Progress",
        )

    with sqlite3.connect(database_path) as connection:
        tracker_count = connection.execute(
            "SELECT COUNT(*) FROM application_tracker"
        ).fetchone()[0]
        history_count = connection.execute(
            "SELECT COUNT(*) FROM job_history"
        ).fetchone()[0]

    assert tracker_count == 0
    assert history_count == 1
