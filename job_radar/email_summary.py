"""Turn a scan report into concise plain-text and HTML email summaries."""

from datetime import datetime
from html import escape
from pathlib import Path

from job_radar.recommendation_constants import (
    ACTION_HOLD,
    ACTION_PASS,
    RISK_NOT_LOCATION_ELIGIBLE,
)

from job_radar.report_view_model import (
    build_job_output_view_model,
    build_report_view_model,
    is_email_review_needed_posting,
    is_email_top_match_posting,
)
from job_radar.recommendations import (
    _get_recommendation_summary_counts,
    _get_recommended_action,
)
from job_radar.report_models import ScanReport
from job_radar.scored_posting import ScoredPosting


EMAIL_POSTINGS_LIMIT = 10


def build_email_subject(report: ScanReport) -> str:
    report_date = _get_report_date(report.generated_at)
    email_scored_postings = _get_email_summary_scored_postings(report)
    top_matches = _get_top_matches(email_scored_postings)
    review_needed = _get_review_needed(email_scored_postings)

    return (
        f"junior Report - {report_date} - "
        f"{report.jobs_collected} jobs - "
        f"{len(top_matches)} top match"
        f"{_plural_suffix(len(top_matches))} - "
        f"{len(review_needed)} review needed"
    )


def build_email_body(
    report: ScanReport,
    report_path: str | Path,
    include_report_path: bool = True,
) -> str:
    email_scored_postings = _get_email_summary_scored_postings(report)
    top_matches = _get_top_matches(email_scored_postings)
    review_needed = _get_review_needed(email_scored_postings)

    lines: list[str] = [
        f"Generated at: {_format_generated_at(report.generated_at)}",
        f"Companies enabled: {report.companies_enabled}",
        f"Jobs collected: {report.jobs_collected}",
        _format_optional_count_line(
            "Actionable jobs stored",
            report.jobs_stored,
        ),
        _format_optional_count_line(
            "Jobs not actionable",
            report.jobs_omitted,
        ),
        f"New jobs: {report.jobs_new}",
        f"Seen jobs: {report.jobs_seen}",
        f"Changed jobs: {report.jobs_changed}",
        f"Collector errors: {len(report.collector_errors)}",
        _format_threshold_line(
            label="Top match score threshold",
            threshold=report.top_match_min_score,
        ),
        _format_threshold_line(
            label="Review-needed score threshold",
            threshold=report.review_needed_min_score,
        ),
    ]

    if report.scored_postings is not None:
        _append_email_recommendation_summary(
            lines,
            _get_email_summary_scored_postings(report),
        )

    lines.extend(
        [
            "",
            f"Top Matches, up to {EMAIL_POSTINGS_LIMIT}:",
        ]
    )

    _append_email_posting_lines(
        lines=lines,
        scored_postings=top_matches,
        section_type="top_match",
    )

    lines.extend(
        [
            "",
            f"Review Needed, up to {EMAIL_POSTINGS_LIMIT}:",
        ]
    )

    _append_email_posting_lines(
        lines=lines,
        scored_postings=review_needed,
        section_type="review_needed",
    )

    lines.extend(
        [
            "",
            "Full report:",
        ]
    )

    if include_report_path:
        lines.append(str(report_path))
    else:
        lines.append("Attached as HTML file.")

    return "\n".join(lines)

def build_email_html_body(
    report: ScanReport,
    report_path: str | Path,
    include_report_path: bool = True,
) -> str:
    email_scored_postings = _get_email_summary_scored_postings(report)
    top_matches = _get_top_matches(email_scored_postings)
    review_needed = _get_review_needed(email_scored_postings)

    lines: list[str] = [
        "<!doctype html>",
        "<html>",
        "<body>",
        "<h1>junior Report</h1>",
        "<h2>Summary</h2>",
        "<ul>",
        f"<li><strong>Generated at:</strong> "
        f"{escape(_format_generated_at(report.generated_at))}</li>",
        f"<li><strong>Companies enabled:</strong> {report.companies_enabled}</li>",
        f"<li><strong>Jobs collected:</strong> {report.jobs_collected}</li>",
        f"<li><strong>Actionable jobs stored:</strong> "
        f"{_format_optional_count(report.jobs_stored)}</li>",
        f"<li><strong>Jobs not actionable:</strong> "
        f"{_format_optional_count(report.jobs_omitted)}</li>",
        f"<li><strong>New jobs:</strong> {report.jobs_new}</li>",
        f"<li><strong>Seen jobs:</strong> {report.jobs_seen}</li>",
        f"<li><strong>Changed jobs:</strong> {report.jobs_changed}</li>",
        f"<li><strong>Collector errors:</strong> {len(report.collector_errors)}</li>",
        f"<li><strong>Top match score threshold:</strong> "
        f"{_format_optional_count(report.top_match_min_score)}</li>",
        f"<li><strong>Review-needed score threshold:</strong> "
        f"{_format_optional_count(report.review_needed_min_score)}</li>",
    ]

    if report.scored_postings is not None:
        _append_email_html_recommendation_summary(
            lines,
            _get_email_summary_scored_postings(report),
        )

    lines.append("</ul>")

    _append_html_posting_section(
        lines=lines,
        heading=f"Top Matches, up to {EMAIL_POSTINGS_LIMIT}",
        scored_postings=top_matches,
        section_type="top_match",
    )

    _append_html_posting_section(
        lines=lines,
        heading=f"Review Needed, up to {EMAIL_POSTINGS_LIMIT}",
        scored_postings=review_needed,
        section_type="review_needed",
    )

    lines.extend(
        [
            "<h2>Full report</h2>",
        ]
    )

    if include_report_path:
        lines.append(f"<p>{escape(str(report_path))}</p>")
    else:
        lines.append("<p>Attached as HTML file.</p>")

    lines.extend(
        [
            "</body>",
            "</html>",
        ]
    )

    return "\n".join(lines)


