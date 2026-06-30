from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path

from job_radar.models import JobPosting


TOP_MATCHES_QUICK_VIEW_LIMIT = 10
NORTHERN_COLORADO_HIGHLIGHTS_LIMIT = 10
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
    top_match_min_score: int | None = None
    review_needed_min_score: int | None = None
    jobs_stored: int | None = None
    jobs_omitted: int | None = None


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
        lines.append(f"- Jobs stored: {report.jobs_stored}")

    if report.jobs_omitted is not None:
        lines.append(f"- Jobs omitted: {report.jobs_omitted}")

    if report.top_match_min_score is not None:
        lines.append(f"- Top match score threshold: {report.top_match_min_score}")

    if report.review_needed_min_score is not None:
        lines.append(
            f"- Review-needed score threshold: {report.review_needed_min_score}"
        )

    _append_companies_scanned_summary(lines, report.postings)
    _append_source_type_summary(lines, report.postings)

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
        lines.append(f"<li><strong>Jobs stored:</strong> {report.jobs_stored}</li>")

    if report.jobs_omitted is not None:
        lines.append(f"<li><strong>Jobs omitted:</strong> {report.jobs_omitted}</li>")

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

    if report.scored_postings is not None:
        _append_html_location_status_summary(lines, report.scored_postings)

    lines.append("</ul>")

    if report.collector_errors:
        _append_html_collector_errors(lines, report.collector_errors)

    if report.scored_postings is not None:
        _append_html_scored_sections(lines, report.scored_postings)
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
    _append_northern_colorado_highlights_section(lines, scored_postings)
    _append_review_needed_section(lines, scored_postings)
    _append_omitted_jobs_section(lines, scored_postings)


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


def _get_review_needed(
    scored_postings: list[ScoredPosting],
) -> list[ScoredPosting]:
    return [
        scored_posting
        for scored_posting in scored_postings
        if scored_posting.review_needed_eligible
        and _is_actionable_posting(scored_posting)
    ]


