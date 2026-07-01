import sqlite3
from pathlib import Path

from openpyxl import Workbook

from job_radar.candidate_profile import CandidateProfile
from job_radar.cli import _find_profile_avoid_matches, handle_import_history, handle_scan
from job_radar.job_history import EXPECTED_HEADERS
from job_radar.email_sender import EmailSendResult
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


def count_job_posting_rows(database_file: Path) -> int:
    with sqlite3.connect(database_file) as connection:
        cursor = connection.execute("SELECT COUNT(*) FROM job_postings")
        return int(cursor.fetchone()[0])
    


def count_job_history_rows(database_file: Path) -> int:
    with sqlite3.connect(database_file) as connection:
        cursor = connection.execute("SELECT COUNT(*) FROM job_history")
        return int(cursor.fetchone()[0])


def write_cli_history_workbook(workbook_path: Path) -> None:
    workbook = Workbook()
    pipeline_sheet = workbook.active
    pipeline_sheet.title = "Pipeline Import"
    reviewed_sheet = workbook.create_sheet("Reviewed Import")

    pipeline_sheet.append(EXPECTED_HEADERS)
    reviewed_sheet.append(EXPECTED_HEADERS)

    pipeline_sheet.append(
        [
            "pipeline",
            "Example AI",
            "Senior Infrastructure Engineer",
            "LinkedIn",
            "Greenhouse",
            "Remote",
            "Remote",
            "$160k-$200k",
            "2026-06-01",
            "Rejected - No Interview",
            "Rejected No Interview",
            "Unknown",
            "Very Strong",
            "Low",
            "Linux, HPC, Infrastructure",
            "Generic Remote Competition",
            None,
            "No",
            "Yes",
            "pipeline:example-ai:senior-infrastructure-engineer",
            "Form rejection.",
        ]
    )

    reviewed_sheet.append(
        [
            "reviewed",
            "SkipCo",
            "Frontend Engineer",
            "LinkedIn",
            "Greenhouse",
            "Remote",
            "Remote",
            "$150k-$180k",
            "2026-06-02",
            "Skipped",
            "Skipped",
            None,
            "Weak",
            "Very Low",
            "Frontend",
            "Role Family Mismatch",
            None,
            "No",
            "Yes",
            "reviewed:skipco:frontend-engineer",
            "Not an infrastructure role.",
        ]
    )

    workbook.save(workbook_path)