def write_email_preview(
    path: str | Path,
    report: ScanReport,
) -> Path:
    preview_path = Path(path)
    preview_path.parent.mkdir(parents=True, exist_ok=True)

    subject = build_email_subject(report)
    body = build_email_body(
        report,
        report_path="",
        include_report_path=False,
    )

    preview_text = f"Subject: {subject}\n\n{body}\n"
    preview_path.write_text(preview_text, encoding="utf-8")

    return preview_path


def _get_report_date(generated_at: str | None) -> str:
    if not generated_at:
        return "unknown-date"

    return generated_at.split("T", maxsplit=1)[0]


def _format_generated_at(generated_at: str | None) -> str:
    if not generated_at:
        return "Unknown"

    try:
        parsed_timestamp = datetime.fromisoformat(generated_at)
    except ValueError:
        return generated_at

    timezone_name = "UTC"

    if parsed_timestamp.tzinfo is None:
        timezone_name = "local"

    return f"{parsed_timestamp:%Y-%m-%d %H:%M} {timezone_name}"


def _format_threshold_line(label: str, threshold: int | None) -> str:
    if threshold is None:
        return f"{label}: Unknown"

    return f"{label}: {threshold}"


def _format_optional_count_line(label: str, count: int | None) -> str:
    if count is None:
        return f"{label}: Unknown"

    return f"{label}: {count}"


def _get_email_summary_scored_postings(report: ScanReport) -> list[ScoredPosting]:
    return build_report_view_model(
        scored_postings=report.scored_postings,
        omitted_scored_postings=report.omitted_scored_postings,
        email_postings_limit=EMAIL_POSTINGS_LIMIT,
    ).email_scored_postings


def _is_email_actionable_posting(scored_posting: ScoredPosting) -> bool:
    return _get_recommended_action(scored_posting) not in {ACTION_HOLD, ACTION_PASS}


def _is_email_top_match_posting(scored_posting: ScoredPosting) -> bool:
    return is_email_top_match_posting(scored_posting)


def _is_email_review_needed_posting(scored_posting: ScoredPosting) -> bool:
    return is_email_review_needed_posting(scored_posting)


def _get_top_matches(
    scored_postings: list[ScoredPosting] | None,
) -> list[ScoredPosting]:
    return build_report_view_model(
        scored_postings=scored_postings,
        email_postings_limit=EMAIL_POSTINGS_LIMIT,
    ).email_top_matches


def _get_review_needed(
    scored_postings: list[ScoredPosting] | None,
) -> list[ScoredPosting]:
    return build_report_view_model(
        scored_postings=scored_postings,
        email_postings_limit=EMAIL_POSTINGS_LIMIT,
    ).email_review_needed


def _append_email_posting_lines(
    lines: list[str],
    scored_postings: list[ScoredPosting],
    section_type: str,
) -> None:
    if not scored_postings:
        lines.append("- None")
        return

    for index, scored_posting in enumerate(scored_postings, start=1):
        _append_email_posting_detail(
            lines=lines,
            scored_posting=scored_posting,
            index=index,
            section_type=section_type,
        )