def _append_omitted_jobs_section(
    lines: list[str],
    scored_postings: list[ScoredPosting],
) -> None:
    omitted_count = len(
        [
            scored_posting
            for scored_posting in scored_postings
            if (
                not scored_posting.top_match_eligible
                and not scored_posting.review_needed_eligible
            )
            or not _is_actionable_posting(scored_posting)
        ]
    )

    lines.extend(
        [
            "## Omitted Jobs",
            "",
        ]
    )

    if omitted_count == 0:
        lines.extend(
            [
                "No scored jobs were omitted from the detailed report.",
                "",
            ]
        )
        return

    lines.extend(
        [
            (
                f"{omitted_count} scored jobs were omitted because they did not "
                "qualify as actionable Top Match or Review Needed roles."
            ),
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
                f"  - Status: {scored_posting.location_status}",
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
            f"- Hiring probability: {_get_hiring_probability_label(scored_posting)}",
            f"- Recommended action: {_get_recommended_action(scored_posting)}",
            f"- Hiring risks: {_format_hiring_risk_flags(scored_posting)}",
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


def _get_technical_match_label(scored_posting: ScoredPosting) -> str:
    title_text = _get_title_text(scored_posting)
    positive_labels = _get_positive_score_labels(scored_posting.score_reasons)

    if _has_any_title_keyword(
        title_text,
        [
            "frontend",
            "full stack",
            "product manager",
            "program manager",
            "project manager",
            "account manager",
            "business development",
            "developer advocate",
            "compliance",
            "facilities",
            "sourcing",
            "engineering manager",
            "technical program manager",
            "technical project manager",
            "technical product manager",
            "product",
            "partnership",
            "delivery lead",
            "enterprise applications",
            "forward deployed",
        ],
    ):
        return "Weak"

    strong_signal_count = _count_matching_labels(
        positive_labels,
        [
            "hpc",
            "linux",
            "slurm",
            "gpu",
            "cluster",
            "datacenter",
            "data center",
            "infrastructure",
            "site reliability",
            "sre",
            "storage",
            "hardware",
        ],
    )

    if strong_signal_count >= 4:
        return "Very Strong"

    if strong_signal_count >= 2:
        return "Strong"

    if strong_signal_count >= 1:
        return "Moderate"

    return "Weak"


def _get_hiring_probability_label(scored_posting: ScoredPosting) -> str:
    risks = _get_hiring_risk_flags(scored_posting)
    technical_match = _get_technical_match_label(scored_posting)

    if "hard location mismatch" in risks:
        return "Very Low"

    if "role family mismatch" in risks or "support role" in risks:
        return "Low"

    if (
        "software-heavy translation risk" in risks
        or "generic remote competition" in risks
        or "production Kubernetes translation risk" in risks
    ):
        if technical_match in {"Very Strong", "Strong"}:
            return "Medium"
        return "Low"

    if technical_match == "Very Strong":
        return "High"

    if technical_match == "Strong":
        return "Medium"

    if technical_match == "Moderate":
        return "Low"

    return "Very Low"


def _get_recommended_action(scored_posting: ScoredPosting) -> str:
    hiring_probability = _get_hiring_probability_label(scored_posting)
    technical_match = _get_technical_match_label(scored_posting)
    risks = _get_hiring_risk_flags(scored_posting)

    if "hard location mismatch" in risks:
        return "Pass"

    if "role family mismatch" in risks or "support role" in risks:
        return "Pass"

    if hiring_probability in {"High", "Medium"} and technical_match == "Very Strong":
        if risks:
            return "Apply + Recruiter Message"
        return "Apply"

    if hiring_probability == "Medium" and technical_match == "Strong":
        return "Tailor Resume"

    if (
        technical_match in {"Very Strong", "Strong"}
        and (
            "generic remote competition" in risks
            or "software-heavy translation risk" in risks
        )
    ):
        return "Network First"

    if hiring_probability == "Low":
        return "Hold"

    return "Pass"


def _is_actionable_posting(scored_posting: ScoredPosting) -> bool:
    return _get_recommended_action(scored_posting) != "Pass"


def _format_hiring_risk_flags(scored_posting: ScoredPosting) -> str:
    risks = _get_hiring_risk_flags(scored_posting)

    if not risks:
        return "None"

    return "; ".join(risks)


def _get_hiring_risk_flags(scored_posting: ScoredPosting) -> list[str]:
    title_text = _get_title_text(scored_posting)
    location_text = (scored_posting.posting.location or "").lower()
    positive_labels = _get_positive_score_labels(scored_posting.score_reasons)
    risks: list[str] = []

    if scored_posting.location_status == "skipped":
        risks.append("hard location mismatch")
    elif _has_any_location_keyword(
        location_text,
        [
            "apac",
            "emea",
            "europe",
            "eu",
            "netherlands",
            "amsterdam",
            "germany",
            "france",
            "uk",
            "united kingdom",
            "singapore",
            "australia",
        ],
    ):
        risks.append("hard location mismatch")
    elif scored_posting.location_status in {"mixed", "conditional", "unknown"}:
        risks.append("location needs confirmation")

    if _has_any_title_keyword(
        title_text,
        [
            "frontend",
            "full stack",
            "product manager",
            "program manager",
            "project manager",
            "account manager",
            "business development",
            "developer advocate",
            "compliance",
            "sourcing",
            "engineering manager",
            "technical program manager",
            "technical project manager",
            "technical product manager",
            "product",
            "partnership",
            "delivery lead",
            "facilities",
            "enterprise applications",
            "forward deployed",
        ],
    ):
        risks.append("role family mismatch")

    if _has_any_title_keyword(title_text, ["support", "technical support", "analyst"]):
        risks.append("support role")

    if _has_any_title_keyword(
        title_text,
        ["software engineer", "frontend", "full stack", "platform engineer"],
    ):
        risks.append("software-heavy translation risk")

    if "kubernetes" in positive_labels or "k8s" in positive_labels:
        risks.append("production Kubernetes translation risk")

    if (
        scored_posting.location_status == "allowed"
        and "remote" in positive_labels
        and _get_technical_match_label(scored_posting) != "Very Strong"
    ):
        risks.append("generic remote competition")

    return _dedupe_preserving_order(risks)


def _get_title_text(scored_posting: ScoredPosting) -> str:
    return (scored_posting.posting.title or "").lower()


def _get_positive_score_labels(score_reasons: list[str]) -> list[str]:
    labels: list[str] = []

    for reason in score_reasons:
        if not reason.startswith("+"):
            continue

        if ":" not in reason:
            continue

        label = reason.split(":", maxsplit=1)[1].strip().lower()

        if label:
            labels.append(label)

    return _dedupe_preserving_order(labels)


def _has_any_title_keyword(title_text: str, keywords: list[str]) -> bool:
    return any(keyword in title_text for keyword in keywords)


def _has_any_location_keyword(location_text: str, keywords: list[str]) -> bool:
    return any(keyword in location_text for keyword in keywords)


def _count_matching_labels(labels: list[str], keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if keyword in labels)


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    deduped_values: list[str] = []

    for value in values:
        if value not in deduped_values:
            deduped_values.append(value)

    return deduped_values


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
        if scored_posting.top_match_eligible
        and _is_actionable_posting(scored_posting)
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
        lines.append(f"<li>{escape(label)}: {counts[label]}</li>")

    lines.append("</ul></li>")


def _append_html_location_status_summary(
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

    lines.append("<li><strong>Location statuses:</strong><ul>")

    for location_status in preferred_order:
        if location_status in status_counts:
            lines.append(
                f"<li>{escape(location_status)}: "
                f"{status_counts[location_status]}</li>"
            )

    for location_status in sorted(status_counts):
        if location_status not in preferred_order:
            lines.append(
                f"<li>{escape(location_status)}: "
                f"{status_counts[location_status]}</li>"
            )

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
) -> None:
    _append_html_top_matches_section(lines, scored_postings)
    _append_html_northern_colorado_highlights_section(lines, scored_postings)
    _append_html_review_needed_section(lines, scored_postings)
    _append_html_omitted_jobs_section(lines, scored_postings)


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
            f"<br>Status: {escape(scored_posting.location_status)}"
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
    omitted_count = len(
        [
            scored_posting
            for scored_posting in scored_postings
            if (
                not scored_posting.top_match_eligible
                and not scored_posting.review_needed_eligible
            )
            or not _is_actionable_posting(scored_posting)
        ]
    )

    lines.append("<h2>Omitted Jobs</h2>")

    if omitted_count == 0:
        lines.append("<p>No scored jobs were omitted from the detailed report.</p>")
        return

    lines.append(
        "<p>"
        f"{omitted_count} scored jobs were omitted because they did not "
        "qualify as actionable Top Match or Review Needed roles."
        "</p>"
    )


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

    if scored_posting.top_match_eligible:
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
            f"<li><strong>Hiring risks:</strong> "
            f"{escape(_format_hiring_risk_flags(scored_posting))}</li>",
            f"<li><strong>Score reasons:</strong> "
            f"{escape(_format_score_reasons(scored_posting.score_reasons))}</li>",
            f"<li><strong>Location status:</strong> "
            f"{escape(scored_posting.location_status)}</li>",
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