from datetime import date

from job_radar.job_history import JobHistoryRecord
from job_radar.models import JobPosting
from job_radar.tracker.tracker_models import ApplicationRecord
from job_radar.tracker.tracker_storage import get_application, upsert_application


HISTORY_DECISIONS = {
    "Passed",
    "Withdrawn",
    "Revisit",
}

TRACKER_DECISIONS = {
    "Applied",
}

APPLIED_HISTORY_OUTCOMES = {
    "Closed Before Application",
    "Rejected - No Interview",
    "Rejected - After Interview",
    "Withdrawn",
}

TRACKER_OUTCOMES = {
    "Pending / In Progress",
    "Interview Scheduled",
    "Interview Completed",
    "Waiting For Feedback",
    "Offer",
    "Dormant",
    "N/A",
}


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
    decision = _canonical_history_value(record.status)
    outcome = _canonical_history_value(record.outcome_category)

    # Passed, Withdrawn, and Revisit are terminal archive decisions.
    if decision in HISTORY_DECISIONS:
        return False

    if decision not in TRACKER_DECISIONS:
        return False

    # Applied jobs stay in Tracker unless the outcome is explicitly terminal.
    if outcome in APPLIED_HISTORY_OUTCOMES:
        return False

    return outcome in TRACKER_OUTCOMES


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
        applied_on=record.event_date,
        last_activity_on=record.event_date,
    )


def build_history_record_from_application_record(
    application: ApplicationRecord,
    *,
    status: str,
    outcome: str,
    event_date: str | None = None,
    notes: str | None = None,
) -> JobHistoryRecord:
    return JobHistoryRecord(
        history_type="Pipeline",
        company=application.company_name,
        role=application.role_title,
        source="Job Radar Tracker",
        ats_platform=None,
        work_arrangement=None,
        location=None,
        comp_range=None,
        event_date=(
            event_date
            or application.last_activity_on
            or application.applied_on
            or date.today().isoformat()
        ),
        status=status,
        outcome_category=outcome,
        recruiter_contact=None,
        technical_match=None,
        hiring_probability=None,
        skills_signals=None,
        primary_blocker=None,
        secondary_blocker=None,
        revisit=None,
        include_in_job_radar=True,
        import_key=_build_tracker_history_import_key(application.job_radar_id),
        notes=notes,
        job_radar_id=application.job_radar_id,
        posting_url=application.source_url,
        lead_source="Job Radar Tracker",
    )


def is_terminal_tracker_outcome(outcome: str | None) -> bool:
    return _canonical_history_value(outcome) in APPLIED_HISTORY_OUTCOMES


def _build_tracker_history_import_key(job_radar_id: str) -> str:
    return f"job-radar-id:{_history_import_key_token(job_radar_id)}"


def _history_import_key_token(value: str) -> str:
    return "-".join(_canonical_history_value(value).lower().split())


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
    outcome = _canonical_history_value(application.outcome)

    if normalized_status in {"rejected", "withdrawn"}:
        return "closed"

    if outcome in APPLIED_HISTORY_OUTCOMES:
        return "closed"

    if normalized_status in {"interviewing", "offer"}:
        return "active_pipeline"

    if outcome in {"Interview Scheduled", "Interview Completed", "Waiting For Feedback", "Offer"}:
        return "active_pipeline"

    if normalized_status == "follow_up_due":
        return "follow_up_due"

    if normalized_status == "dormant" or outcome == "Dormant":
        return "dormant"

    follow_up_date = _parse_date(application.follow_up_on)

    if follow_up_date is not None:
        if follow_up_date <= reference_date:
            return "follow_up_due"

        return "follow_up_scheduled"

    if application.follow_up_on:
        return "needs_date_review"

    activity_date = _get_application_activity_date(application)

    if activity_date is None:
        if application.last_activity_on or application.applied_on:
            return "needs_date_review"

        return "waiting"

    if activity_date > reference_date:
        return "needs_date_review"

    days_since_activity = (reference_date - activity_date).days

    if days_since_activity > 180:
        return "presumed_closed"

    if days_since_activity > 90:
        return "stale"

    if days_since_activity > 30:
        return "dormant"

    return "waiting"


def _get_application_activity_date(application: ApplicationRecord) -> date | None:
    return _parse_date(application.last_activity_on) or _parse_date(application.applied_on)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _tracker_status_from_history_record(record: JobHistoryRecord) -> str:
    decision = _canonical_history_value(record.status)

    if decision == "Applied":
        return "Applied"

    return decision or "Applied"


def _canonical_history_value(value: str | None) -> str:
    if value is None:
        return ""

    return " ".join(value.strip().split())


def _normalized_history_value(value: str | None) -> str:
    if value is None:
        return ""

    return " ".join(value.lower().replace("/", " ").replace("-", " ").split())
