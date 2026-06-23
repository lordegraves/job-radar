from pathlib import Path

from job_radar.models import JobPosting
from job_radar.reporting import (
    ScanError,
    ScanReport,
    ScoredPosting,
    render_markdown_report,
    write_markdown_report,
)


def make_posting(title: str = "Senior Infrastructure Engineer") -> JobPosting:
    return JobPosting(
        company_key="example_ai",
        company_name="Example AI",
        source_type="greenhouse",
        source_job_id="123",
        source_url="https://boards.greenhouse.io/exampleai/jobs/123",
        title=title,
        location="Remote",
        description="Build Linux infrastructure.",
        canonical_key="example_ai:senior-infrastructure-engineer:remote",
        content_hash="hash",
    )


def test_render_markdown_report_includes_summary() -> None:
    report = ScanReport(
        companies_enabled=1,
        jobs_collected=1,
        jobs_new=1,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[make_posting()],
    )

    markdown = render_markdown_report(report)

    assert "# Job Radar Report" in markdown
    assert "- Companies enabled: 1" in markdown
    assert "- Jobs collected: 1" in markdown
    assert "- New jobs: 1" in markdown
    assert "- Seen jobs: 0" in markdown
    assert "- Changed jobs: 0" in markdown
    assert "- Collector errors: 0" in markdown


def test_render_markdown_report_includes_collector_errors() -> None:
    report = ScanReport(
        companies_enabled=1,
        jobs_collected=0,
        jobs_new=0,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[
            ScanError(
                company_key="example_ai",
                company_name="Example AI",
                source_type="greenhouse",
                message="Failed to fetch Greenhouse jobs",
            )
        ],
        postings=[],
    )

    markdown = render_markdown_report(report)

    assert "## Collector Errors" in markdown
    assert (
        "- example_ai (Example AI, greenhouse): Failed to fetch Greenhouse jobs"
        in markdown
    )


def test_render_markdown_report_includes_jobs() -> None:
    report = ScanReport(
        companies_enabled=1,
        jobs_collected=1,
        jobs_new=1,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[make_posting()],
    )

    markdown = render_markdown_report(report)

    assert "## Jobs" in markdown
    assert (
        "### [Senior Infrastructure Engineer]"
        "(https://boards.greenhouse.io/exampleai/jobs/123)"
        in markdown
    )
    assert "- Company: Example AI" in markdown
    assert "- Source: greenhouse" in markdown
    assert "- Location: Remote" in markdown
    assert "- URL: https://boards.greenhouse.io/exampleai/jobs/123" in markdown
    assert (
        "- Canonical key: `example_ai:senior-infrastructure-engineer:remote`"
        in markdown
    )

def test_render_markdown_report_handles_no_jobs() -> None:
    report = ScanReport(
        companies_enabled=1,
        jobs_collected=0,
        jobs_new=0,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[],
    )

    markdown = render_markdown_report(report)

    assert "No jobs were collected during this scan." in markdown


def test_write_markdown_report_writes_file(tmp_path: Path) -> None:
    report_path = tmp_path / "today.md"
    report = ScanReport(
        companies_enabled=1,
        jobs_collected=1,
        jobs_new=1,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[make_posting()],
    )

    written_path = write_markdown_report(report_path, report)

    assert written_path == report_path
    assert report_path.exists()
    assert "# Job Radar Report" in report_path.read_text(encoding="utf-8")


def test_render_markdown_report_includes_score_and_score_reasons() -> None:
    posting = make_posting(title="Senior Linux Infrastructure Engineer")

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=1,
        jobs_new=1,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[posting],
        scored_postings=[
            ScoredPosting(
                posting=posting,
                score=28,
                score_reasons=[
                    "+10 linux",
                    "+10 infrastructure",
                    "+8 kubernetes",
                ],
            )
        ],
    )

    markdown = render_markdown_report(report)

    assert "- Score: 28" in markdown
    assert "- Score reasons: +10 linux, +10 infrastructure, +8 kubernetes" in markdown