from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path

from job_radar.compensation import CompensationResult
from job_radar.models import JobPosting
from job_radar.resume_match import ResumeMatchResult
from job_radar.tracker.tracker_models import ApplicationRecord
from job_radar.tracker.tracker_service import get_application_workflow_state
from job_radar.recommendation_constants import (
    ACTION_HOLD,
    ACTION_PASS,
    ACTION_PREVIOUSLY_REVIEWED,
    ACTION_TRACK_STATUS,
    RISK_BELOW_COMPENSATION_FLOOR,
    RISK_GENERIC_REMOTE_COMPETITION,
    RISK_HARD_LOCATION_MISMATCH,
    RISK_HIGH_COMPETITION_EMPLOYER,
    RISK_LOCATION_NEEDS_CONFIRMATION,
    RISK_NOT_LOCATION_ELIGIBLE,
    RISK_PRODUCTION_KUBERNETES_TRANSLATION,
    RISK_ROLE_FAMILY_MISMATCH,
    RISK_SECURITY_DOMAIN_TRANSLATION,
    RISK_SOFTWARE_HEAVY_TRANSLATION,
    RISK_SUPPORT_ROLE,
    TRACK_STATUS_ALREADY_APPLIED_MESSAGE,
)
from job_radar.recommendations import (
    _RECOMMENDATION_SUMMARY_ORDER,
    _format_hiring_risk_flags,
    _format_resume_evidence,
    _format_resume_gaps,
    _get_action_rationale,
    _get_compensation_label,
    _get_compensation_range_label,
    _get_hiring_probability_label,
    _get_hiring_risk_flags,
    _get_recommendation_summary_counts,
    _get_recommended_action,
    _get_resume_match_label,
    _get_technical_match_label,
    _is_actionable_posting,
    _is_top_match_display_posting,
)


TOP_MATCHES_QUICK_VIEW_LIMIT = 10
NORTHERN_COLORADO_HIGHLIGHTS_LIMIT = 10
PASSED_JOBS_REPORT_LIMIT = 25
NORTHERN_COLORADO_LOCATION_KEYWORDS = (
    "fort collins",
    "loveland",
    "greeley",
    "windsor",
    "berthoud",
    "longmont",
    "northern colorado",
    "cheyenne",
)

TRACKER_WORKFLOW_SUMMARY_ORDER = (
    "follow_up_due",
    "needs_date_review",
    "active_pipeline",
    "follow_up_scheduled",
    "waiting",
    "dormant",
    "stale",
    "presumed_closed",
    "closed",
)

TRACKER_NEEDS_ACTION_WORKFLOW_STATES = (
    "follow_up_due",
    "needs_date_review",
    "active_pipeline",
)

TRACKER_NEEDS_REVIEW_WORKFLOW_STATES = (
    "needs_date_review",
    "dormant",
    "stale",
    "presumed_closed",
)


@dataclass(frozen=True)
class ScoredPosting:
    posting: JobPosting
    score: int
    score_reasons: list[str]
    location_status: str = "unknown"
    top_match_eligible: bool = False
    top_match_reasons: list[str] | None = None
    review_needed_eligible: bool = False
    resume_match: ResumeMatchResult | None = None
    compensation: CompensationResult | None = None
    profile_avoid_matches: list[str] | None = None
    history_context: list[str] | None = None
    history_risk_level: str | None = None
    history_risk_reasons: list[str] | None = None
    application: ApplicationRecord | None = None


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
    omitted_scored_postings: list[ScoredPosting] | None = None
    generated_at: str | None = None
    top_match_min_score: int | None = None
    review_needed_min_score: int | None = None
    jobs_stored: int | None = None
    jobs_omitted: int | None = None
    history_context: list[str] | None = None
    tracker_workflow_summary: dict[str, int] | None = None


def render_markdown_report(report: ScanReport) -> str:
    lines: list[str] = [
        "# Job Radar Report",
        "",
        "## Summary",
        "",
    ]

    if report.generated_at is not None:
        lines.append(f"- Generated at: {_format_generated_at(report.generated_at)}")

    lines.extend(
        [
            f"- Companies enabled: {report.companies_enabled}",
            f"- Jobs collected: {report.jobs_collected}",
            f"- New jobs: {report.jobs_new}",
            f"- Seen jobs: {report.jobs_seen}",
            f"- Changed jobs: {report.jobs_changed}",
            f"- Collector errors: {len(report.collector_errors)}",
        ]
    )

    if report.jobs_stored is not None:
        lines.append(f"- Actionable jobs stored: {report.jobs_stored}")

    if report.jobs_omitted is not None:
        lines.append(f"- Jobs not actionable: {report.jobs_omitted}")

    if report.top_match_min_score is not None:
        lines.append(f"- Top match score threshold: {report.top_match_min_score}")

    if report.review_needed_min_score is not None:
        lines.append(
            f"- Review-needed score threshold: {report.review_needed_min_score}"
        )

    _append_companies_scanned_summary(lines, report.postings)
    _append_source_type_summary(lines, report.postings)
    _append_tracker_action_summary(lines, report.tracker_workflow_summary)
    _append_tracker_workflow_summary(lines, report.tracker_workflow_summary)

    if report.scored_postings is not None:
        report_scored_postings = _get_report_scored_postings(report)
        surfaced_scored_postings = _get_surfaced_recommendation_postings(report)
        _append_work_arrangement_summary(lines, report.scored_postings)
        _append_recommendation_summary(lines, surfaced_scored_postings)
        _append_history_risk_summary(lines, report_scored_postings)
        _append_omitted_jobs_audit_summary(lines, report_scored_postings)

    _append_history_context_summary(lines, report.history_context)

    lines.append("")

    if report.collector_errors:
        _append_collector_errors(lines, report.collector_errors)

    if report.scored_postings is not None:
        _append_scored_sections(
            lines,
            scored_postings=report.scored_postings,
            omitted_scored_postings=report.omitted_scored_postings,
        )
    else:
        _append_unscored_jobs_section(lines, report.postings)

    return "\n".join(lines).rstrip() + "\n"


def write_markdown_report(report_path: str | Path, report: ScanReport) -> Path:
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown_report(report), encoding="utf-8")
    return path


