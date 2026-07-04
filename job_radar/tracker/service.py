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
        notes=record.notes,
    )


def _tracker_status_from_history_record(record: JobHistoryRecord) -> str:
    decision = _normalized_history_value(record.status)
    outcome = _normalized_history_value(record.outcome_category)

    if outcome in {"rejected no interview", "rejected after interview"}:
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
