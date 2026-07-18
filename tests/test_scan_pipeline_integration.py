"""Tests the complete scan pipeline with synthetic jobs and a temporary database."""

import json
import sqlite3
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


def write_scan_test_files(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path, Path]:
    config_file = tmp_path / "companies.yaml"
    settings_file = tmp_path / "settings.yaml"
    scoring_file = tmp_path / "scoring.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    report_file = tmp_path / "today.html"

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

top_matches:
  min_score: 1
  excluded_title_keywords: []
  strong_signals:
    - title:infrastructure
""",
        encoding="utf-8",
    )

    return config_file, settings_file, database_file, report_file, scoring_file


def count_job_postings(database_file: Path) -> int:
    with sqlite3.connect(database_file) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM job_postings"
        ).fetchone()

    assert row is not None
    return int(row[0])


def read_snapshot(report_file: Path) -> dict:
    snapshot_file = report_file.with_suffix(".json")
    return json.loads(snapshot_file.read_text(encoding="utf-8"))


def test_scan_pipeline_tracks_new_then_seen(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config_file, settings_file, database_file, report_file, scoring_file = (
        write_scan_test_files(tmp_path)
    )

    fake_posting = make_fake_posting()

    monkeypatch.setattr(
        "job_radar.scan_service.collect_jobs_for_company",
        lambda company_config: [fake_posting],
    )

    handle_scan(
        config_path=str(config_file),
        settings_path=str(settings_file),
        report_path=str(report_file),
        scoring_path=str(scoring_file),
    )

    first_output = capsys.readouterr().out
    first_snapshot = read_snapshot(report_file)
    first_html = report_file.read_text(encoding="utf-8")

    assert database_file.exists()
    assert count_job_postings(database_file) == 1
    assert report_file.exists()
    assert report_file.with_suffix(".json").exists()
    assert not report_file.with_suffix(".md").exists()

    assert "Jobs collected: 1" in first_output
    assert "Actionable jobs stored: 1" in first_output
    assert "Jobs not actionable: 0" in first_output
    assert "Jobs new: 1" in first_output
    assert "Jobs seen: 0" in first_output
    assert "Jobs changed: 0" in first_output

    assert first_snapshot["summary"]["new_jobs"] == 1
    assert len(first_snapshot["top_matches"]) == 1
    assert len(first_snapshot["new_jobs"]) == 1
    assert first_snapshot["top_matches"][0]["title"] == (
        "Senior Infrastructure Engineer"
    )
    assert first_snapshot["top_matches"][0]["why_matched"] == (
        "infrastructure, linux, remote"
    )
    assert first_snapshot["new_jobs"][0]["url"] == (
        "https://boards.greenhouse.io/exampleai/jobs/123"
    )

    assert "<h1>Job Radar Report</h1>" in first_html
    assert "<h2>Top Matches</h2>" in first_html
    assert "Senior Infrastructure Engineer" in first_html

    handle_scan(
        config_path=str(config_file),
        settings_path=str(settings_file),
        report_path=str(report_file),
        scoring_path=str(scoring_file),
    )

    second_output = capsys.readouterr().out
    second_snapshot = read_snapshot(report_file)
    second_html = report_file.read_text(encoding="utf-8")

    assert count_job_postings(database_file) == 1
    assert "Jobs collected: 1" in second_output
    assert "Actionable jobs stored: 1" in second_output
    assert "Jobs not actionable: 0" in second_output
    assert "Jobs new: 0" in second_output
    assert "Jobs seen: 1" in second_output
    assert "Jobs changed: 0" in second_output

    assert second_snapshot["summary"]["new_jobs"] == 0
    assert len(second_snapshot["top_matches"]) == 1
    assert second_snapshot["new_jobs"] == []
    assert second_snapshot["top_matches"][0]["title"] == (
        "Senior Infrastructure Engineer"
    )
    assert second_snapshot["top_matches"][0]["why_matched"] == (
        "infrastructure, linux, remote"
    )

    assert "<h1>Job Radar Report</h1>" in second_html
    assert "<h2>Top Matches</h2>" in second_html
    assert "Senior Infrastructure Engineer" in second_html
