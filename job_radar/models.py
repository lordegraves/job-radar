from dataclasses import dataclass


@dataclass(frozen=True)
class JobPosting:
    company_key: str
    company_name: str
    source_type: str
    source_url: str
    title: str
    location: str | None
    description: str | None
    source_job_id: str | None = None
    remote_status: str | None = None
    salary_text: str | None = None
    canonical_key: str | None = None
    content_hash: str | None = None