from datetime import datetime
from html import escape
from pathlib import Path

from job_radar.reporting import ScanReport, ScoredPosting, TOP_MATCHES_LIMIT


def build_email_subject(report: ScanReport) -> str:
    report_date = _get_report_date(report.generated_at)
    top_matches = _get_top_matches(report.scored_postings)
    review_needed = _get_review_needed(report.scored_postings)

    return (
        f"Job Radar Report - {report_date} - "
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
    top_matches = _get_top_matches(report.scored_postings)
    review_needed = _get_review_needed(report.scored_postings)

    lines: list[str] = [
        f"Generated at: {_format_generated_at(report.generated_at)}",
        f"Companies enabled: {report.companies_enabled}",
        f"Jobs collected: {report.jobs_collected}",
        _format_optional_count_line("Jobs stored", report.jobs_stored),
        _format_optional_count_line("Jobs omitted", report.jobs_omitted),
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
        "",
        f"Top Matches, up to {TOP_MATCHES_LIMIT}:",
    ]

    _append_email_posting_lines(
        lines=lines,
        scored_postings=top_matches,
        section_type="top_match",
    )

    lines.extend(
        [
            "",
            f"Review Needed, up to {TOP_MATCHES_LIMIT}:",
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
        lines.append("Attached as Markdown file.")

    return "\n".join(lines)

def build_email_html_body(
    report: ScanReport,
    report_path: str | Path,
    include_report_path: bool = True,
) -> str:
    top_matches = _get_top_matches(report.scored_postings)
    review_needed = _get_review_needed(report.scored_postings)

    lines: list[str] = [
        "<!doctype html>",
        "<html>",
        "<body>",
        "<h1>Job Radar Report</h1>",
        "<h2>Summary</h2>",
        "<ul>",
        f"<li><strong>Generated at:</strong> "
        f"{escape(_format_generated_at(report.generated_at))}</li>",
        f"<li><strong>Companies enabled:</strong> {report.companies_enabled}</li>",
        f"<li><strong>Jobs collected:</strong> {report.jobs_collected}</li>",
        f"<li><strong>Jobs stored:</strong> "
        f"{_format_optional_count(report.jobs_stored)}</li>",
        f"<li><strong>Jobs omitted:</strong> "
        f"{_format_optional_count(report.jobs_omitted)}</li>",
        f"<li><strong>New jobs:</strong> {report.jobs_new}</li>",
        f"<li><strong>Seen jobs:</strong> {report.jobs_seen}</li>",
        f"<li><strong>Changed jobs:</strong> {report.jobs_changed}</li>",
        f"<li><strong>Collector errors:</strong> {len(report.collector_errors)}</li>",
        f"<li><strong>Top match score threshold:</strong> "
        f"{_format_optional_count(report.top_match_min_score)}</li>",
        f"<li><strong>Review-needed score threshold:</strong> "
        f"{_format_optional_count(report.review_needed_min_score)}</li>",
        "</ul>",
    ]

    _append_html_posting_section(
        lines=lines,
        heading=f"Top Matches, up to {TOP_MATCHES_LIMIT}",
        scored_postings=top_matches,
        section_type="top_match",
    )

    _append_html_posting_section(
        lines=lines,
        heading=f"Review Needed, up to {TOP_MATCHES_LIMIT}",
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
        lines.append("<p>Attached as Markdown file.</p>")

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
    report_path: str | Path,
) -> Path:
    preview_path = Path(path)
    preview_path.parent.mkdir(parents=True, exist_ok=True)

    subject = build_email_subject(report)
    body = build_email_body(report, report_path)

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


def _get_top_matches(
    scored_postings: list[ScoredPosting] | None,
) -> list[ScoredPosting]:
    if scored_postings is None:
        return []

    return [
        scored_posting
        for scored_posting in scored_postings
        if scored_posting.top_match_eligible
    ][:TOP_MATCHES_LIMIT]


def _get_review_needed(
    scored_postings: list[ScoredPosting] | None,
) -> list[ScoredPosting]:
    if scored_postings is None:
        return []

    return [
        scored_posting
        for scored_posting in scored_postings
        if scored_posting.review_needed_eligible
    ][:TOP_MATCHES_LIMIT]


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
    posting = scored_posting.posting

    lines.extend(
        [
            f"{index}. {_format_value(posting.title)}",
            f"   Company: {_format_value(posting.company_name)}",
            f"   Score: {scored_posting.score}",
            f"   Location: {_format_value(posting.location)}",
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


def _get_top_match_reasons(scored_posting: ScoredPosting) -> list[str]:
    if scored_posting.top_match_reasons:
        return scored_posting.top_match_reasons

    return [
        "marked eligible by top-match scoring rules",
        f"location status: {scored_posting.location_status or 'unknown'}",
    ]


def _get_review_needed_reasons(scored_posting: ScoredPosting) -> list[str]:
    return [
        "marked eligible by review-needed scoring rules",
        f"location status: {scored_posting.location_status or 'unknown'}",
    ]


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
    posting = scored_posting.posting

    lines.extend(
        [
            "<section>",
            f"<h3>{escape(_format_value(posting.title))}</h3>",
            "<ul>",
            f"<li><strong>Company:</strong> "
            f"{escape(_format_value(posting.company_name))}</li>",
            f"<li><strong>Score:</strong> {scored_posting.score}</li>",
            f"<li><strong>Location:</strong> "
            f"{escape(_format_value(posting.location))}</li>",
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

    if posting.source_url:
        lines.append(
            f'<p><a href="{escape(posting.source_url, quote=True)}">'
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


def _format_value(value: str | None) -> str:
    if not value:
        return "Unknown"

    return value


def _plural_suffix(count: int) -> str:
    if count == 1:
        return ""

    return "es"