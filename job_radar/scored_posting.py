"""Bundle a job posting with every score, decision, and history result it earned."""

from dataclasses import dataclass

from job_radar.compensation import CompensationResult
from job_radar.eligibility import EligibilityResult
from job_radar.models import JobPosting
from job_radar.llm_advisory import LlmFitReview
from job_radar.resume_match import ResumeMatchResult
from job_radar.score_evidence import ScoreEvidence
from job_radar.tracker.tracker_models import ApplicationRecord


@dataclass(frozen=True)
class ScoredPosting:
    posting: JobPosting
    score: int
    score_reasons: list[str]
    score_evidence: list[ScoreEvidence] | None = None
    location_status: str = "unknown"
    top_match_eligible: bool = False
    potential_top_match_eligible: bool = False
    location_outlier_eligible: bool = False
    top_match_reasons: list[str] | None = None
    review_needed_eligible: bool = False
    resume_match: ResumeMatchResult | None = None
    compensation: CompensationResult | None = None
    eligibility: EligibilityResult | None = None
    profile_avoid_matches: list[str] | None = None
    history_context: list[str] | None = None
    history_risk_level: str | None = None
    history_risk_reasons: list[str] | None = None
    application: ApplicationRecord | None = None
    llm_review: LlmFitReview | None = None
