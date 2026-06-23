from pathlib import Path

from job_radar.cli import handle_scan
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


def make_fake_posting() -> JobPosting:
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

    return JobPosting(
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


def write_test_config_files(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    config_file = tmp_path / "companies.yaml"
    settings_file = tmp_path / "settings.yaml"
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

    return config_file, settings_file, database_file, report_file


def test_phase1a_scan_pipeline_tracks_new_then_seen(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config_file, settings_file, database_file, report_file = write_test_config_files(
        tmp_path
    )

    fake_posting = make_fake_posting()

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
    )

    first_output = capsys.readouterr().out
    first_report = report_file.read_text(encoding="utf-8")

    assert database_file.exists()
    assert "Jobs collected: 1" in first_output
    assert "Jobs new: 1" in first_output
    assert "Jobs seen: 0" in first_output
    assert "Jobs changed: 0" in first_output
    assert "- New jobs: 1" in first_report
    assert "- Seen jobs: 0" in first_report
    assert "Senior Infrastructure Engineer" in first_report

    handle_scan(
        config_path=str(config_file),
        settings_path=str(settings_file),
        report_path=str(report_file),
    )

    second_output = capsys.readouterr().out
    second_report = report_file.read_text(encoding="utf-8")

    assert "Jobs collected: 1" in second_output
    assert "Jobs new: 0" in second_output
    assert "Jobs seen: 1" in second_output
    assert "Jobs changed: 0" in second_output
    assert "- New jobs: 0" in second_report
    assert "- Seen jobs: 1" in second_report
    assert "Senior Infrastructure Engineer" in second_report