def _append_email_posting_detail(
    lines: list[str],
    scored_posting: ScoredPosting,
    index: int,
    section_type: str,
) -> None:
    job = build_job_output_view_model(scored_posting)

    lines.extend(
        [
            f"{index}. {job.title}",
            f"   Company: {job.company}",
            f"   Score: {job.score}",
            f"   Eligibility: {job.eligibility_label}",
            f"   Eligibility reasons: {job.eligibility_reason_text}",
            f"   Location: {job.location}",
            f"   Role fit: {job.technical_match}",
            f"   Resume match: {job.resume_match}",
            f"   Resume evidence: {job.resume_evidence}",
            f"   Resume gaps: {job.resume_gaps}",
            f"   Compensation: {job.compensation}",
            f"   Compensation range: {job.compensation_range}",
            f"   Hiring probability: {job.hiring_probability}",
            f"   Recommended action: {job.recommended_action}",
            f"   Action rationale: {job.action_rationale}",
            f"   Hiring risks: {job.hiring_risks}",
        ]
    )

    if section_type == "top_match":
        _append_reason_lines(
            lines=lines,
            heading="Why it is a top match:",
            reasons=_get_top_match_reasons(scored_posting),
        )

    if section_type == "review_needed":
        _append_reason_lines(
            lines=lines,
            heading="Why it needs review:",
            reasons=_get_review_needed_reasons(scored_posting),
        )

    lines.append(
        f"   Signals: {_format_signal_summary(scored_posting.score_reasons)}"
    )


