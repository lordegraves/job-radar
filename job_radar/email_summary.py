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


def build_email_body(report: ScanReport, report_path: str | Path) -> str:
    top_matches = _get_top_matches(report.scored_postings)
    review_needed = _get_review_needed(report.scored_postings)

    lines: list[str] = [
        f"Generated at: {report.generated_at or 'Unknown'}",
        f"Companies enabled: {report.companies_enabled}",
        f"Jobs collected: {report.jobs_collected}",
        f"New jobs: {report.jobs_new}",
        f"Seen jobs: {report.jobs_seen}",
        f"Changed jobs: {report.jobs_changed}",
        f"Collector errors: {len(report.collector_errors)}",
        "",
        "Top Matches:",
    ]

    _append_email_posting_lines(lines, top_matches)

    lines.extend(
        [
            "",
            "Review Needed:",
        ]
    )

    _append_email_posting_lines(lines, review_needed)

    lines.extend(
        [
            "",
            "Full report:",
            str(report_path),
        ]
    )

    return "\n".join(lines)


def _get_report_date(generated_at: str | None) -> str:
    if not generated_at:
        return "unknown-date"

    return generated_at.split("T", maxsplit=1)[0]


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
    ]


def _append_email_posting_lines(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    if not scored_postings:
        lines.append("- None")
        return

    for scored_posting in scored_postings:
        posting = scored_posting.posting
        lines.append(
            f"- {posting.title} - {posting.company_name} - {scored_posting.score}"
        )


def _plural_suffix(count: int) -> str:
    if count == 1:
        return ""

    return "es"