def render_html_report(report: ScanReport) -> str:
    lines: list[str] = [
        "<!doctype html>",
        "<html>",
        "<head>",
        '<meta charset="utf-8">',
        "<title>Job Radar Report</title>",
        "<style>",
        "body { font-family: Arial, sans-serif; line-height: 1.4; margin: 24px; }",
        "h1 { margin-bottom: 8px; }",
        "h2 { border-bottom: 1px solid #cccccc; padding-bottom: 4px; margin-top: 28px; }",
        "h3 { margin-bottom: 8px; }",
        "a { color: #0b66c3; }",
        ".summary { background: #f6f8fa; border: 1px solid #dddddd; padding: 12px 16px; }",
        ".job-card { border: 1px solid #dddddd; padding: 14px 16px; margin: 16px 0; border-radius: 6px; }",
        ".top-match { border-left: 6px solid #2e7d32; }",
        ".review-needed { border-left: 6px solid #b26a00; }",
        ".quick-view { background: #f6f8fa; border: 1px solid #dddddd; padding: 10px 14px; }",
        "code { background: #f6f8fa; padding: 2px 4px; }",
        "</style>",
        "</head>",
        "<body>",
        "<h1>Job Radar Report</h1>",
        "<h2>Summary</h2>",
        '<ul class="summary">',
    ]

    if report.generated_at is not None:
        lines.append(
            f"<li><strong>Generated at:</strong> "
            f"{escape(_format_generated_at(report.generated_at))}</li>"
        )

    lines.extend(
        [
            f"<li><strong>Companies enabled:</strong> {report.companies_enabled}</li>",
            f"<li><strong>Jobs collected:</strong> {report.jobs_collected}</li>",
            f"<li><strong>New jobs:</strong> {report.jobs_new}</li>",
            f"<li><strong>Seen jobs:</strong> {report.jobs_seen}</li>",
            f"<li><strong>Changed jobs:</strong> {report.jobs_changed}</li>",
            f"<li><strong>Collector errors:</strong> "
            f"{len(report.collector_errors)}</li>",
        ]
    )

    if report.jobs_stored is not None:
        lines.append(
            f"<li><strong>Actionable jobs stored:</strong> "
            f"{report.jobs_stored}</li>"
        )

    if report.jobs_omitted is not None:
        lines.append(
            f"<li><strong>Jobs not actionable:</strong> "
            f"{report.jobs_omitted}</li>"
        )

    if report.top_match_min_score is not None:
        lines.append(
            f"<li><strong>Top match score threshold:</strong> "
            f"{report.top_match_min_score}</li>"
        )

    if report.review_needed_min_score is not None:
        lines.append(
            f"<li><strong>Review-needed score threshold:</strong> "
            f"{report.review_needed_min_score}</li>"
        )

    _append_html_count_summary(
        lines=lines,
        heading="Companies scanned",
        counts=_count_companies(report.postings),
    )
    _append_html_count_summary(
        lines=lines,
        heading="Source types",
        counts=_count_source_types(report.postings),
    )
    _append_html_tracker_action_summary(lines, report.tracker_workflow_summary)
    _append_html_tracker_workflow_summary(lines, report.tracker_workflow_summary)

    if report.scored_postings is not None:
        report_scored_postings = _get_report_scored_postings(report)
        surfaced_scored_postings = _get_surfaced_recommendation_postings(report)
        _append_html_work_arrangement_summary(lines, report.scored_postings)
        _append_html_count_summary(
            lines=lines,
            heading="Recommendation summary",
            counts=_get_recommendation_summary_counts(surfaced_scored_postings),
        )
        _append_html_count_summary(
            lines=lines,
            heading="History risk summary",
            counts=_get_history_risk_summary_counts(report_scored_postings),
        )
        _append_html_omitted_jobs_audit_summary(lines, report_scored_postings)
    _append_html_history_context_summary(lines, report.history_context)

    lines.append("</ul>")

    if report.collector_errors:
        _append_html_collector_errors(lines, report.collector_errors)

    if report.scored_postings is not None:
        _append_html_scored_sections(
            lines,
            scored_postings=report.scored_postings,
            omitted_scored_postings=report.omitted_scored_postings,
        )
    else:
        _append_html_unscored_jobs_section(lines, report.postings)

    lines.extend(
        [
            "</body>",
            "</html>",
        ]
    )

    return "\n".join(lines) + "\n"


def write_html_report(report_path: str | Path, report: ScanReport) -> Path:
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html_report(report), encoding="utf-8")
    return path


def _count_companies(postings: list[JobPosting]) -> dict[str, int]:
    company_counts: dict[str, int] = {}

    for posting in postings:
        company_name = posting.company_name or "Unknown"
        company_counts[company_name] = company_counts.get(company_name, 0) + 1

    return company_counts


def _count_source_types(postings: list[JobPosting]) -> dict[str, int]:
    source_type_counts: dict[str, int] = {}

    for posting in postings:
        source_type = posting.source_type or "unknown"
        source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1

    return source_type_counts


def _append_companies_scanned_summary(
    lines: list[str],
    postings: list[JobPosting],
) -> None:
    company_counts = _count_companies(postings)

    if not company_counts:
        return

    lines.append("- Companies scanned:")

    for company_name in sorted(company_counts):
        lines.append(f"  - {company_name}: {company_counts[company_name]}")


def _append_source_type_summary(
    lines: list[str],
    postings: list[JobPosting],
) -> None:
    source_type_counts = _count_source_types(postings)

    if not source_type_counts:
        return

    lines.append("- Source types:")

    for source_type in sorted(source_type_counts):
        lines.append(f"  - {source_type}: {source_type_counts[source_type]}")


def _append_tracker_action_summary(
    lines: list[str],
    tracker_workflow_summary: dict[str, int] | None,
) -> None:
    if not tracker_workflow_summary:
        return

    needs_action_count = _sum_tracker_workflow_states(
        tracker_workflow_summary,
        TRACKER_NEEDS_ACTION_WORKFLOW_STATES,
    )
    needs_review_count = _sum_tracker_workflow_states(
        tracker_workflow_summary,
        TRACKER_NEEDS_REVIEW_WORKFLOW_STATES,
    )

    if needs_action_count == 0 and needs_review_count == 0:
        return

    lines.append("- Tracker action summary:")
    lines.append(f"  - Needs action: {needs_action_count}")
    lines.append(f"  - Needs review: {needs_review_count}")


def _sum_tracker_workflow_states(
    tracker_workflow_summary: dict[str, int],
    workflow_states: tuple[str, ...],
) -> int:
    return sum(
        tracker_workflow_summary.get(workflow_state, 0)
        for workflow_state in workflow_states
    )


def _append_tracker_workflow_summary(
    lines: list[str],
    tracker_workflow_summary: dict[str, int] | None,
) -> None:
    if not tracker_workflow_summary:
        return

    lines.append("- Tracker workflow summary:")

    for workflow_state in _get_ordered_tracker_workflow_states(
        tracker_workflow_summary
    ):
        lines.append(f"  - {workflow_state}: {tracker_workflow_summary[workflow_state]}")


