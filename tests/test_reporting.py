from pathlib import Path

from job_radar.models import JobPosting
from job_radar.reporting import (
    ScanError,
    ScanReport,
    render_markdown_report,
    write_markdown_report,
)


def test_render_markdown_report_includes_summary() -> None:
    report = ScanReport(
        companies_enabled=2,
        jobs_collected=0,
        jobs_new=0,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[],
    )

    markdown = render_markdown_report(report)

    assert "# Job Radar Report" in markdown
    assert "- Companies enabled: 2" in markdown
    assert "- Jobs collected: 0" in markdown
    assert "- New jobs: 0" in markdown
    assert "- Seen jobs: 0" in markdown
    assert "- Changed jobs: 0" in markdown
    assert "- Collector errors: 0" in markdown
    assert "No jobs were collected during this scan." in markdown


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
    assert "example_ai" in markdown
    assert "Failed to fetch Greenhouse jobs" in markdown


def test_render_markdown_report_includes_jobs() -> None:
    posting = JobPosting(
        company_key="example_ai",
        company_name="Example AI",
        source_type="greenhouse",
        source_job_id="123",
        source_url="https://boards.greenhouse.io/exampleai/jobs/123",
        title="Senior Infrastructure Engineer",
        location="Remote",
        description="Build Linux infrastructure.",
        canonical_key="example-ai:senior-infrastructure-engineer:remote",
        content_hash="abc123",
    )

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=1,
        jobs_new=1,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[posting],
    )

    markdown = render_markdown_report(report)

    assert "## Jobs" in markdown
    assert "### Senior Infrastructure Engineer" in markdown
    assert "- Company: Example AI" in markdown
    assert "- Source: greenhouse" in markdown
    assert "- Location: Remote" in markdown
    assert "- URL: https://boards.greenhouse.io/exampleai/jobs/123" in markdown


def test_write_markdown_report_creates_file(tmp_path: Path) -> None:
    report_path = tmp_path / "today.md"

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=0,
        jobs_new=0,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[],
    )

    result = write_markdown_report(report_path, report)

    assert result == report_path
    assert report_path.exists()
    assert "# Job Radar Report" in report_path.read_text(encoding="utf-8")