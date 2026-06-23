from dataclasses import dataclass
from pathlib import Path

from job_radar.models import JobPosting


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


def render_markdown_report(report: ScanReport) -> str:
    lines: list[str] = []

    lines.append("# Job Radar Report")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Companies enabled: {report.companies_enabled}")
    lines.append(f"- Jobs collected: {report.jobs_collected}")
    lines.append(f"- New jobs: {report.jobs_new}")
    lines.append(f"- Seen jobs: {report.jobs_seen}")
    lines.append(f"- Changed jobs: {report.jobs_changed}")
    lines.append(f"- Collector errors: {len(report.collector_errors)}")
    lines.append("")

    if report.collector_errors:
        lines.append("## Collector Errors")
        lines.append("")

        for error in report.collector_errors:
            lines.append(
                f"- {error.company_key} ({error.company_name}, {error.source_type}): "
                f"{error.message}"
            )

        lines.append("")

    if report.postings:
        lines.append("## Jobs")
        lines.append("")

        for posting in report.postings:
            lines.append(f"### {posting.title}")
            lines.append("")
            lines.append(f"- Company: {posting.company_name}")
            lines.append(f"- Source: {posting.source_type}")
            lines.append(f"- Location: {posting.location or 'Unknown'}")
            lines.append(f"- URL: {posting.source_url}")

            if posting.salary_text:
                lines.append(f"- Salary: {posting.salary_text}")

            lines.append(f"- Canonical key: `{posting.canonical_key}`")
            lines.append("")

    else:
        lines.append("## Jobs")
        lines.append("")
        lines.append("No jobs were collected during this scan.")
        lines.append("")

    return "\n".join(lines)


def write_markdown_report(report_path: str | Path, report: ScanReport) -> Path:
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown_report(report), encoding="utf-8")
    return path