"""Sort scored jobs into the report and email sections users actually see."""

from dataclasses import dataclass

from job_radar.recommendation_constants import (
    ACTION_HOLD,
    ACTION_PASS,
    ACTION_TRACK_STATUS,
)
from job_radar.recommendations import (
    _get_recommended_action,
    _is_actionable_posting,
    _is_top_match_display_posting,
)
from job_radar.scored_posting import ScoredPosting


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

    return scored_posting.review_needed_eligible


def is_email_top_match_posting(scored_posting: ScoredPosting) -> bool:
    if _get_recommended_action(scored_posting) == ACTION_TRACK_STATUS:
        return False

    return _is_top_match_display_posting(scored_posting)


def is_email_review_needed_posting(scored_posting: ScoredPosting) -> bool:
    if _get_recommended_action(scored_posting) in {
        ACTION_HOLD,
        ACTION_PASS,
        ACTION_TRACK_STATUS,
    }:
        return False

    return scored_posting.review_needed_eligible
