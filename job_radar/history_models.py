"""Define the common record shape used for imported job-search history."""

from dataclasses import dataclass


@dataclass(frozen=True)
class JobHistoryRecord:
    history_type: str
    company: str
    role: str
    source: str | None
    ats_platform: str | None
    work_arrangement: str | None
    location: str | None
    comp_range: str | None
    event_date: str | None
    status: str | None
    outcome_category: str | None
    recruiter_contact: str | None
    technical_match: str | None
    hiring_probability: str | None
    skills_signals: str | None
    primary_blocker: str | None
    secondary_blocker: str | None
    revisit: str | None
    include_in_job_radar: bool
    import_key: str
    notes: str | None
    job_radar_id: str | None = None
    posting_url: str | None = None
    lead_source: str | None = None
    applied_on: str | None = None
    last_activity_on: str | None = None
    follow_up_on: str | None = None