def _append_email_recommendation_summary(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    recommendation_counts = _get_recommendation_summary_counts(scored_postings)

    if not recommendation_counts:
        return

    lines.append("Recommendation summary:")

    for recommendation, count in recommendation_counts.items():
        lines.append(f"  - {recommendation}: {count}")


def _get_top_match_reasons(scored_posting: ScoredPosting) -> list[str]:
    if scored_posting.top_match_reasons:
        return _format_email_reason_lines(scored_posting.top_match_reasons)

    return [
        "Score and match signals make this a strong candidate.",
        _format_email_work_arrangement_reason(scored_posting),
    ]


def _get_review_needed_reasons(scored_posting: ScoredPosting) -> list[str]:
    return [
        "Strong technical signals, but review before applying.",
        _format_email_work_arrangement_reason(scored_posting),
    ]


def _format_email_reason_lines(reasons: list[str]) -> list[str]:
    formatted_reasons: list[str] = []

    for reason in reasons:
        formatted_reason = _format_email_reason(reason)

        if formatted_reason not in formatted_reasons:
            formatted_reasons.append(formatted_reason)

    return formatted_reasons


def _format_email_reason(reason: str) -> str:
    if reason.startswith("score ") and " meets top-match threshold " in reason:
        return "Score meets the top-match threshold."

    if reason.startswith("location fit is acceptable"):
        return "Work arrangement fits your preferences."

    if reason.startswith("strong signal matched:"):
        signal = reason.split(":", maxsplit=1)[1].strip()
        signal_label = _format_signal_label(signal)
        return f"Strong match signal: {signal_label}."

    if reason == "marked eligible by top-match scoring rules":
        return "Score and match signals make this a strong candidate."

    if reason == "marked eligible by review-needed scoring rules":
        return "Strong technical signals, but review before applying."

    if reason.startswith("work arrangement:"):
        return _format_work_arrangement_label(
            reason.split(":", maxsplit=1)[1].strip()
        )

    return reason


def _format_email_work_arrangement_reason(scored_posting: ScoredPosting) -> str:
    return _format_work_arrangement_label(
        _format_email_work_arrangement(scored_posting)
    )


def _format_work_arrangement_label(work_arrangement: str) -> str:
    if work_arrangement == "remote":
        return "Remote role fits your preferences."

    if work_arrangement == RISK_NOT_LOCATION_ELIGIBLE:
        return "Work arrangement does not fit your preferences."

    if work_arrangement == "needs confirmation":
        return "Work arrangement needs confirmation."

    if work_arrangement == "unknown":
        return "Work arrangement is unknown."

    return f"Work arrangement: {work_arrangement}."


def _format_signal_label(signal: str) -> str:
    if ":" not in signal:
        return signal

    signal_source, signal_value = signal.split(":", maxsplit=1)

    if signal_source == "title":
        return f"title matches {signal_value}"

    if signal_source == "body":
        return f"description mentions {signal_value}"

    return signal_value


def _append_reason_lines(
    lines: list[str],
    heading: str,
    reasons: list[str] | None,
) -> None:
    lines.append(f"   {heading}")

    if not reasons:
        lines.append("      - None")
        return

    for reason in reasons:
        lines.append(f"      - {reason}")


def _format_signal_summary(score_reasons: list[str]) -> str:
    if not score_reasons:
        return "None"

    labels: list[str] = []

    for reason in score_reasons:
        if reason.startswith("-"):
            continue

        if ":" not in reason:
            continue

        label = reason.split(":", maxsplit=1)[1].strip()

        if label and label not in labels:
            labels.append(label)

    if not labels:
        return "None"

    return ", ".join(labels)


def _append_email_html_recommendation_summary(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    recommendation_counts = _get_recommendation_summary_counts(scored_postings)

    if not recommendation_counts:
        return

    lines.append("<li><strong>Recommendation summary:</strong><ul>")

    for recommendation, count in recommendation_counts.items():
        lines.append(f"<li>{escape(recommendation)}: {count}</li>")

    lines.append("</ul></li>")


def _append_html_posting_section(
    lines: list[str],
    heading: str,
    scored_postings: list[ScoredPosting],
    section_type: str,
) -> None:
    lines.append(f"<h2>{escape(heading)}</h2>")

    if not scored_postings:
        lines.append("<p>None</p>")
        return

    for scored_posting in scored_postings:
        _append_html_posting_detail(
            lines=lines,
            scored_posting=scored_posting,
            section_type=section_type,
        )


def _append_html_posting_detail(
    lines: list[str],
    scored_posting: ScoredPosting,
    section_type: str,
) -> None:
    job = build_job_output_view_model(scored_posting)

    lines.extend(
        [
            "<section>",
            f"<h3>{escape(job.title)}</h3>",
            "<ul>",
            f"<li><strong>Company:</strong> "
            f"{escape(job.company)}</li>",
            f"<li><strong>Score:</strong> {job.score}</li>",
            f"<li><strong>Eligibility:</strong> "
            f"{escape(job.eligibility_label)}</li>",
            f"<li><strong>Eligibility reasons:</strong> "
            f"{escape(job.eligibility_reason_text)}</li>",
            f"<li><strong>Location:</strong> "
            f"{escape(job.location)}</li>",
            f"<li><strong>Role fit:</strong> "
            f"{escape(job.technical_match)}</li>",
            f"<li><strong>Resume match:</strong> "
            f"{escape(job.resume_match)}</li>",
            f"<li><strong>Resume evidence:</strong> "
            f"{escape(job.resume_evidence)}</li>",
            f"<li><strong>Resume gaps:</strong> "
            f"{escape(job.resume_gaps)}</li>",
            f"<li><strong>Compensation:</strong> "
            f"{escape(job.compensation)}</li>",
            f"<li><strong>Compensation range:</strong> "
            f"{escape(job.compensation_range)}</li>",
            f"<li><strong>Hiring probability:</strong> "
            f"{escape(job.hiring_probability)}</li>",
            f"<li><strong>Recommended action:</strong> "
            f"{escape(job.recommended_action)}</li>",
            f"<li><strong>Action rationale:</strong> "
            f"{escape(job.action_rationale)}</li>",
            f"<li><strong>Hiring risks:</strong> "
            f"{escape(job.hiring_risks)}</li>",
            f"<li><strong>Signals:</strong> "
            f"{escape(_format_signal_summary(scored_posting.score_reasons))}</li>",
            "</ul>",
        ]
    )

    if section_type == "top_match":
        _append_html_reason_lines(
            lines=lines,
            heading="Why it is a top match",
            reasons=_get_top_match_reasons(scored_posting),
        )

    if section_type == "review_needed":
        _append_html_reason_lines(
            lines=lines,
            heading="Why it needs review",
            reasons=_get_review_needed_reasons(scored_posting),
        )

    if job.source_url:
        lines.append(
            f'<p><a href="{escape(job.source_url, quote=True)}">'
            "View posting"
            "</a></p>"
        )

    lines.append("</section>")


def _append_html_reason_lines(
    lines: list[str],
    heading: str,
    reasons: list[str] | None,
) -> None:
    lines.append(f"<p><strong>{escape(heading)}:</strong></p>")

    if not reasons:
        lines.append("<ul><li>None</li></ul>")
        return

    lines.append("<ul>")

    for reason in reasons:
        lines.append(f"<li>{escape(reason)}</li>")

    lines.append("</ul>")


def _format_optional_count(count: int | None) -> str:
    if count is None:
        return "Unknown"

    return str(count)


def _format_email_work_arrangement(scored_posting: ScoredPosting) -> str:
    for reason in scored_posting.score_reasons:
        if "location_" not in reason:
            continue

        if ":" not in reason:
            continue

        label = reason.split(":", maxsplit=1)[1].strip()

        if label:
            return label

    if scored_posting.location_status in {"mixed", "conditional", "unknown"}:
        return "needs confirmation"

    if scored_posting.location_status == "skipped":
        return RISK_NOT_LOCATION_ELIGIBLE

    return "unknown"


def _format_value(value: str | None) -> str:
    if not value:
        return "Unknown"

    return value


def _plural_suffix(count: int) -> str:
    if count == 1:
        return ""

    return "es"
