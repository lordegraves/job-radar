from pathlib import Path

from job_radar.cli import handle_scan
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


def test_handle_scan_collects_stores_scores_and_reports_jobs(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config_file = tmp_path / "companies.yaml"
    settings_file = tmp_path / "settings.yaml"
    scoring_file = tmp_path / "scoring.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    report_file = tmp_path / "today.md"

    config_file.write_text(
        """
companies:
  - company_key: example_ai
    name: Example AI
    source_type: greenhouse
    source_slug: exampleai
    enabled: true
""",
        encoding="utf-8",
    )

    settings_file.write_text(
        f"""
database_path: {database_file}
reports_path: {tmp_path}
logs_path: {tmp_path}

retention:
  report_retention_days: 90
  routine_event_retention_days: 90
  log_max_mb: 5
  log_backup_count: 5
  raw_capture_enabled: false
  raw_capture_retention_days: 7
""",
        encoding="utf-8",
    )

    scoring_file.write_text(
        """
positive_keywords:
  infrastructure: 10
  linux: 10

negative_keywords:
  sales: -10

location_preferences:
  allowed:
    remote: 100
  conditional: {}
  skipped: {}
""",
        encoding="utf-8",
    )

    canonical_key = make_canonical_key(
        company_key="example_ai",
        title="Senior Infrastructure Engineer",
        location="Remote",
    )

    content_hash = make_content_hash(
        title="Senior Infrastructure Engineer",
        location="Remote",
        description="Build Linux infrastructure.",
    )

    fake_posting = JobPosting(
        company_key="example_ai",
        company_name="Example AI",
        source_type="greenhouse",
        source_job_id="123",
        source_url="https://boards.greenhouse.io/exampleai/jobs/123",
        title="Senior Infrastructure Engineer",
        location="Remote",
        description="Build Linux infrastructure.",
        canonical_key=canonical_key,
        content_hash=content_hash,
    )

    def fake_collect_jobs_for_company(company_config):
        return [fake_posting]

    monkeypatch.setattr(
        "job_radar.cli.collect_jobs_for_company",
        fake_collect_jobs_for_company,
    )

    handle_scan(
        config_path=str(config_file),
        settings_path=str(settings_file),
        report_path=str(report_file),
        scoring_path=str(scoring_file),
    )

    output = capsys.readouterr().out
    report_text = report_file.read_text(encoding="utf-8")

    assert database_file.exists()
    assert report_file.exists()

    assert "Scan requested" in output
    assert "Companies enabled: 1" in output
    assert "Jobs collected: 1" in output
    assert "Jobs new: 1" in output
    assert "Jobs seen: 0" in output
    assert "Jobs changed: 0" in output
    assert "Collector errors: 0" in output

    assert "# Job Radar Report" in report_text
    assert "- Companies enabled: 1" in report_text
    assert "- Jobs collected: 1" in report_text
    assert "- New jobs: 1" in report_text
    assert "- Seen jobs: 0" in report_text
    assert "- Changed jobs: 0" in report_text
    assert "- Collector errors: 0" in report_text

    assert "## Top Matches" in report_text
    assert "## All Jobs" in report_text
    assert (
        "### [Senior Infrastructure Engineer]"
        "(https://boards.greenhouse.io/exampleai/jobs/123)"
        in report_text
    )

    assert "- Score: 140" in report_text
    assert "+30 title:infrastructure" in report_text
    assert "+10 body:linux" in report_text
    assert "+100 location_allowed:remote" in report_text
    assert "- Location status: allowed" in report_text

    assert "- Company: Example AI" in report_text
    assert "- Source: greenhouse" in report_text
    assert "- Location: Remote" in report_text
    assert "- URL: https://boards.greenhouse.io/exampleai/jobs/123" in report_text
    assert "- Canonical key: `example-ai:senior-infrastructure-engineer:remote`" in report_text