"""Sort scored jobs into the report and email sections users actually see."""

from dataclasses import dataclass

from job_radar.eligibility import ELIGIBILITY_NEEDS_REVIEW
from job_radar.recommendation_constants import (
    ACTION_HOLD,
    ACTION_PASS,
    ACTION_TRACK_STATUS,
)
from job_radar.recommendations import (
    _format_hiring_risk_flags,
    _format_resume_evidence,
    _format_resume_gaps,
    _get_action_rationale,
    _get_compensation_label,
    _get_compensation_range_label,
    _get_hiring_probability_label,
    _get_recommended_action,
    _get_resume_match_label,
    _get_technical_match_label,
    _is_actionable_posting,
    _is_top_match_display_posting,
)
from job_radar.scored_posting import ScoredPosting


@dataclass(frozen=True)
class JobOutputViewModel:
    """Prepare common job facts once for every report output format."""

    scored_posting: ScoredPosting
    title: str
    company: str
    location: str
    source_type: str
    source_url: str | None
    canonical_key: str
    job_radar_id: str
    salary_text: str | None
    score: int
    technical_match: str
    resume_match: str
    resume_evidence: str
    resume_gaps: str
    compensation: str
    compensation_range: str
    hiring_probability: str
    recommended_action: str
    action_rationale: str
    hiring_risks: str
    why_matched: str
    history_context: str
    history_risk: str
    eligibility_status: str | None
    eligibility_label: str
    eligibility_reasons: tuple[str, ...]
    eligibility_reason_text: str


def build_job_output_view_model(
    scored_posting: ScoredPosting,
) -> JobOutputViewModel:
    posting = scored_posting.posting
    history_context = "; ".join(scored_posting.history_context or []) or "None"
    history_risk = scored_posting.history_risk_level or "None"

    if scored_posting.history_risk_level and scored_posting.history_risk_reasons:
        history_risk = (
            f"{scored_posting.history_risk_level}: "
            f"{', '.join(scored_posting.history_risk_reasons)}"
        )

    eligibility_status = None
    eligibility_label = "Not evaluated"
    eligibility_reasons: tuple[str, ...] = ()
    eligibility_reason_text = "Not evaluated"

    if scored_posting.eligibility is not None:
        eligibility_status = scored_posting.eligibility.status
        eligibility_label = {
            "eligible": "Eligible",
            "needs_review": "Needs Review",
            "not_eligible": "Not Eligible",
        }.get(eligibility_status, eligibility_status)
        eligibility_reasons = tuple(
            reason.message
            for reason in scored_posting.eligibility.reasons
            if reason.message.strip()
        )
        eligibility_reason_text = (
            "; ".join(eligibility_reasons)
            if eligibility_reasons
            else "None recorded"
        )

    return JobOutputViewModel(
        scored_posting=scored_posting,
        title=posting.title or "Unknown",
        company=posting.company_name or "Unknown",
        location=posting.location or "Unknown",
        source_type=posting.source_type,
        source_url=posting.source_url,
        canonical_key=posting.canonical_key,
        job_radar_id=posting.job_radar_id,
        salary_text=posting.salary_text,
        score=scored_posting.score,
        technical_match=_get_technical_match_label(scored_posting),
        resume_match=_get_resume_match_label(scored_posting),
        resume_evidence=_format_resume_evidence(scored_posting),
        resume_gaps=_format_resume_gaps(scored_posting),
        compensation=_get_compensation_label(scored_posting),
        compensation_range=_get_compensation_range_label(scored_posting),
        hiring_probability=_get_hiring_probability_label(scored_posting),
        recommended_action=_get_recommended_action(scored_posting),
        action_rationale=_get_action_rationale(scored_posting),
        hiring_risks=_format_hiring_risk_flags(scored_posting),
        why_matched=_format_match_summary(scored_posting.score_reasons),
        history_context=history_context,
        history_risk=history_risk,
        eligibility_status=eligibility_status,
        eligibility_label=eligibility_label,
        eligibility_reasons=eligibility_reasons,
        eligibility_reason_text=eligibility_reason_text,
    )


