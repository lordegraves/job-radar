from dataclasses import dataclass


@dataclass(frozen=True)
class ApplicationRecord:
    job_radar_id: str
    company_name: str
    role_title: str
    source_url: str | None = None
    status: str = "review_needed"
    follow_up_on: str | None = None
    outcome: str | None = None
    notes: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