def test_handle_import_history_imports_workbook_rows(
    tmp_path: Path,
    capsys,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    workbook_file = tmp_path / "job-history.xlsx"
    database_file = tmp_path / "job_radar.sqlite3"

    write_cli_history_workbook(workbook_file)

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

    handle_import_history(
        workbook_path=str(workbook_file),
        settings_path=str(settings_file),
    )

    output = capsys.readouterr().out

    assert database_file.exists()
    assert count_job_history_rows(database_file) == 2

    assert "Application history import complete" in output
    assert f"Workbook: {workbook_file}" in output
    assert f"Database: {database_file}" in output
    assert "Rows read: 2" in output
    assert "Rows imported: 2" in output
    assert "Rows updated: 0" in output
    assert "Rows skipped: 0" in output


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
    html_report_file = tmp_path / "today.html"

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

top_matches:
  min_score: 1
  excluded_title_keywords: []
  strong_signals:
    - title:infrastructure
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
    assert html_report_file.exists()
    assert count_job_posting_rows(database_file) == 1

    assert "Scan requested" in output
    assert "Companies enabled: 1" in output
    assert "Jobs collected: 1" in output
    assert "Jobs stored: 1" in output
    assert "Jobs omitted: 0" in output
    assert "Jobs new: 1" in output
    assert "Jobs seen: 0" in output
    assert "Jobs changed: 0" in output
    assert "Collector errors: 0" in output

    assert "# Job Radar Report" in report_text
    assert "- Companies enabled: 1" in report_text
    assert "- Jobs collected: 1" in report_text
    assert "- Jobs stored: 1" in report_text
    assert "- Jobs omitted: 0" in report_text
    assert "- New jobs: 1" in report_text
    assert "- Seen jobs: 0" in report_text
    assert "- Changed jobs: 0" in report_text
    assert "- Collector errors: 0" in report_text
    assert "- Top match score threshold: 1" in report_text
    assert "- Review-needed score threshold: 100" in report_text

    assert "## Top Matches" in report_text
    assert "## Omitted Jobs" in report_text
    assert "## All Jobs" not in report_text
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


def test_handle_scan_passes_html_report_attachment_to_email_sender(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config_file = tmp_path / "companies.yaml"
    settings_file = tmp_path / "settings.yaml"
    scoring_file = tmp_path / "scoring.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    report_file = tmp_path / "today.md"
    html_report_file = tmp_path / "today.html"

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

email:
  enabled: false
  sender: ""
  sender_name: "Job Radar"
  recipients: []
  smtp_host: ""
  smtp_port: 587
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

    captured_email_call = {}

    def fake_collect_jobs_for_company(company_config):
        return [fake_posting]

    def fake_send_email_report(
        email_settings,
        subject,
        body,
        html_body=None,
        attachment_path=None,
    ):
        captured_email_call["email_settings"] = email_settings
        captured_email_call["subject"] = subject
        captured_email_call["body"] = body
        captured_email_call["html_body"] = html_body
        captured_email_call["attachment_path"] = attachment_path

        return EmailSendResult(
            sent=True,
            message="Email sent",
        )

    monkeypatch.setattr(
        "job_radar.cli.collect_jobs_for_company",
        fake_collect_jobs_for_company,
    )
    monkeypatch.setattr(
        "job_radar.cli.send_email_report",
        fake_send_email_report,
    )

    handle_scan(
        config_path=str(config_file),
        settings_path=str(settings_file),
        report_path=str(report_file),
        scoring_path=str(scoring_file),
        send_email=True,
    )

    output = capsys.readouterr().out

    assert report_file.exists()
    assert html_report_file.exists()
    assert captured_email_call["attachment_path"] == html_report_file
    assert captured_email_call["subject"].startswith("Job Radar Report - ")
    assert "Full report:" in captured_email_call["body"]
    assert "Attached as HTML file." in captured_email_call["body"]
    assert str(report_file) not in captured_email_call["body"]
    assert captured_email_call["html_body"] is not None
    assert "<h1>Job Radar Report</h1>" in captured_email_call["html_body"]
    assert "View posting" in captured_email_call["html_body"]
    assert f"HTML report written: {html_report_file}" in output
    assert "Email send result: Email sent" in output


def test_find_profile_avoid_matches_detects_plain_avoid_terms() -> None:
    profile = CandidateProfile(
        name="Clayton Graves",
        compensation_floor_usd=160000,
        preferred_base_usd=185000,
        resume=None,
        core_strengths=[],
        credible_adjacent=[],
        learning_or_gap=[],
        avoid=["frontend", "product management"],
    )

    posting = JobPosting(
        company_key="test",
        company_name="Test Company",
        source_type="greenhouse",
        source_url="https://example.com/job",
        title="Senior Frontend Engineer",
        location="Remote",
        description="Build product management tooling.",
    )

    assert _find_profile_avoid_matches(profile, posting) == [
        "frontend",
        "product management",
    ]


def test_find_profile_avoid_matches_detects_cleared_only_roles() -> None:
    profile = CandidateProfile(
        name="Clayton Graves",
        compensation_floor_usd=160000,
        preferred_base_usd=185000,
        resume=None,
        core_strengths=[],
        credible_adjacent=[],
        learning_or_gap=[],
        avoid=["cleared-only roles"],
    )

    posting = JobPosting(
        company_key="test",
        company_name="Test Company",
        source_type="greenhouse",
        source_url="https://example.com/job",
        title="Senior Infrastructure Engineer",
        location="Remote",
        description="Active Top Secret clearance and polygraph required.",
    )

    assert _find_profile_avoid_matches(profile, posting) == ["cleared-only roles"]


def test_find_profile_avoid_matches_ignores_non_matching_terms() -> None:
    profile = CandidateProfile(
        name="Clayton Graves",
        compensation_floor_usd=160000,
        preferred_base_usd=185000,
        resume=None,
        core_strengths=[],
        credible_adjacent=[],
        learning_or_gap=[],
        avoid=["frontend", "customer success", "cleared-only roles"],
    )

    posting = JobPosting(
        company_key="test",
        company_name="Test Company",
        source_type="greenhouse",
        source_url="https://example.com/job",
        title="Senior Infrastructure Engineer",
        location="Remote",
        description="Build Linux infrastructure and cluster systems.",
    )

    assert _find_profile_avoid_matches(profile, posting) == []