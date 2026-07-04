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
