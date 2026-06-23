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


def render_markdown_report(report: ScanReport) -> str:
    lines = [
        "# Job Radar Report",
        "",
        "## Summary",
        "",
        f"- Companies enabled: {report.companies_enabled}",
        f"- Jobs collected: {report.jobs_collected}",
        f"- New jobs: {report.jobs_new}",
        f"- Seen jobs: {report.jobs_seen}",
        f"- Changed jobs: {report.jobs_changed}",
        f"- Collector errors: {len(report.collector_errors)}",
        "",
    ]

    if report.collector_errors:
        lines.extend(
            [
                "## Collector Errors",
                "",
            ]
        )

        for error in report.collector_errors:
            lines.append(
                f"- {error.company_key} ({error.company_name}, {error.source_type}): "
                f"{error.message}"
            )

        lines.append("")

    if report.scored_postings is not None:
        if not report.scored_postings:
            lines.extend(
                [
                    "## Top Matches",
                    "",
                    "No jobs were collected during this scan.",
                    "",
                    "## All Jobs",
                    "",
                    "No jobs were collected during this scan.",
                    "",
                ]
            )
            return "\n".join(lines)

        top_matches = _get_top_matches(report.scored_postings)

        lines.extend(
            [
                "## Top Matches",
                "",
            ]
        )

        for scored_posting in top_matches:
            _append_scored_posting(lines, scored_posting)

        lines.extend(
            [
                "## All Jobs",
                "",
            ]
        )

        for scored_posting in report.scored_postings:
            _append_scored_posting(lines, scored_posting)

        return "\n".join(lines)

    lines.extend(
        [
            "## Jobs",
            "",
        ]
    )

    if not report.postings:
        lines.append("No jobs were collected during this scan.")
        lines.append("")
        return "\n".join(lines)

    for posting in report.postings:
        _append_posting(lines, posting)

    return "\n".join(lines)


def _append_scored_posting(lines: list[str], scored_posting: ScoredPosting) -> None:
    posting = scored_posting.posting

    lines.extend(
        [
            f"### [{posting.title}]({posting.source_url})",
            "",
            f"- Score: {scored_posting.score}",
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


def _format_score_reasons(score_reasons: list[str]) -> str:
    if not score_reasons:
        return "None"

    return ", ".join(score_reasons)

def _get_top_matches(scored_postings: list[ScoredPosting]) -> list[ScoredPosting]:
    eligible_postings = [
        scored_posting
        for scored_posting in scored_postings
        if _is_top_match_eligible(scored_posting)
    ]

    return eligible_postings[:TOP_MATCHES_LIMIT]


def _is_top_match_eligible(scored_posting: ScoredPosting) -> bool:
    if scored_posting.location_status != "allowed":
        return False

    if scored_posting.score <= 0:
        return False

    if _has_negative_title_match(scored_posting):
        return False

    if _has_excluded_title_keyword(scored_posting):
        return False

    if not _has_strong_technical_signal(scored_posting):
        return False

    return True

def _has_negative_title_match(scored_posting: ScoredPosting) -> bool:
    for reason in scored_posting.score_reasons:
        if reason.startswith("-") and "title:" in reason:
            return True

    return False


def _has_excluded_title_keyword(scored_posting: ScoredPosting) -> bool:
    excluded_title_keywords = [
        "account executive",
        "business",
        "communications",
        "customer success",
        "finance",
        "fx",
        "gtm",
        "investments",
        "legal",
        "liquidity",
        "marketing",
        "people",
        "product manager",
        "recruiter",
        "recruiting",
        "sales",
        "sourcing",
    ]

    title = scored_posting.posting.title.lower()

    for keyword in excluded_title_keywords:
        if keyword in title:
            return True

    return False


def _has_strong_technical_signal(scored_posting: ScoredPosting) -> bool:
    strong_signals = [
        "title:infrastructure",
        "title:kubernetes",
        "title:linux",
        "title:cluster",
        "title:datacenter",
        "title:data center",
        "title:reliability",
        "title:sre",
        "body:hpc",
        "body:slurm",
        "body:gpu",
        "body:kubernetes",
        "body:linux",
        "body:infrastructure",
        "body:datacenter",
        "body:data center",
        "body:hardware",
    ]

    for reason in scored_posting.score_reasons:
        for signal in strong_signals:
            if signal in reason:
                return True

    return False

def write_markdown_report(report_path: str | Path, report: ScanReport) -> Path:
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown_report(report), encoding="utf-8")
    return path