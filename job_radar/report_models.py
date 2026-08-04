"""Define the complete scan result shared by report and email builders."""

from dataclasses import dataclass

from job_radar.models import JobPosting
from job_radar.scored_posting import ScoredPosting


@dataclass(frozen=True)
class ScanError:
    company_key: str
    company_name: str
    source_type: str
    message: str


@dataclass(frozen=True)
class ScanReport:
    companies_enabled: int
    jobs_collected: int
    jobs_new: int
    jobs_seen: int
    jobs_changed: int
    collector_errors: list[ScanError]
    postings: list[JobPosting]
    scored_postings: list[ScoredPosting] | None = None
    new_scored_postings: list[ScoredPosting] | None = None
    omitted_scored_postings: list[ScoredPosting] | None = None
    generated_at: str | None = None
    top_match_min_score: int | None = None
    review_needed_min_score: int | None = None
    jobs_stored: int | None = None
    jobs_omitted: int | None = None
    history_context: list[str] | None = None
    tracker_workflow_summary: dict[str, int] | None = None
    llm_jobs_reviewed: int = 0
    llm_reviews_reused: int = 0
    llm_failures: int = 0
