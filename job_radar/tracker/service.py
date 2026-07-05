from datetime import date

from job_radar.job_history import JobHistoryRecord
from job_radar.models import JobPosting
from job_radar.tracker.models import ApplicationRecord
from job_radar.tracker.storage import get_application, upsert_application


def build_application_record_from_posting(
    posting: JobPosting,
    *,
    status: str = "review_needed",
    follow_up_on: str | None = None,
    outcome: str | None = None,
    notes: str | None = None,
) -> ApplicationRecord:
    return ApplicationRecord(
        job_radar_id=posting.job_radar_id,
        company_name=posting.company_name,
        role_title=posting.title,
        source_url=posting.source_url,
        status=status,
        follow_up_on=follow_up_on,
        outcome=outcome,
        notes=notes,
    )


def track_application_from_posting(
    database_path: str,
    posting: JobPosting,
    *,
    status: str = "review_needed",
    follow_up_on: str | None = None,
    outcome: str | None = None,
    notes: str | None = None,
) -> str:
    record = build_application_record_from_posting(
        posting,
        status=status,
        follow_up_on=follow_up_on,
        outcome=outcome,
        notes=notes,
    )

    return upsert_application(database_path, record)


def track_application_from_posting_if_missing(
    database_path: str,
    posting: JobPosting,
    *,
    status: str = "review_needed",
    follow_up_on: str | None = None,
    outcome: str | None = None,
    notes: str | None = None,
) -> str:
    existing_application = get_application(database_path, posting.job_radar_id)

    if existing_application is not None:
        return "existing"

    return track_application_from_posting(
        database_path,
        posting,
        status=status,
        follow_up_on=follow_up_on,
        outcome=outcome,
        notes=notes,
    )


def should_track_history_record(record: JobHistoryRecord) -> bool:
    decision = _normalized_history_value(record.status)
    outcome = _normalized_history_value(record.outcome_category)

    if decision in {
        "passed",
        "skipped",
        "not interested",
        "revisit if recruiter contacts me",
    }:
        return False

    if decision in {
        "applied",
        "interested",
        "review needed",
        "follow up due",
        "interviewing",
        "offer",
        "withdrawn",
        "rejected no interview",
        "rejected after interview",
    }:
        return True

    if outcome in {
        "pending in progress",
        "alive until declared dead",
        "dormant",
        "rejected no interview",
        "rejected after interview",
        "withdrawn",
    }:
        return True

    return False


def build_application_record_from_history_record(
    record: JobHistoryRecord,
) -> ApplicationRecord:
    return ApplicationRecord(
        job_radar_id=record.job_radar_id or record.import_key,
        company_name=record.company,
        role_title=record.role,
        source_url=record.posting_url,
        status=_tracker_status_from_history_record(record),
        outcome=record.outcome_category,
        notes=_clean_history_notes_for_tracker(record.notes),
    )


def _clean_history_notes_for_tracker(notes: str | None) -> str | None:
    if notes is None:
        return None

    normalized_notes = " ".join(notes.split())
    normalized_notes_lower = normalized_notes.lower()

    generated_report_markers = [
        "- score:",
        "- why it is a top match:",
        "- why this matched:",
        "- technical match:",
        "- resume match:",
        "- resume evidence:",
        "- resume gaps:",
    ]

    marker_count = sum(
        1 for marker in generated_report_markers if marker in normalized_notes_lower
    )

    if marker_count >= 2:
        return None

    return notes


def get_application_workflow_state(
    application: ApplicationRecord,
    *,
    today: date | None = None,
) -> str:
    reference_date = today or date.today()
    normalized_status = _normalized_history_value(application.status)

    if normalized_status in {"rejected", "withdrawn", "dormant"}:
        return "closed"

    if normalized_status in {"interviewing", "offer"}:
        return "active_pipeline"

    if normalized_status == "follow_up_due":
        return "follow_up_due"

    follow_up_date = _parse_follow_up_date(application.follow_up_on)

    if follow_up_date is not None:
        if follow_up_date <= reference_date:
            return "follow_up_due"

        return "follow_up_scheduled"

    if application.follow_up_on:
        return "needs_date_review"

    if normalized_status in {"applied", "interested", "review_needed"}:
        return "waiting"

    return "waiting"


def _parse_follow_up_date(value: str | None) -> date | None:
    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _tracker_status_from_history_record(record: JobHistoryRecord) -> str:
    decision = _normalized_history_value(record.status)
    outcome = _normalized_history_value(record.outcome_category)

    if (
        decision in {"rejected no interview", "rejected after interview"}
        or outcome in {"rejected no interview", "rejected after interview"}
    ):
        return "rejected"

    if outcome == "dormant":
        return "dormant"

    if decision == "withdrawn" or outcome == "withdrawn":
        return "withdrawn"

    if decision == "interested":
        return "interested"

    if decision == "review needed":
        return "review_needed"

    if decision == "follow up due":
        return "follow_up_due"

    if decision == "interviewing":
        return "interviewing"

    if decision == "offer":
        return "offer"

    if decision == "applied":
        return "applied"

    return "review_needed"


def _normalized_history_value(value: str | None) -> str:
    if value is None:
        return ""

    return " ".join(value.lower().replace("/", " ").replace("-", " ").split())
