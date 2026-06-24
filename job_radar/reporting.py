from dataclasses import dataclass
from pathlib import Path

from job_radar.models import JobPosting


TOP_MATCHES_LIMIT = 10


@dataclass(frozen=True)
class ScoredPosting:
    posting: JobPosting
    score: int
    score_reasons: list[str]
    location_status: str = "unknown"
    top_match_eligible: bool = False
    top_match_reasons: list[str] | None = None
    review_needed_eligible: bool = False


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
    generated_at: str | None = None


def render_markdown_report(report: ScanReport) -> str:
    lines: list[str] = [
        "# Job Radar Report",
        "",
        "## Summary",
        "",
    ]

    if report.generated_at is not None:
        lines.append(f"- Generated at: {report.generated_at}")

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

    _append_companies_scanned_summary(lines, report.postings)

    if report.scored_postings is not None:
        _append_location_status_summary(lines, report.scored_postings)

    lines.append("")

    if report.collector_errors:
        _append_collector_errors(lines, report.collector_errors)

    if report.scored_postings is not None:
        _append_scored_sections(lines, report.scored_postings)
    else:
        _append_unscored_jobs_section(lines, report.postings)

    return "\n".join(lines).rstrip() + "\n"


def write_markdown_report(report_path: str | Path, report: ScanReport) -> Path:
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown_report(report), encoding="utf-8")
    return path


def _append_companies_scanned_summary(
    lines: list[str],
    postings: list[JobPosting],
) -> None:
    if not postings:
        return

    company_counts: dict[str, int] = {}

    for posting in postings:
        company_name = posting.company_name or "Unknown"
        company_counts[company_name] = company_counts.get(company_name, 0) + 1

    lines.append("- Companies scanned:")

    for company_name in sorted(company_counts):
        lines.append(f"  - {company_name}: {company_counts[company_name]}")


def _append_location_status_summary(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    if not scored_postings:
        return

    status_counts: dict[str, int] = {}

    for scored_posting in scored_postings:
        location_status = scored_posting.location_status or "unknown"
        status_counts[location_status] = status_counts.get(location_status, 0) + 1

    preferred_order = [
        "allowed",
        "allowed_with_travel",
        "mixed",
        "conditional",
        "skipped",
        "unknown",
    ]

    lines.append("- Location statuses:")

    for location_status in preferred_order:
        if location_status in status_counts:
            lines.append(f"  - {location_status}: {status_counts[location_status]}")

    for location_status in sorted(status_counts):
        if location_status not in preferred_order:
            lines.append(f"  - {location_status}: {status_counts[location_status]}")


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
) -> None:
    _append_top_matches_section(lines, scored_postings)
    _append_review_needed_section(lines, scored_postings)
    _append_all_jobs_section(lines, scored_postings)


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

    _append_top_matches_quick_view(lines, top_matches)

    for scored_posting in top_matches:
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


def _get_review_needed(
    scored_postings: list[ScoredPosting],
) -> list[ScoredPosting]:
    return [
        scored_posting
        for scored_posting in scored_postings
        if scored_posting.review_needed_eligible
    ]


def _append_all_jobs_section(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    lines.extend(
        [
            "## All Jobs",
            "",
        ]
    )

    if not scored_postings:
        lines.extend(
            [
                "No jobs were collected during this scan.",
                "",
            ]
        )
        return

    for scored_posting in scored_postings:
        _append_scored_posting(lines, scored_posting)


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
                f"  - Status: {scored_posting.location_status}",
            ]
        )

    lines.append("")


def _append_scored_posting(
    lines: list[str],
    scored_posting: ScoredPosting,
) -> None:
    posting = scored_posting.posting

    lines.extend(
        [
            f"### [{posting.title}]({posting.source_url})",
            "",
            f"- Score: {scored_posting.score}",
            f"- Why this matched: "
            f"{_format_match_summary(scored_posting.score_reasons)}",
            f"- Score reasons: {_format_score_reasons(scored_posting.score_reasons)}",
            f"- Location status: {scored_posting.location_status}",
            f"- Company: {posting.company_name}",
            f"- Source: {posting.source_type}",
            f"- Location: {posting.location or 'Unknown'}",
            f"- URL: {posting.source_url}",
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


def _append_posting(lines: list[str], posting: JobPosting) -> None:
    lines.extend(
        [
            f"### [{posting.title}]({posting.source_url})",
            "",
            f"- Company: {posting.company_name}",
            f"- Source: {posting.source_type}",
            f"- Location: {posting.location or 'Unknown'}",
            f"- URL: {posting.source_url}",
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


def _format_score_reasons(score_reasons: list[str]) -> str:
    if not score_reasons:
        return "None"

    return ", ".join(score_reasons)


def _get_top_matches(scored_postings: list[ScoredPosting]) -> list[ScoredPosting]:
    eligible_postings = [
        scored_posting
        for scored_posting in scored_postings
        if scored_posting.top_match_eligible
    ]

    return eligible_postings[:TOP_MATCHES_LIMIT]