def _format_match_summary(score_reasons: list[str]) -> str:
    if not score_reasons:
        return "No scoring reasons recorded"

    labels: list[str] = []

    for reason in score_reasons:
        if reason.startswith("-") or ":" not in reason:
            continue

        keyword = reason.split(":", maxsplit=1)[1].strip()

        if keyword and keyword not in labels:
            labels.append(keyword)

    return ", ".join(labels) if labels else "No positive match reasons"


@dataclass(frozen=True)
class ReportViewModel:
    report_scored_postings: list[ScoredPosting]
    top_matches: list[ScoredPosting]
    review_needed: list[ScoredPosting]
    tracked_applications: list[ScoredPosting]
    email_scored_postings: list[ScoredPosting]
    email_top_matches: list[ScoredPosting]
    email_review_needed: list[ScoredPosting]


def build_report_view_model(
    scored_postings: list[ScoredPosting] | None,
    omitted_scored_postings: list[ScoredPosting] | None = None,
    email_postings_limit: int = 10,
) -> ReportViewModel:
    primary_postings = list(scored_postings or [])
    report_scored_postings = list(primary_postings)
    report_scored_postings.extend(omitted_scored_postings or [])

    top_matches = [
        scored_posting
        for scored_posting in report_scored_postings
        if is_top_match_report_posting(scored_posting)
    ]
    review_needed = [
        scored_posting
        for scored_posting in report_scored_postings
        if is_review_needed_report_posting(scored_posting)
    ]
    tracked_applications = [
        scored_posting
        for scored_posting in report_scored_postings
        if _get_recommended_action(scored_posting) == ACTION_TRACK_STATUS
    ]

    email_scored_postings = [
        scored_posting
        for scored_posting in report_scored_postings
        if _get_recommended_action(scored_posting) != ACTION_TRACK_STATUS
    ]
    email_top_matches = [
        scored_posting
        for scored_posting in email_scored_postings
        if is_email_top_match_posting(scored_posting)
    ][:email_postings_limit]
    email_review_needed = [
        scored_posting
        for scored_posting in email_scored_postings
        if is_email_review_needed_posting(scored_posting)
    ][:email_postings_limit]

    return ReportViewModel(
        report_scored_postings=report_scored_postings,
        top_matches=top_matches,
        review_needed=review_needed,
        tracked_applications=tracked_applications,
        email_scored_postings=email_scored_postings,
        email_top_matches=email_top_matches,
        email_review_needed=email_review_needed,
    )


def is_top_match_report_posting(scored_posting: ScoredPosting) -> bool:
    if _get_recommended_action(scored_posting) == ACTION_TRACK_STATUS:
        return False

    return _is_top_match_display_posting(scored_posting)


def is_review_needed_report_posting(scored_posting: ScoredPosting) -> bool:
    if not _is_actionable_posting(scored_posting):
        return False

    if _get_recommended_action(scored_posting) == ACTION_TRACK_STATUS:
        return False

    if _is_top_match_display_posting(scored_posting):
        return False

    eligibility_needs_review = (
        scored_posting.eligibility is not None
        and scored_posting.eligibility.status == ELIGIBILITY_NEEDS_REVIEW
    )

    # Practical unknowns belong in Review Needed even when the legacy keyword
    # score is weak. Calling the job "not recommended" while its own action says
    # "Needs review" hides exactly the uncertainty the user must resolve.
    return scored_posting.review_needed_eligible or eligibility_needs_review


def is_email_top_match_posting(scored_posting: ScoredPosting) -> bool:
    if _get_recommended_action(scored_posting) == ACTION_TRACK_STATUS:
        return False

    return _is_top_match_display_posting(scored_posting)


def is_email_review_needed_posting(scored_posting: ScoredPosting) -> bool:
    recommended_action = _get_recommended_action(scored_posting)
    eligibility_needs_review = (
        scored_posting.eligibility is not None
        and scored_posting.eligibility.status == ELIGIBILITY_NEEDS_REVIEW
    )

    if recommended_action in {
        ACTION_PASS,
        ACTION_TRACK_STATUS,
    }:
        return False

    if _is_top_match_display_posting(scored_posting):
        return False

    if (
        recommended_action == ACTION_HOLD
        and not scored_posting.review_needed_eligible
        and not eligibility_needs_review
    ):
        return False

    return scored_posting.review_needed_eligible or eligibility_needs_review
