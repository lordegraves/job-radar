from datetime import datetime
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
        f"New jobs: {report.jobs_new}",
        f"Seen jobs: {report.jobs_seen}",
        f"Changed jobs: {report.jobs_changed}",
        f"Collector errors: {len(report.collector_errors)}",
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
            f"   URL: {_format_value(posting.source_url)}",
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

    _append_reason_lines(
        lines=lines,
        heading="Why it scored:",
        reasons=scored_posting.score_reasons,
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


def _format_value(value: str | None) -> str:
    if not value:
        return "Unknown"

    return value


def _plural_suffix(count: int) -> str:
    if count == 1:
        return ""

    return "es"