def _append_work_arrangement_summary(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    if not scored_postings:
        return

    work_arrangement_counts = _get_work_arrangement_summary_counts(scored_postings)

    if not work_arrangement_counts:
        return

    lines.append("- Work location fit:")

    for work_arrangement in _get_ordered_work_arrangements(work_arrangement_counts):
        lines.append(
            f"  - {_format_work_arrangement_summary_label(work_arrangement)}: "
            f"{work_arrangement_counts[work_arrangement]}"
        )


def _get_work_arrangement_summary_counts(
    scored_postings: list[ScoredPosting],
) -> dict[str, int]:
    work_arrangement_counts: dict[str, int] = {}

    for scored_posting in scored_postings:
        work_arrangement = _format_work_arrangement(scored_posting)
        work_arrangement_counts[work_arrangement] = (
            work_arrangement_counts.get(work_arrangement, 0) + 1
        )

    return work_arrangement_counts


def _format_work_arrangement_summary_label(work_arrangement: str) -> str:
    if work_arrangement == "remote":
        return "Remote-friendly"

    if work_arrangement == "hybrid":
        return "Hybrid"

    if work_arrangement == "onsite":
        return "Onsite"

    if work_arrangement == "needs confirmation":
        return "Needs location confirmation"

    if work_arrangement == RISK_NOT_LOCATION_ELIGIBLE:
        return "Not location eligible"

    if work_arrangement == "unknown":
        return "Unknown location fit"

    return work_arrangement


def _get_ordered_work_arrangements(
    work_arrangement_counts: dict[str, int],
) -> list[str]:
    preferred_order = [
        "remote",
        "hybrid",
        "onsite",
        "needs confirmation",
        RISK_NOT_LOCATION_ELIGIBLE,
        "unknown",
    ]

    ordered_arrangements = [
        work_arrangement
        for work_arrangement in preferred_order
        if work_arrangement in work_arrangement_counts
    ]

    for work_arrangement in sorted(work_arrangement_counts):
        if work_arrangement not in ordered_arrangements:
            ordered_arrangements.append(work_arrangement)

    return ordered_arrangements


def _get_ordered_tracker_workflow_states(
    tracker_workflow_summary: dict[str, int],
) -> list[str]:
    ordered_workflow_states = [
        workflow_state
        for workflow_state in TRACKER_WORKFLOW_SUMMARY_ORDER
        if workflow_state in tracker_workflow_summary
    ]

    for workflow_state in sorted(tracker_workflow_summary):
        if workflow_state not in ordered_workflow_states:
            ordered_workflow_states.append(workflow_state)

    return ordered_workflow_states


def _get_report_scored_postings(report: ScanReport) -> list[ScoredPosting]:
    report_scored_postings = list(report.scored_postings or [])
    report_scored_postings.extend(report.omitted_scored_postings or [])

    return report_scored_postings


def _get_surfaced_recommendation_postings(report: ScanReport) -> list[ScoredPosting]:
    scored_postings = list(report.scored_postings or [])
    report_scored_postings = _get_report_scored_postings(report)
    surfaced_postings: list[ScoredPosting] = []

    surfaced_postings.extend(_get_top_matches(scored_postings))
    surfaced_postings.extend(_get_northern_colorado_highlights(scored_postings))
    surfaced_postings.extend(_get_review_needed(report_scored_postings))
    surfaced_postings.extend(
        scored_posting
        for scored_posting in report_scored_postings
        if _get_recommended_action(scored_posting) == ACTION_TRACK_STATUS
    )

    return _dedupe_scored_postings(surfaced_postings)


def _dedupe_scored_postings(
    scored_postings: list[ScoredPosting],
) -> list[ScoredPosting]:
    seen_keys: set[str] = set()
    deduped_postings: list[ScoredPosting] = []

    for scored_posting in scored_postings:
        posting = scored_posting.posting
        dedupe_key = (
            posting.source_url
            or posting.canonical_key
            or f"{posting.company_key}:{posting.title}:{posting.location}"
        )

        if dedupe_key in seen_keys:
            continue

        seen_keys.add(dedupe_key)
        deduped_postings.append(scored_posting)

    return deduped_postings


def _append_recommendation_summary(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    recommendation_counts = _get_recommendation_summary_counts(scored_postings)

    if not recommendation_counts:
        return

    lines.append("- Recommendation summary:")

    for recommendation in _RECOMMENDATION_SUMMARY_ORDER:
        lines.append(f"  - {recommendation}: {recommendation_counts[recommendation]}")


def _append_history_risk_summary(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    history_risk_counts = _get_history_risk_summary_counts(scored_postings)

    if not history_risk_counts:
        return

    lines.append("- History risk summary:")

    for risk_level in _get_ordered_history_risk_levels(history_risk_counts):
        lines.append(f"  - {risk_level}: {history_risk_counts[risk_level]}")


def _append_omitted_jobs_audit_summary(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    omitted_postings = _get_omitted_postings(scored_postings)

    if not omitted_postings:
        return

    omitted_reason_counts = _get_omitted_reason_summary_counts(omitted_postings)

    if not omitted_reason_counts:
        return

    # Keep the high-level audit near the scan summary so the report explains
    # why thousands of collected jobs did not surface before the reader scrolls.
    lines.append("- Omitted jobs audit:")
    lines.append("  - One job may appear in more than one signal count.")

    for reason in sorted(omitted_reason_counts):
        lines.append(f"  - {reason}: {omitted_reason_counts[reason]}")


def _get_history_risk_summary_counts(
    scored_postings: list[ScoredPosting],
) -> dict[str, int]:
    history_risk_counts: dict[str, int] = {}

    for scored_posting in scored_postings:
        risk_level = scored_posting.history_risk_level

        if not risk_level:
            continue

        history_risk_counts[risk_level] = history_risk_counts.get(risk_level, 0) + 1

    return history_risk_counts


def _get_ordered_history_risk_levels(
    history_risk_counts: dict[str, int],
) -> list[str]:
    preferred_order = [
        "track_status",
        "blocker_review",
        "caution",
        "neutral",
    ]

    ordered_levels = [
        risk_level
        for risk_level in preferred_order
        if risk_level in history_risk_counts
    ]

    for risk_level in sorted(history_risk_counts):
        if risk_level not in ordered_levels:
            ordered_levels.append(risk_level)

    return ordered_levels


def _append_history_context_summary(
    lines: list[str],
    history_context: list[str] | None,
) -> None:
    if not history_context:
        return

    lines.append("- Job history context:")

    for context_item in history_context:
        lines.append(f"  - {context_item}")


def _append_collector_errors(
    lines: list[str],
    collector_errors: list[ScanError],
) -> None:
    lines.extend(
        [
            "## Collector Errors",
            "",
        ]
    )

    for error in collector_errors:
        lines.append(
            "- "
            f"{error.company_key} "
            f"({error.company_name}, {error.source_type}): "
            f"{error.message}"
        )

    lines.append("")


def _append_scored_sections(
    lines: list[str],
    scored_postings: list[ScoredPosting],
    omitted_scored_postings: list[ScoredPosting] | None = None,
) -> None:
    report_scored_postings = list(scored_postings)

    if omitted_scored_postings is not None:
        report_scored_postings.extend(omitted_scored_postings)

    _append_top_matches_section(lines, report_scored_postings)
    _append_northern_colorado_highlights_section(lines, report_scored_postings)
    _append_review_needed_section(lines, report_scored_postings)
    _append_omitted_jobs_section(
        lines,
        scored_postings=(
            omitted_scored_postings
            if omitted_scored_postings is not None
            else scored_postings
        ),
    )


def _append_top_matches_section(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    lines.extend(
        [
            "## Top Matches",
            "",
        ]
    )

    top_matches = _get_top_matches(scored_postings)

    if not top_matches:
        lines.extend(
            [
                "No top matches found.",
                "",
            ]
        )
        return

    _append_top_matches_quick_view(
        lines,
        top_matches[:TOP_MATCHES_QUICK_VIEW_LIMIT],
    )

    for scored_posting in top_matches:
        _append_scored_posting(lines, scored_posting)


def _append_northern_colorado_highlights_section(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    lines.extend(
        [
            "## Northern Colorado Highlights",
            "",
        ]
    )

    highlights = _get_northern_colorado_highlights(scored_postings)

    if not highlights:
        lines.extend(
            [
                "No Northern Colorado highlights found.",
                "",
            ]
        )
        return

    for scored_posting in highlights:
        _append_scored_posting(lines, scored_posting)


def _append_review_needed_section(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    lines.extend(
        [
            "## Review Needed",
            "",
        ]
    )

    review_needed = _get_review_needed(scored_postings)

    if not review_needed:
        lines.extend(
            [
                "No review-needed jobs found.",
                "",
            ]
        )
        return

    for scored_posting in review_needed:
        _append_scored_posting(lines, scored_posting)


def _is_top_match_report_posting(scored_posting: ScoredPosting) -> bool:
    return _is_top_match_display_posting(scored_posting)


def _is_review_needed_report_posting(scored_posting: ScoredPosting) -> bool:
    if not _is_actionable_posting(scored_posting):
        return False

    if _get_recommended_action(scored_posting) == ACTION_TRACK_STATUS:
        return True

    return scored_posting.review_needed_eligible


def _get_review_needed(
    scored_postings: list[ScoredPosting],
) -> list[ScoredPosting]:
    return [
        scored_posting
        for scored_posting in scored_postings
        if _is_review_needed_report_posting(scored_posting)
    ]


def _append_omitted_jobs_section(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    omitted_postings = _get_omitted_postings(scored_postings)
    ordered_omitted_postings = _get_ordered_omitted_postings(omitted_postings)

    lines.extend(
        [
            "## Passed / Not Recommended",
            "",
        ]
    )

    if not omitted_postings:
        lines.extend(
            [
                "No passed jobs to show.",
                "",
            ]
        )
        return

    lines.extend(
        [
            (
                f"{len(omitted_postings)} scored jobs were not recommended for "
                "apply/review based on fit, location, compensation, or hiring-risk "
                "signals."
            ),
            "",
        ]
    )

    omitted_reason_counts = _get_omitted_reason_summary_counts(omitted_postings)

    if omitted_reason_counts:
        lines.extend(
            [
                "- Risk / pass signal summary:",
                "  - One job may appear in more than one signal count.",
            ]
        )

        for reason in sorted(omitted_reason_counts):
            lines.append(f"  - {reason}: {omitted_reason_counts[reason]}")

        lines.append("")

    lines.extend(
        [
            f"### Passed jobs most worth reviewing, up to {PASSED_JOBS_REPORT_LIMIT}",
            "",
        ]
    )

    for scored_posting in ordered_omitted_postings[:PASSED_JOBS_REPORT_LIMIT]:
        _append_passed_posting(lines, scored_posting)

    if len(omitted_postings) > PASSED_JOBS_REPORT_LIMIT:
        lines.extend(
            [
                (
                    f"{len(omitted_postings) - PASSED_JOBS_REPORT_LIMIT} additional "
                    "passed jobs were hidden from this report to keep the file readable."
                ),
                "",
            ]
        )


def _get_omitted_postings(
    scored_postings: list[ScoredPosting],
) -> list[ScoredPosting]:
    return [
        scored_posting
        for scored_posting in scored_postings
        if not _is_top_match_report_posting(scored_posting)
        and not _is_review_needed_report_posting(scored_posting)
    ]


def _get_ordered_omitted_postings(
    scored_postings: list[ScoredPosting],
) -> list[ScoredPosting]:
    return sorted(
        scored_postings,
        key=_get_omitted_posting_review_priority,
        reverse=True,
    )


def _get_omitted_posting_review_priority(scored_posting: ScoredPosting) -> tuple[int, int]:
    return (
        _get_omitted_posting_review_score(scored_posting),
        scored_posting.score,
    )


def _get_omitted_posting_review_score(scored_posting: ScoredPosting) -> int:
    risks = _get_hiring_risk_flags(scored_posting)
    technical_match = _get_technical_match_label(scored_posting)
    recommended_action = _get_recommended_action(scored_posting)

    review_score = scored_posting.score

    if technical_match == "Very Strong":
        review_score += 50
    elif technical_match == "Strong":
        review_score += 35
    elif technical_match == "Moderate":
        review_score += 15

    if recommended_action != ACTION_PASS:
        review_score += 25

    if RISK_BELOW_COMPENSATION_FLOOR in risks:
        review_score += 15

    if RISK_HARD_LOCATION_MISMATCH in risks or RISK_NOT_LOCATION_ELIGIBLE in risks:
        review_score += 10

    if RISK_LOCATION_NEEDS_CONFIRMATION in risks:
        review_score += 5

    if RISK_ROLE_FAMILY_MISMATCH in risks:
        review_score -= 100

    if RISK_SUPPORT_ROLE in risks:
        review_score -= 80

    if any(risk.startswith("profile avoid match:") for risk in risks):
        review_score -= 80

    if RISK_SOFTWARE_HEAVY_TRANSLATION in risks:
        review_score -= 20

    if RISK_SECURITY_DOMAIN_TRANSLATION in risks:
        review_score -= 20

    return review_score


def _format_pass_reason(scored_posting: ScoredPosting) -> str:
    recommended_action = _get_recommended_action(scored_posting)
    risks = _get_hiring_risk_flags(scored_posting)

    if recommended_action == ACTION_TRACK_STATUS:
        return TRACK_STATUS_ALREADY_APPLIED_MESSAGE

    if recommended_action == ACTION_PASS:
        if RISK_BELOW_COMPENSATION_FLOOR in risks:
            return "Compensation appears below your current floor."

        if RISK_ROLE_FAMILY_MISMATCH in risks:
            return "Role family does not match your target infrastructure/SRE profile."

        if RISK_NOT_LOCATION_ELIGIBLE in risks:
            return "Location does not fit your remote/Northern Colorado preferences."

        if RISK_SOFTWARE_HEAVY_TRANSLATION in risks:
            return "Role appears too software-heavy for the current target profile."

        if RISK_SECURITY_DOMAIN_TRANSLATION in risks:
            return "Role leans too far into security-domain work."

        if risks:
            return "Risk flags make this a poor apply target."

        return "Score and match signals are too weak for this scan."

    if recommended_action == ACTION_PREVIOUSLY_REVIEWED:
        return "Already reviewed in prior history; revisit only if something changed."

    if recommended_action == ACTION_HOLD:
        return "Not strong enough to act on now."

    if (
        not scored_posting.top_match_eligible
        and not scored_posting.review_needed_eligible
    ):
        return "Did not meet the Top Match or Review Needed thresholds."

    return "Not actionable enough for the detailed apply/review sections."


def _format_pass_summary_reason(risk: str) -> str:
    if risk == RISK_BELOW_COMPENSATION_FLOOR:
        return "Below compensation floor"

    if risk == RISK_ROLE_FAMILY_MISMATCH:
        return "Role family mismatch"

    if risk == RISK_NOT_LOCATION_ELIGIBLE:
        return "Not location eligible"

    if risk == RISK_SOFTWARE_HEAVY_TRANSLATION:
        return "Software-heavy mismatch"

    if risk == RISK_SECURITY_DOMAIN_TRANSLATION:
        return "Security-domain mismatch"

    if risk == RISK_PRODUCTION_KUBERNETES_TRANSLATION:
        return "Kubernetes translation risk"

    if risk == RISK_HIGH_COMPETITION_EMPLOYER:
        return "High-competition employer"

    if risk == RISK_GENERIC_REMOTE_COMPETITION:
        return "Generic remote competition"

    return risk


def _get_omitted_reason_summary_counts(
    scored_postings: list[ScoredPosting],
) -> dict[str, int]:
    omitted_reason_counts: dict[str, int] = {}

    for scored_posting in scored_postings:
        recommended_action = _get_recommended_action(scored_posting)

        if recommended_action == ACTION_PASS:
            risks = _get_hiring_risk_flags(scored_posting)

            if risks:
                for risk in risks:
                    reason = _format_pass_summary_reason(risk)
                    omitted_reason_counts[reason] = (
                        omitted_reason_counts.get(reason, 0) + 1
                    )
                continue

            reason = "Weak fit"

        elif recommended_action == ACTION_HOLD:
            reason = "Low hiring probability"

        elif (
            not scored_posting.top_match_eligible
            and not scored_posting.review_needed_eligible
        ):
            reason = "Below Top Match / Review Needed threshold"

        else:
            reason = f"Not actionable: {recommended_action}"

        omitted_reason_counts[reason] = omitted_reason_counts.get(reason, 0) + 1

    return omitted_reason_counts


def _append_passed_posting(
    lines: list[str],
    scored_posting: ScoredPosting,
) -> None:
    posting = scored_posting.posting

    lines.extend(
        [
            f"#### [{posting.title}]({posting.source_url})",
            "",
            f"- Company: {posting.company_name}",
            f"- Score: {scored_posting.score}",
            f"- Location: {posting.location or 'Unknown'}",
            f"- Recommended action: {_get_recommended_action(scored_posting)}",
            f"- Why not recommended: {_format_pass_reason(scored_posting)}",
            f"- Hiring risks: {_format_hiring_risk_flags(scored_posting)}",
            f"- URL: {posting.source_url}",
            f"- Job Radar ID: `{posting.job_radar_id}`",
            "",
        ]
    )


def _append_unscored_jobs_section(
    lines: list[str],
    postings: list[JobPosting],
) -> None:
    lines.extend(
        [
            "## Jobs",
            "",
        ]
    )

    if not postings:
        lines.extend(
            [
                "No jobs were collected during this scan.",
                "",
            ]
        )
        return

    for posting in postings:
        _append_posting(lines, posting)


def _append_top_matches_quick_view(
    lines: list[str],
    top_matches: list[ScoredPosting],
) -> None:
    lines.extend(
        [
            "### Quick View",
            "",
        ]
    )

    for scored_posting in top_matches:
        posting = scored_posting.posting
        location = posting.location or "Unknown"

        lines.extend(
            [
                f"- **{scored_posting.score}** - "
                f"[{posting.title}]({posting.source_url})",
                f"  - Company: {posting.company_name}",
                f"  - Location: {location}",
                f"  - Work location fit: {_format_work_arrangement(scored_posting)}",
            ]
        )

    lines.append("")


def _append_scored_posting(
    lines: list[str],
    scored_posting: ScoredPosting,
) -> None:
    posting = scored_posting.posting
    decision_explanation = _format_markdown_decision_explanation(scored_posting)

    lines.extend(
        [
            f"### [{posting.title}]({posting.source_url})",
            "",
            f"- Score: {scored_posting.score}",
        ]
    )

    if decision_explanation is not None:
        label, explanation = decision_explanation
        lines.append(f"- {label}: {explanation}")

    lines.extend(
        [
            f"- Why this matched: "
            f"{_format_match_summary(scored_posting.score_reasons)}",
            f"- Technical match: {_get_technical_match_label(scored_posting)}",
            f"- Resume match: {_get_resume_match_label(scored_posting)}",
            f"- Resume evidence: {_format_resume_evidence(scored_posting)}",
            f"- Resume gaps: {_format_resume_gaps(scored_posting)}",
            f"- Compensation: {_get_compensation_label(scored_posting)}",
            f"- Compensation range: {_get_compensation_range_label(scored_posting)}",
            f"- Hiring probability: {_get_hiring_probability_label(scored_posting)}",
            f"- Recommended action: {_get_recommended_action(scored_posting)}",
            f"- Action rationale: {_get_action_rationale(scored_posting)}",
            f"- Hiring risks: {_format_hiring_risk_flags(scored_posting)}",
            f"- History context: {_format_history_context(scored_posting)}",
        ]
    )

    history_risk = _format_history_risk(scored_posting)

    if history_risk != "None":
        lines.append(f"- History risk: {history_risk}")

    _append_markdown_track_status(lines, scored_posting.application)

    lines.extend(
        [
            f"- Work location fit: {_format_work_arrangement(scored_posting)}",
            f"- Company: {posting.company_name}",
            f"- Source: {posting.source_type}",
            f"- Location: {posting.location or 'Unknown'}",
            f"- URL: {posting.source_url}",
            f"- Job Radar ID: `{posting.job_radar_id}`",
        ]
    )

    if posting.salary_text:
        lines.append(f"- Salary: {posting.salary_text}")

    lines.extend(
        [
            f"- Canonical key: `{posting.canonical_key}`",
            "",
        ]
    )


def _append_markdown_track_status(
    lines: list[str],
    application: ApplicationRecord | None,
) -> None:
    if application is None:
        return

    workflow_state = get_application_workflow_state(application)

    lines.append("- Track Status:")
    lines.append(f"  - Status: {application.status}")
    lines.append(f"  - Workflow: {workflow_state}")

    if application.follow_up_on:
        lines.append(f"  - Follow up on: {application.follow_up_on}")

    if application.outcome:
        lines.append(f"  - Outcome: {application.outcome}")

    if application.notes:
        lines.append(f"  - Notes: {application.notes}")


def _append_posting(lines: list[str], posting: JobPosting) -> None:
    lines.extend(
        [
            f"### [{posting.title}]({posting.source_url})",
            "",
            f"- Company: {posting.company_name}",
            f"- Source: {posting.source_type}",
            f"- Location: {posting.location or 'Unknown'}",
            f"- URL: {posting.source_url}",
            f"- Job Radar ID: `{posting.job_radar_id}`",
        ]
    )

    if posting.salary_text:
        lines.append(f"- Salary: {posting.salary_text}")

    lines.extend(
        [
            f"- Canonical key: `{posting.canonical_key}`",
            "",
        ]
    )


def _format_history_context(scored_posting: ScoredPosting) -> str:
    if not scored_posting.history_context:
        return "None"

    return "; ".join(scored_posting.history_context)


def _format_history_risk(scored_posting: ScoredPosting) -> str:
    if not scored_posting.history_risk_level:
        return "None"

    risk_reasons = scored_posting.history_risk_reasons or []

    if not risk_reasons:
        return scored_posting.history_risk_level

    return f"{scored_posting.history_risk_level}: {', '.join(risk_reasons)}"


def _format_work_arrangement(scored_posting: ScoredPosting) -> str:
    location_labels = _extract_location_reason_labels(scored_posting.score_reasons)

    if location_labels:
        return ", ".join(location_labels)

    if scored_posting.location_status in {"mixed", "conditional", "unknown"}:
        return "needs confirmation"

    if scored_posting.location_status == "skipped":
        return RISK_NOT_LOCATION_ELIGIBLE

    return "unknown"


def _extract_location_reason_labels(score_reasons: list[str]) -> list[str]:
    labels: list[str] = []

    for reason in score_reasons:
        if "location_" not in reason:
            continue

        if ":" not in reason:
            continue

        label = reason.split(":", maxsplit=1)[1].strip()

        if label and label not in labels:
            labels.append(label)

    return labels


def _format_match_summary(score_reasons: list[str]) -> str:
    if not score_reasons:
        return "No scoring reasons recorded"

    labels: list[str] = []

    for reason in score_reasons:
        if reason.startswith("-"):
            continue

        if ":" not in reason:
            continue

        keyword = reason.split(":", maxsplit=1)[1].strip()

        if keyword and keyword not in labels:
            labels.append(keyword)

    if not labels:
        return "No positive match reasons"

    return ", ".join(labels)


def _format_markdown_decision_explanation(
    scored_posting: ScoredPosting,
) -> tuple[str, str] | None:
    return _format_decision_explanation(scored_posting)


def _format_html_decision_explanation(
    scored_posting: ScoredPosting,
) -> tuple[str, str] | None:
    return _format_decision_explanation(scored_posting)


def _format_decision_explanation(
    scored_posting: ScoredPosting,
) -> tuple[str, str] | None:
    if _get_recommended_action(scored_posting) == ACTION_TRACK_STATUS:
        return (
            "Why it needs review",
            TRACK_STATUS_ALREADY_APPLIED_MESSAGE,
        )

    if scored_posting.top_match_eligible:
        if scored_posting.top_match_reasons:
            return (
                "Why it is a top match",
                "; ".join(scored_posting.top_match_reasons),
            )

        return (
            "Why it is a top match",
            "This role met the Top Match eligibility rules for score, "
            "location, and technical alignment.",
        )

    if scored_posting.review_needed_eligible:
        if scored_posting.location_status in {"mixed", "conditional", "unknown"}:
            return (
                "Why it needs review",
                "This role has enough technical signal to review manually, "
                "but the location fit needs confirmation.",
            )

        hiring_risks = _format_hiring_risk_flags(scored_posting)

        if hiring_risks != "None":
            return (
                "Why it needs review",
                f"{_get_recommended_action(scored_posting)} recommended, "
                f"but review risk first: {hiring_risks}.",
            )

        return (
            "Why it needs review",
            "This role has enough signal to review manually, but it did "
            "not qualify as a Top Match.",
        )

    return None


def _format_generated_at(generated_at: str) -> str:
    try:
        parsed_timestamp = datetime.fromisoformat(generated_at)
    except ValueError:
        return generated_at

    timezone_name = "UTC"

    if parsed_timestamp.tzinfo is None:
        timezone_name = "local"

    return f"{parsed_timestamp:%Y-%m-%d %H:%M} {timezone_name}"


def _get_top_matches(scored_postings: list[ScoredPosting]) -> list[ScoredPosting]:
    eligible_postings = [
        scored_posting
        for scored_posting in scored_postings
        if _is_top_match_report_posting(scored_posting)
    ]

    return eligible_postings


def _get_northern_colorado_highlights(
    scored_postings: list[ScoredPosting],
) -> list[ScoredPosting]:
    top_match_urls = {
        scored_posting.posting.source_url
        for scored_posting in _get_top_matches(scored_postings)
    }

    highlights = [
        scored_posting
        for scored_posting in scored_postings
        if scored_posting.posting.source_url not in top_match_urls
        and _is_northern_colorado_highlight(scored_posting)
    ]

    return highlights[:NORTHERN_COLORADO_HIGHLIGHTS_LIMIT]


def _is_northern_colorado_highlight(scored_posting: ScoredPosting) -> bool:
    if not scored_posting.top_match_eligible and not scored_posting.review_needed_eligible:
        return False

    location = (scored_posting.posting.location or "").lower()

    return any(
        keyword in location
        for keyword in NORTHERN_COLORADO_LOCATION_KEYWORDS
    )


def _append_html_count_summary(
    lines: list[str],
    heading: str,
    counts: dict[str, int],
) -> None:
    if not counts:
        return

    lines.append(f"<li><strong>{escape(heading)}:</strong><ul>")

    for label in sorted(counts):
        display_label = label

        if heading == "Work location fit":
            display_label = _format_work_arrangement_summary_label(label)

        lines.append(f"<li>{escape(display_label)}: {counts[label]}</li>")

    lines.append("</ul></li>")


def _append_html_work_arrangement_summary(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    _append_html_count_summary(
        lines=lines,
        heading="Work location fit",
        counts=_get_work_arrangement_summary_counts(scored_postings),
    )


def _append_html_tracker_action_summary(
    lines: list[str],
    tracker_workflow_summary: dict[str, int] | None,
) -> None:
    if not tracker_workflow_summary:
        return

    needs_action_count = _sum_tracker_workflow_states(
        tracker_workflow_summary,
        TRACKER_NEEDS_ACTION_WORKFLOW_STATES,
    )
    needs_review_count = _sum_tracker_workflow_states(
        tracker_workflow_summary,
        TRACKER_NEEDS_REVIEW_WORKFLOW_STATES,
    )

    if needs_action_count == 0 and needs_review_count == 0:
        return

    lines.append("<li><strong>Tracker action summary:</strong><ul>")
    lines.append(f"<li>Needs action: {needs_action_count}</li>")
    lines.append(f"<li>Needs review: {needs_review_count}</li>")
    lines.append("</ul></li>")


def _append_html_tracker_workflow_summary(
    lines: list[str],
    tracker_workflow_summary: dict[str, int] | None,
) -> None:
    if not tracker_workflow_summary:
        return

    lines.append("<li><strong>Tracker workflow summary:</strong><ul>")

    for workflow_state in _get_ordered_tracker_workflow_states(
        tracker_workflow_summary
    ):
        lines.append(
            f"<li>{escape(workflow_state)}: "
            f"{tracker_workflow_summary[workflow_state]}</li>"
        )

    lines.append("</ul></li>")


def _append_html_omitted_jobs_audit_summary(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    omitted_postings = _get_omitted_postings(scored_postings)

    if not omitted_postings:
        return

    omitted_reason_counts = _get_omitted_reason_summary_counts(omitted_postings)

    if not omitted_reason_counts:
        return

    lines.append("<li><strong>Omitted jobs audit:</strong>")
    lines.append("<ul>")
    lines.append("<li>One job may appear in more than one signal count.</li>")

    for reason in sorted(omitted_reason_counts):
        lines.append(
            f"<li>{escape(reason)}: {omitted_reason_counts[reason]}</li>"
        )

    lines.append("</ul>")
    lines.append("</li>")


def _append_html_history_context_summary(
    lines: list[str],
    history_context: list[str] | None,
) -> None:
    if not history_context:
        return

    lines.append("<li><strong>Job history context:</strong><ul>")

    for context_item in history_context:
        lines.append(f"<li>{escape(context_item)}</li>")

    lines.append("</ul></li>")


def _append_html_collector_errors(
    lines: list[str],
    collector_errors: list[ScanError],
) -> None:
    lines.extend(
        [
            "<h2>Collector Errors</h2>",
            "<ul>",
        ]
    )

    for error in collector_errors:
        lines.append(
            "<li>"
            f"{escape(error.company_key)} "
            f"({escape(error.company_name)}, {escape(error.source_type)}): "
            f"{escape(error.message)}"
            "</li>"
        )

    lines.append("</ul>")


def _append_html_scored_sections(
    lines: list[str],
    scored_postings: list[ScoredPosting],
    omitted_scored_postings: list[ScoredPosting] | None = None,
) -> None:
    _append_html_top_matches_section(lines, scored_postings)
    _append_html_northern_colorado_highlights_section(lines, scored_postings)
    _append_html_review_needed_section(lines, scored_postings)
    _append_html_omitted_jobs_section(
        lines,
        scored_postings=(
            omitted_scored_postings
            if omitted_scored_postings is not None
            else scored_postings
        ),
    )


def _append_html_top_matches_section(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    lines.append("<h2>Top Matches</h2>")

    top_matches = _get_top_matches(scored_postings)

    if not top_matches:
        lines.append("<p>No top matches found.</p>")
        return

    quick_view_top_matches = top_matches[:TOP_MATCHES_QUICK_VIEW_LIMIT]

    lines.extend(
        [
            "<h3>Quick View</h3>",
            '<ul class="quick-view">',
        ]
    )

    for scored_posting in quick_view_top_matches:
        posting = scored_posting.posting
        lines.append(
            "<li>"
            f"<strong>{scored_posting.score}</strong> - "
            f'<a href="{escape(posting.source_url, quote=True)}">'
            f"{escape(posting.title)}</a>"
            f"<br>Company: {escape(posting.company_name)}"
            f"<br>Location: {escape(posting.location or 'Unknown')}"
            f"<br>Work location fit: "
            f"{escape(_format_work_arrangement(scored_posting))}"
            "</li>"
        )

    lines.append("</ul>")

    for scored_posting in top_matches:
        _append_html_scored_posting(lines, scored_posting)


def _append_html_northern_colorado_highlights_section(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    lines.append("<h2>Northern Colorado Highlights</h2>")

    highlights = _get_northern_colorado_highlights(scored_postings)

    if not highlights:
        lines.append("<p>No Northern Colorado highlights found.</p>")
        return

    for scored_posting in highlights:
        _append_html_scored_posting(lines, scored_posting)


def _append_html_review_needed_section(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    lines.append("<h2>Review Needed</h2>")

    review_needed = _get_review_needed(scored_postings)

    if not review_needed:
        lines.append("<p>No review-needed jobs found.</p>")
        return

    for scored_posting in review_needed:
        _append_html_scored_posting(lines, scored_posting)


def _append_html_omitted_jobs_section(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    omitted_postings = _get_omitted_postings(scored_postings)
    ordered_omitted_postings = _get_ordered_omitted_postings(omitted_postings)

    lines.append("<h2>Passed / Not Recommended</h2>")

    if not omitted_postings:
        lines.append("<p>No passed jobs to show.</p>")
        return

    lines.append(
        "<p>"
        f"{len(omitted_postings)} scored jobs were not recommended for "
        "apply/review based on fit, location, compensation, or hiring-risk "
        "signals."
        "</p>"
    )

    omitted_reason_counts = _get_omitted_reason_summary_counts(omitted_postings)

    if omitted_reason_counts:
        lines.append("<p><strong>Risk / pass signal summary:</strong></p>")
        lines.append(
            "<p>One job may appear in more than one signal count.</p>"
        )
        lines.append("<ul>")

        for reason in sorted(omitted_reason_counts):
            lines.append(
                f"<li>{escape(reason)}: {omitted_reason_counts[reason]}</li>"
            )

        lines.append("</ul>")

    lines.append(
        f"<h3>Passed jobs most worth reviewing, up to "
        f"{PASSED_JOBS_REPORT_LIMIT}</h3>"
    )

    for scored_posting in ordered_omitted_postings[:PASSED_JOBS_REPORT_LIMIT]:
        _append_html_passed_posting(lines, scored_posting)

    if len(omitted_postings) > PASSED_JOBS_REPORT_LIMIT:
        lines.append(
            "<p>"
            f"{len(omitted_postings) - PASSED_JOBS_REPORT_LIMIT} additional "
            "passed jobs were hidden from this report to keep the file readable."
            "</p>"
        )


def _append_html_passed_posting(
    lines: list[str],
    scored_posting: ScoredPosting,
) -> None:
    posting = scored_posting.posting

    lines.extend(
        [
            '<section class="job-card">',
            f'<h3><a href="{escape(posting.source_url, quote=True)}">'
            f"{escape(posting.title)}</a></h3>",
            "<ul>",
            f"<li><strong>Company:</strong> {escape(posting.company_name)}</li>",
            f"<li><strong>Score:</strong> {scored_posting.score}</li>",
            f"<li><strong>Location:</strong> "
            f"{escape(posting.location or 'Unknown')}</li>",
            f"<li><strong>Recommended action:</strong> "
            f"{escape(_get_recommended_action(scored_posting))}</li>",
            f"<li><strong>Why not recommended:</strong> "
            f"{escape(_format_pass_reason(scored_posting))}</li>",
            f"<li><strong>Hiring risks:</strong> "
            f"{escape(_format_hiring_risk_flags(scored_posting))}</li>",
            f"<li><strong>Job Radar ID:</strong> "
            f"<code>{escape(posting.job_radar_id)}</code></li>",
            f"<li><strong>Posting:</strong> "
            f'<a href="{escape(posting.source_url, quote=True)}">'
            "View posting</a></li>",
            "</ul>",
            "</section>",
        ]
    )


def _append_html_track_status(
    lines: list[str],
    application: ApplicationRecord | None,
) -> None:
    if application is None:
        return

    workflow_state = get_application_workflow_state(application)

    lines.append("<li><strong>Track Status:</strong>")
    lines.append("<ul>")
    lines.append(f"<li>Status: {escape(application.status)}</li>")
    lines.append(f"<li>Workflow: {escape(workflow_state)}</li>")

    if application.follow_up_on:
        lines.append(f"<li>Follow up on: {escape(application.follow_up_on)}</li>")

    if application.outcome:
        lines.append(f"<li>Outcome: {escape(application.outcome)}</li>")

    if application.notes:
        lines.append(f"<li>Notes: {escape(application.notes)}</li>")

    lines.append("</ul>")
    lines.append("</li>")


def _append_html_unscored_jobs_section(
    lines: list[str],
    postings: list[JobPosting],
) -> None:
    lines.append("<h2>Jobs</h2>")

    if not postings:
        lines.append("<p>No jobs were collected during this scan.</p>")
        return

    for posting in postings:
        lines.extend(
            [
                '<section class="job-card">',
                f'<h3><a href="{escape(posting.source_url, quote=True)}">'
                f"{escape(posting.title)}</a></h3>",
                "<ul>",
                f"<li><strong>Company:</strong> "
                f"{escape(posting.company_name)}</li>",
                f"<li><strong>Source:</strong> {escape(posting.source_type)}</li>",
                f"<li><strong>Location:</strong> "
                f"{escape(posting.location or 'Unknown')}</li>",
                f"<li><strong>Job Radar ID:</strong> "
                f"<code>{escape(posting.job_radar_id)}</code></li>",
                f"<li><strong>Posting:</strong> "
                f'<a href="{escape(posting.source_url, quote=True)}">'
                "View posting</a></li>",
                "</ul>",
                "</section>",
            ]
        )


def _append_html_scored_posting(
    lines: list[str],
    scored_posting: ScoredPosting,
) -> None:
    posting = scored_posting.posting
    section_class = "job-card"
    recommended_action = _get_recommended_action(scored_posting)

    if recommended_action == ACTION_TRACK_STATUS:
        section_class = "job-card review-needed"
    elif scored_posting.top_match_eligible:
        section_class = "job-card top-match"
    elif scored_posting.review_needed_eligible:
        section_class = "job-card review-needed"

    decision_explanation = _format_html_decision_explanation(scored_posting)

    lines.extend(
        [
            f'<section class="{section_class}">',
            f'<h3><a href="{escape(posting.source_url, quote=True)}">'
            f"{escape(posting.title)}</a></h3>",
            "<ul>",
            f"<li><strong>Score:</strong> {scored_posting.score}</li>",
        ]
    )

    if decision_explanation is not None:
        label, explanation = decision_explanation
        lines.append(
            f"<li><strong>{escape(label)}:</strong> "
            f"{escape(explanation)}</li>"
        )

    lines.extend(
        [
            f"<li><strong>Why this matched:</strong> "
            f"{escape(_format_match_summary(scored_posting.score_reasons))}</li>",
            f"<li><strong>Technical match:</strong> "
            f"{escape(_get_technical_match_label(scored_posting))}</li>",
            f"<li><strong>Hiring probability:</strong> "
            f"{escape(_get_hiring_probability_label(scored_posting))}</li>",
            f"<li><strong>Recommended action:</strong> "
            f"{escape(_get_recommended_action(scored_posting))}</li>",
            f"<li><strong>Action rationale:</strong> "
            f"{escape(_get_action_rationale(scored_posting))}</li>",
            f"<li><strong>Hiring risks:</strong> "
            f"{escape(_format_hiring_risk_flags(scored_posting))}</li>",
            f"<li><strong>Job Radar ID:</strong> "
            f"<code>{escape(posting.job_radar_id)}</code></li>",
            f"<li><strong>History context:</strong> "
            f"{escape(_format_history_context(scored_posting))}</li>",
        ]
    )

    history_risk = _format_history_risk(scored_posting)

    if history_risk != "None":
        lines.append(
            f"<li><strong>History risk:</strong> {escape(history_risk)}</li>"
        )

    _append_html_track_status(lines, scored_posting.application)

    lines.extend(
        [
            f"<li><strong>Work location fit:</strong> "
            f"{escape(_format_work_arrangement(scored_posting))}</li>",
            f"<li><strong>Company:</strong> "
            f"{escape(posting.company_name)}</li>",
            f"<li><strong>Source:</strong> {escape(posting.source_type)}</li>",
            f"<li><strong>Location:</strong> "
            f"{escape(posting.location or 'Unknown')}</li>",
            f"<li><strong>Posting:</strong> "
            f'<a href="{escape(posting.source_url, quote=True)}">'
            "View posting</a></li>",
        ]
    )

    if posting.salary_text:
        lines.append(f"<li><strong>Salary:</strong> {escape(posting.salary_text)}</li>")

    lines.extend(
        [
            f"<li><strong>Canonical key:</strong> "
            f"<code>{escape(posting.canonical_key)}</code></li>",
            "</ul>",
            "</section>",
        ]
    )