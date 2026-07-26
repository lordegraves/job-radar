"""Render a complete, safe-to-open HTML report from one scan result."""

from datetime import datetime
from html import escape
from pathlib import Path

from job_radar import __display_version__
from job_radar.models import JobPosting
from job_radar.report_models import ScanError, ScanReport
from job_radar.report_view_model import (
    build_job_output_view_model,
    build_report_view_model,
    is_review_needed_report_posting,
    is_top_match_report_posting,
)
from job_radar.scored_posting import ScoredPosting
from job_radar.tracker.tracker_models import ApplicationRecord
from job_radar.tracker.tracker_service import get_application_workflow_state
from job_radar.recommendation_constants import (
    ACTION_HOLD,
    ACTION_PASS,
    ACTION_PREVIOUSLY_REVIEWED,
    ACTION_TRACK_STATUS,
    RISK_BELOW_COMPENSATION_FLOOR,
    RISK_HARD_LOCATION_MISMATCH,
    RISK_LOCATION_NEEDS_CONFIRMATION,
    RISK_NOT_LOCATION_ELIGIBLE,
    TRACK_STATUS_ALREADY_APPLIED_MESSAGE,
)
from job_radar.recommendations import (
    _format_hiring_risk_flags,
    _get_hiring_risk_flags,
    _get_recommendation_summary_counts,
    _get_recommended_action,
    _get_technical_match_label,
)


TOP_MATCHES_QUICK_VIEW_LIMIT = 10
PASSED_JOBS_REPORT_LIMIT = 25

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


def render_html_report(report: ScanReport) -> str:
    lines: list[str] = [
        "<!doctype html>",
        "<html>",
        "<head>",
        '<meta charset="utf-8">',
        "<title>junior Report</title>",
        "<style>",
        "html { scroll-behavior: smooth; }",
        "body { font-family: Arial, sans-serif; line-height: 1.4; margin: 24px; }",
        "h1 { margin-bottom: 8px; }",
        "h2 { border-bottom: 1px solid #cccccc; padding-bottom: 4px; margin-top: 28px; scroll-margin-top: 16px; }",
        "h3 { margin-bottom: 8px; }",
        "a { color: #0b66c3; }",
        ".table-of-contents { background: #f6f8fa; border: 1px solid #dddddd; padding: 12px 16px; margin-bottom: 20px; }",
        ".table-of-contents ul { margin-bottom: 0; }",
        ".summary { background: #f6f8fa; border: 1px solid #dddddd; padding: 12px 16px; }",
        ".job-card { border: 1px solid #dddddd; padding: 14px 16px; margin: 16px 0; border-radius: 6px; }",
        ".top-match { border-left: 6px solid #2e7d32; }",
        ".review-needed { border-left: 6px solid #b26a00; }",
        ".tracked-application { border-left: 6px solid #5f6368; }",
        ".quick-view { background: #f6f8fa; border: 1px solid #dddddd; padding: 10px 14px; }",
        "code { background: #f6f8fa; padding: 2px 4px; }",
        "</style>",
        "</head>",
        "<body>",
        "<h1>junior Report</h1>",
        f"<p><strong>Junior build:</strong> {escape(__display_version__)}</p>",
    ]

    _append_html_table_of_contents(lines, report)

    lines.extend(
        [
            '<h2 id="summary">Summary</h2>',
            '<ul class="summary">',
        ]
    )

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

    if report.scored_postings is not None:
        report_view = build_report_view_model(
            scored_postings=report.scored_postings,
            omitted_scored_postings=report.omitted_scored_postings,
        )
        lines.extend(
            [
                f"<li><strong>Top matches:</strong> "
                f"{len(report_view.top_matches)}</li>",
                f"<li><strong>Review needed:</strong> "
                f"{len(report_view.review_needed)}</li>",
                f"<li><strong>Tracked applications:</strong> "
                f"{len(report_view.tracked_applications)}</li>",
            ]
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
        _append_html_back_to_contents(lines)

    if report.scored_postings is not None:
        _append_html_scored_sections(
            lines,
            scored_postings=report.scored_postings,
            new_scored_postings=report.new_scored_postings,
            omitted_scored_postings=report.omitted_scored_postings,
        )
    else:
        _append_html_unscored_jobs_section(lines, report.postings)
        _append_html_back_to_contents(lines)

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


def _append_html_table_of_contents(
    lines: list[str],
    report: ScanReport,
) -> None:
    sections = [("summary", "Summary")]

    if report.collector_errors:
        sections.append(("collector-errors", "Collector Errors"))

    if report.scored_postings is not None:
        sections.extend(
            [
                ("top-matches", "Top Matches"),
                ("potential-top-matches", "Potential Top Matches"),
                ("review-needed", "Review Needed"),
                ("tracked-applications", "Tracked Applications"),
                ("new-jobs", "New Jobs"),
                ("passed-not-recommended", "Passed / Not Recommended"),
            ]
        )
    else:
        sections.append(("jobs", "Jobs"))

    lines.extend(
        [
            '<nav id="report-contents" class="table-of-contents" '
            'aria-label="Report contents">',
            "<h2>Report contents</h2>",
            "<ul>",
        ]
    )

    for section_id, section_label in sections:
        lines.append(
            f'<li><a href="#{section_id}">{escape(section_label)}</a></li>'
        )

    lines.extend(
        [
            "</ul>",
            "</nav>",
        ]
    )


def _append_html_back_to_contents(lines: list[str]) -> None:
    lines.append(
        '<p><a href="#report-contents">Back to report contents</a></p>'
    )


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


def _sum_tracker_workflow_states(
    tracker_workflow_summary: dict[str, int],
    workflow_states: tuple[str, ...],
) -> int:
    return sum(
        tracker_workflow_summary.get(workflow_state, 0)
        for workflow_state in workflow_states
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
    return build_report_view_model(
        scored_postings=report.scored_postings,
        omitted_scored_postings=report.omitted_scored_postings,
    ).report_scored_postings


def _get_surfaced_recommendation_postings(report: ScanReport) -> list[ScoredPosting]:
    scored_postings = list(report.scored_postings or [])
    report_scored_postings = _get_report_scored_postings(report)
    surfaced_postings: list[ScoredPosting] = []

    surfaced_postings.extend(_get_top_matches(scored_postings))
    surfaced_postings.extend(_get_review_needed(report_scored_postings))
    surfaced_postings.extend(_get_tracked_applications(report_scored_postings))

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


def _is_top_match_report_posting(scored_posting: ScoredPosting) -> bool:
    return is_top_match_report_posting(scored_posting)


def _is_review_needed_report_posting(scored_posting: ScoredPosting) -> bool:
    return is_review_needed_report_posting(scored_posting)


def _get_review_needed(
    scored_postings: list[ScoredPosting],
) -> list[ScoredPosting]:
    return build_report_view_model(
        scored_postings=scored_postings,
    ).review_needed


def _get_tracked_applications(
    scored_postings: list[ScoredPosting],
) -> list[ScoredPosting]:
    return build_report_view_model(
        scored_postings=scored_postings,
    ).tracked_applications


def _get_omitted_postings(
    scored_postings: list[ScoredPosting],
) -> list[ScoredPosting]:
    return [
        scored_posting
        for scored_posting in scored_postings
        if not _is_top_match_report_posting(scored_posting)
        and not _is_review_needed_report_posting(scored_posting)
        and _get_recommended_action(scored_posting) != ACTION_TRACK_STATUS
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

    if any(risk.startswith("profile avoid match:") for risk in risks):
        review_score -= 80

    return review_score


def _format_pass_reason(scored_posting: ScoredPosting) -> str:
    recommended_action = _get_recommended_action(scored_posting)
    risks = _get_hiring_risk_flags(scored_posting)

    if recommended_action == ACTION_TRACK_STATUS:
        return TRACK_STATUS_ALREADY_APPLIED_MESSAGE

    if recommended_action == ACTION_PASS:
        if RISK_BELOW_COMPENSATION_FLOOR in risks:
            return "Compensation appears below your current floor."

        if RISK_NOT_LOCATION_ELIGIBLE in risks:
            return "Location does not fit this profile's selected locations."

        if any(risk.startswith("profile avoid match:") for risk in risks):
            return "The role matches an exclusion saved in this profile."

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

    if risk == RISK_NOT_LOCATION_ELIGIBLE:
        return "Not location eligible"

    if risk.startswith("profile avoid match:"):
        return "Profile exclusion"

    if risk.startswith("profile gap:"):
        return "Profile gap"

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


def _format_html_decision_explanation(
    scored_posting: ScoredPosting,
) -> tuple[str, str] | None:
    return _format_decision_explanation(scored_posting)


def _format_decision_explanation(
    scored_posting: ScoredPosting,
) -> tuple[str, str] | None:
    if _get_recommended_action(scored_posting) == ACTION_TRACK_STATUS:
        return (
            "Why it is tracked",
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
    return build_report_view_model(
        scored_postings=scored_postings,
    ).top_matches


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
            '<h2 id="collector-errors">Collector Errors</h2>',
            "<p>Some collector errors are temporary source or network issues and may clear on a later scan.</p>",
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
    new_scored_postings: list[ScoredPosting] | None = None,
    omitted_scored_postings: list[ScoredPosting] | None = None,
) -> None:
    report_scored_postings = list(scored_postings)

    if omitted_scored_postings is not None:
        report_scored_postings.extend(omitted_scored_postings)

    _append_html_top_matches_section(lines, report_scored_postings)
    _append_html_back_to_contents(lines)

    _append_html_potential_top_matches_section(lines, report_scored_postings)
    _append_html_back_to_contents(lines)

    _append_html_review_needed_section(lines, report_scored_postings)
    _append_html_back_to_contents(lines)

    _append_html_tracked_applications_section(lines, report_scored_postings)
    _append_html_back_to_contents(lines)

    _append_html_new_jobs_section(
        lines,
        new_scored_postings or [],
    )
    _append_html_back_to_contents(lines)

    _append_html_omitted_jobs_section(
        lines,
        scored_postings=(
            omitted_scored_postings
            if omitted_scored_postings is not None
            else report_scored_postings
        ),
    )
    _append_html_back_to_contents(lines)


def _append_html_top_matches_section(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    lines.append('<h2 id="top-matches">Top Matches</h2>')

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
            f'<a href="{escape(posting.source_url, quote=True)}" '
            'target="_blank" rel="noopener noreferrer">'
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


def _append_html_review_needed_section(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    lines.append('<h2 id="review-needed">Review Needed</h2>')

    review_needed = _get_review_needed(scored_postings)

    if not review_needed:
        lines.append("<p>No review-needed jobs found.</p>")
        return

    for scored_posting in review_needed:
        _append_html_scored_posting(lines, scored_posting)


def _append_html_potential_top_matches_section(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    lines.append('<h2 id="potential-top-matches">Potential Top Matches</h2>')
    potential_matches = build_report_view_model(
        scored_postings=scored_postings,
    ).potential_top_matches

    if not potential_matches:
        lines.append("<p>No potential top matches found.</p>")
        return

    lines.append(
        "<p>These roles have strong fit evidence, but important practical "
        "details still need confirmation.</p>"
    )
    for scored_posting in potential_matches:
        _append_html_scored_posting(lines, scored_posting)


def _append_html_tracked_applications_section(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    lines.append('<h2 id="tracked-applications">Tracked Applications</h2>')

    tracked_applications = _get_tracked_applications(scored_postings)

    if not tracked_applications:
        lines.append("<p>No tracked applications found in this scan.</p>")
        return

    for scored_posting in tracked_applications:
        _append_html_scored_posting(lines, scored_posting)


def _append_html_new_jobs_section(
    lines: list[str],
    new_scored_postings: list[ScoredPosting],
) -> None:
    lines.append('<h2 id="new-jobs">New Jobs</h2>')

    if not new_scored_postings:
        lines.append("<p>No new actionable jobs were found in the latest scan.</p>")
        return

    for scored_posting in new_scored_postings:
        _append_html_scored_posting(lines, scored_posting)


def _append_html_omitted_jobs_section(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    omitted_postings = _get_omitted_postings(scored_postings)
    ordered_omitted_postings = _get_ordered_omitted_postings(omitted_postings)

    lines.append(
        '<h2 id="passed-not-recommended">Passed / Not Recommended</h2>'
    )

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
            "jobs did not meet this profile's relevance or practical "
            "requirements. They are summarized rather than listed here; "
            "the raw scan download contains every collected posting."
            "</p>"
        )


def _append_html_passed_posting(
    lines: list[str],
    scored_posting: ScoredPosting,
) -> None:
    job = build_job_output_view_model(scored_posting)

    lines.extend(
        [
            '<section class="job-card">',
            f'<h3><a href="{escape(job.source_url, quote=True)}" '
            'target="_blank" rel="noopener noreferrer">'
            f"{escape(job.title)}</a></h3>",
            "<ul>",
            f"<li><strong>Company:</strong> {escape(job.company)}</li>",
            f"<li><strong>Score:</strong> {job.score}</li>",
            f"<li><strong>Eligibility:</strong> "
            f"{escape(job.eligibility_label)}</li>",
            f"<li><strong>Eligibility reasons:</strong> "
            f"{escape(job.eligibility_reason_text)}</li>",
            f"<li><strong>Location:</strong> "
            f"{escape(job.location)}</li>",
            f"<li><strong>Recommended action:</strong> "
            f"{escape(job.recommended_action)}</li>",
            f"<li><strong>Why not recommended:</strong> "
            f"{escape(_format_pass_reason(scored_posting))}</li>",
            f"<li><strong>Hiring risks:</strong> "
            f"{escape(job.hiring_risks)}</li>",
            f"<li><strong>Posting:</strong> "
            f'<a href="{escape(job.source_url, quote=True)}" '
            'target="_blank" rel="noopener noreferrer">'
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
    lines.append('<h2 id="jobs">Jobs</h2>')

    if not postings:
        lines.append("<p>No jobs were collected during this scan.</p>")
        return

    for posting in postings:
        lines.extend(
            [
                '<section class="job-card">',
                f'<h3><a href="{escape(posting.source_url, quote=True)}" '
                'target="_blank" rel="noopener noreferrer">'
                f"{escape(posting.title)}</a></h3>",
                "<ul>",
                f"<li><strong>Company:</strong> "
                f"{escape(posting.company_name)}</li>",
                f"<li><strong>Source:</strong> {escape(posting.source_type)}</li>",
                f"<li><strong>Location:</strong> "
                f"{escape(posting.location or 'Unknown')}</li>",
                f"<li><strong>Posting:</strong> "
                f'<a href="{escape(posting.source_url, quote=True)}" '
                'target="_blank" rel="noopener noreferrer">'
                "View posting</a></li>",
                "</ul>",
                "</section>",
            ]
        )


def _append_html_scored_posting(
    lines: list[str],
    scored_posting: ScoredPosting,
) -> None:
    job = build_job_output_view_model(scored_posting)
    posting = scored_posting.posting
    section_class = "job-card"
    recommended_action = job.recommended_action

    if recommended_action == ACTION_TRACK_STATUS:
        section_class = "job-card tracked-application"
    elif scored_posting.top_match_eligible:
        section_class = "job-card top-match"
    elif scored_posting.review_needed_eligible:
        section_class = "job-card review-needed"

    decision_explanation = _format_html_decision_explanation(scored_posting)

    lines.extend(
        [
            f'<section class="{section_class}">',
            f'<h3><a href="{escape(posting.source_url, quote=True)}" '
            'target="_blank" rel="noopener noreferrer">'
            f"{escape(posting.title)}</a></h3>",
            "<ul>",
            f"<li><strong>Score:</strong> {job.score}</li>",
            f"<li><strong>Eligibility:</strong> "
            f"{escape(job.eligibility_label)}</li>",
            f"<li><strong>Eligibility reasons:</strong> "
            f"{escape(job.eligibility_reason_text)}</li>",
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
            f"{escape(job.why_matched)}</li>",
            f"<li><strong>Role fit:</strong> "
            f"{escape(job.technical_match)}</li>",
            f"<li><strong>Hiring probability:</strong> "
            f"{escape(job.hiring_probability)}</li>",
            f"<li><strong>Recommended action:</strong> "
            f"{escape(job.recommended_action)}</li>",
            f"<li><strong>Action rationale:</strong> "
            f"{escape(job.action_rationale)}</li>",
            f"<li><strong>Hiring risks:</strong> "
            f"{escape(job.hiring_risks)}</li>",
            f"<li><strong>History context:</strong> "
            f"{escape(job.history_context)}</li>",
        ]
    )

    history_risk = job.history_risk

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
            f"{escape(job.company)}</li>",
            f"<li><strong>Source:</strong> {escape(job.source_type)}</li>",
            f"<li><strong>Location:</strong> "
            f"{escape(job.location)}</li>",
            f"<li><strong>Posting:</strong> "
            f'<a href="{escape(posting.source_url, quote=True)}" '
            'target="_blank" rel="noopener noreferrer">'
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
