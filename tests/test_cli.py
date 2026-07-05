import sqlite3
from pathlib import Path

from openpyxl import Workbook

from job_radar.candidate_profile import CandidateProfile
from job_radar.cli import (
    _find_profile_avoid_matches,
    build_parser,
    handle_import_history,
    handle_scan,
    handle_tracker_add,
    handle_tracker_list,
    handle_tracker_update,
)
from job_radar.job_history import EXPECTED_HEADERS, SIMPLIFIED_HEADERS, JobHistoryRecord
from job_radar.storage import initialize_database, upsert_job_history_record
from job_radar.email_sender import EmailSendResult
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash
from job_radar.tracker.models import ApplicationRecord
from job_radar.tracker.storage import upsert_application


def count_job_posting_rows(database_file: Path) -> int:
    with sqlite3.connect(database_file) as connection:
        cursor = connection.execute("SELECT COUNT(*) FROM job_postings")
        return int(cursor.fetchone()[0])


def count_scan_run_rows(database_file: Path) -> int:
    with sqlite3.connect(database_file) as connection:
        cursor = connection.execute("SELECT COUNT(*) FROM scan_runs")
        return int(cursor.fetchone()[0])
    


def count_job_history_rows(database_file: Path) -> int:
    with sqlite3.connect(database_file) as connection:
        cursor = connection.execute("SELECT COUNT(*) FROM job_history")
        return int(cursor.fetchone()[0])


def count_application_tracker_rows(database_file: Path) -> int:
    with sqlite3.connect(database_file) as connection:
        cursor = connection.execute("SELECT COUNT(*) FROM application_tracker")
        return int(cursor.fetchone()[0])


def fetch_job_history_status(
    database_file: Path,
    import_key: str,
) -> str | None:
    with sqlite3.connect(database_file) as connection:
        cursor = connection.execute(
            """
            SELECT status
            FROM job_history
            WHERE import_key = ?
            """,
            (import_key,),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    return str(row[0])


def make_cli_history_record(
    import_key: str,
    technical_match: str,
    outcome_category: str,
    primary_blocker: str | None = None,
) -> JobHistoryRecord:
    return JobHistoryRecord(
        history_type="Pipeline",
        company="Example AI",
        role="Senior Infrastructure Engineer",
        source="LinkedIn",
        ats_platform="Greenhouse",
        work_arrangement="Remote",
        location="Remote",
        comp_range="$160k-$200k",
        event_date="2026-06-01",
        status="Rejected - No Interview",
        outcome_category=outcome_category,
        recruiter_contact="Unknown",
        technical_match=technical_match,
        hiring_probability="Low",
        skills_signals="Linux, HPC, Infrastructure",
        primary_blocker=primary_blocker,
        secondary_blocker=None,
        revisit="No",
        include_in_job_radar=True,
        import_key=import_key,
        notes="Form rejection.",
    )


def write_cli_history_workbook(workbook_path: Path) -> None:
    workbook = Workbook()
    pipeline_sheet = workbook.active
    pipeline_sheet.title = "Pipeline Import"
    reviewed_sheet = workbook.create_sheet("Reviewed Import")

    pipeline_sheet.append(EXPECTED_HEADERS)
    reviewed_sheet.append(EXPECTED_HEADERS)

    pipeline_sheet.append(
        [
            "Pipeline",
            "Example AI",
            "Senior Infrastructure Engineer",
            "LinkedIn",
            "Greenhouse",
            "Remote",
            "Remote",
            "$160k-$200k",
            "2026-06-01",
            "Rejected - No Interview",
            "No Interview",
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
            "Reviewed",
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


def write_cli_simplified_history_workbook(workbook_path: Path) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Job Log"
    worksheet.append(SIMPLIFIED_HEADERS)
    worksheet.append(
        [
            "jr-example-ai-001",
            "2026-07-03",
            "Example AI",
            "Senior Infrastructure Engineer",
            "https://example.com/jobs/123",
            "Job Radar",
            "Applied",
            None,
            "Jane Recruiter",
            "Applied from simplified Job Log.",
            "Yes",
        ]
    )
    worksheet.append(
        [
            None,
            "2026-07-03",
            "ManualCo",
            "Principal SRE",
            "https://example.com/manual-lead",
            "LinkedIn",
            "Interested",
            None,
            None,
            "Manual lead from LinkedIn.",
            "Yes",
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
    assert count_application_tracker_rows(database_file) == 1

    assert "Application history import complete" in output
    assert f"Workbook: {workbook_file}" in output
    assert f"Database: {database_file}" in output
    assert "Rows read: 2" in output
    assert "Rows imported: 2" in output
    assert "Rows updated: 0" in output
    assert "Rows skipped: 0" in output
    assert "Tracker rows imported: 1" in output
    assert "Tracker rows updated: 0" in output
    assert "Tracker rows skipped: 1" in output


def test_handle_import_history_imports_simplified_workbook_rows(
    tmp_path: Path,
    capsys,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    workbook_file = tmp_path / "job-history.xlsx"
    database_file = tmp_path / "job_radar.sqlite3"

    write_cli_simplified_history_workbook(workbook_file)

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
    assert count_application_tracker_rows(database_file) == 2

    assert fetch_job_history_status(
        database_file,
        "job-radar-id:jr-example-ai-001",
    ) == "Applied"
    assert fetch_job_history_status(
        database_file,
        "posting-url:https://example.com/manual-lead",
    ) == "Interested"

    assert "Application history import complete" in output
    assert f"Workbook: {workbook_file}" in output
    assert f"Database: {database_file}" in output
    assert "Rows read: 2" in output
    assert "Rows imported: 2" in output
    assert "Rows updated: 0" in output
    assert "Rows skipped: 0" in output
    assert "Tracker rows imported: 2" in output
    assert "Tracker rows updated: 0" in output
    assert "Tracker rows skipped: 0" in output


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
    assert count_scan_run_rows(database_file) == 1

    assert "Scan requested" in output
    assert "Companies enabled: 1" in output
    assert "Jobs collected: 1" in output
    assert "Actionable jobs stored: 1" in output
    assert "Jobs not actionable: 0" in output
    assert "Jobs new: 1" in output
    assert "Jobs seen: 0" in output
    assert "Jobs changed: 0" in output
    assert "Collector errors: 0" in output
    assert "# Job Radar Report" in report_text
    assert "- Companies enabled: 1" in report_text
    assert "- Jobs collected: 1" in report_text
    assert "- Actionable jobs stored: 1" in report_text
    assert "- Jobs not actionable: 0" in report_text
    assert "- New jobs: 1" in report_text
    assert "- Seen jobs: 0" in report_text
    assert "- Changed jobs: 0" in report_text
    assert "- Collector errors: 0" in report_text
    assert "- Top match score threshold: 1" in report_text
    assert "- Review-needed score threshold: 100" in report_text

    assert "## Top Matches" in report_text
    assert "## Passed / Not Recommended" in report_text
    assert "## All Jobs" not in report_text
    assert (
        "### [Senior Infrastructure Engineer]"
        "(https://boards.greenhouse.io/exampleai/jobs/123)"
        in report_text
    )

    assert "- Score: 40" in report_text
    assert "- Why this matched: infrastructure, linux, remote" in report_text
    assert "- Score reasons:" not in report_text
    assert "+30 title:infrastructure" not in report_text
    assert "+10 body:linux" not in report_text
    assert "+0 location_allowed:remote" not in report_text
    assert "- Work location fit: remote" in report_text
    assert "- Location status:" not in report_text

    assert "- Company: Example AI" in report_text
    assert "- Source: greenhouse" in report_text
    assert "- Location: Remote" in report_text
    assert "- URL: https://boards.greenhouse.io/exampleai/jobs/123" in report_text
    assert "- Canonical key: `example-ai:senior-infrastructure-engineer:remote`" in report_text


def test_handle_scan_adds_history_context_to_report(
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

top_matches:
  min_score: 1
  excluded_title_keywords: []
  strong_signals:
    - title:infrastructure
""",
        encoding="utf-8",
    )

    initialize_database(database_file)
    upsert_job_history_record(
        database_file,
        make_cli_history_record(
            import_key="pipeline:example-ai:senior-infrastructure-engineer",
            technical_match="Strong",
            outcome_category="No Interview",
            primary_blocker="Compensation",
        ),
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
        canonical_key="example-ai:senior-infrastructure-engineer:remote",
        content_hash="hash-linux-infrastructure",
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

    capsys.readouterr()
    report_text = report_file.read_text(encoding="utf-8")

    assert "- Job history context:" in report_text
    assert "  - Imported history: 1 records (1 pipeline, 0 reviewed)" in report_text
    assert (
        "  - Strong technical alignment has not always led to interviews "
        "in prior applications (1 no-interview outcomes)"
        in report_text
    )
    assert (
        "  - Strong technical matches with no interview: "
        "Strong / No Interview: 1"
        in report_text
    )
    assert "  - Common prior history signals: Compensation: 1" in report_text
    assert "- History context: Imported history: 1 records" not in report_text
    assert (
        "- History context: Prior similar application at Example AI ended "
        "No Interview despite Strong technical match"
        in report_text
    )
    assert (
        "- History risk: caution: prior_no_interview_despite_strong_match"
        in report_text
    )


def test_handle_scan_imports_configured_history_workbook_before_report(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config_file = tmp_path / "companies.yaml"
    settings_file = tmp_path / "settings.yaml"
    scoring_file = tmp_path / "scoring.yaml"
    workbook_file = tmp_path / "job-history.xlsx"
    database_file = tmp_path / "job_radar.sqlite3"
    report_file = tmp_path / "today.md"

    write_cli_history_workbook(workbook_file)

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
job_history_workbook_path: {workbook_file}

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

    fake_posting = JobPosting(
        company_key="example_ai",
        company_name="Example AI",
        source_type="greenhouse",
        source_job_id="123",
        source_url="https://boards.greenhouse.io/exampleai/jobs/123",
        title="Senior Infrastructure Engineer",
        location="Remote",
        description="Build Linux infrastructure.",
        canonical_key="example-ai:senior-infrastructure-engineer:remote",
        content_hash="hash-linux-infrastructure",
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

    assert count_job_history_rows(database_file) == 2
    assert count_application_tracker_rows(database_file) == 1
    assert fetch_job_history_status(
        database_file,
        "pipeline:example-ai:senior-infrastructure-engineer",
    ) == "Rejected - No Interview"

    assert "Application history import complete" in output
    assert f"Workbook: {workbook_file}" in output
    assert "Rows read: 2" in output
    assert "Rows imported: 2" in output
    assert "Rows updated: 0" in output
    assert "Rows skipped: 0" in output
    assert "Tracker rows imported: 1" in output
    assert "Tracker rows updated: 0" in output
    assert "Tracker rows skipped: 1" in output

    assert "- Job history context:" in report_text
    assert "  - Imported history: 2 records (1 pipeline, 1 reviewed)" in report_text
    assert (
        "  - Strong technical alignment has not always led to interviews "
        "in prior applications (1 no-interview outcomes)"
        in report_text
    )
    assert (
        "  - Strong technical matches with no interview: "
        "Very Strong / No Interview: 1"
        in report_text
    )
    assert "  - Common prior history signals: Generic Remote Competition: 1" in report_text


def test_handle_scan_attaches_existing_tracker_record_to_report(
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

top_matches:
  min_score: 1
  excluded_title_keywords: []
  strong_signals:
    - title:infrastructure
""",
        encoding="utf-8",
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
        canonical_key="example-ai:senior-infrastructure-engineer:remote",
        content_hash="hash-linux-infrastructure",
    )

    initialize_database(database_file)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id=fake_posting.job_radar_id,
            company_name="Example AI",
            role_title="Senior Infrastructure Engineer",
            source_url="https://boards.greenhouse.io/exampleai/jobs/123",
            status="applied",
            follow_up_on="2026-07-10",
            outcome="interviewing",
            notes="Already applied through company site.",
        ),
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

    capsys.readouterr()
    report_text = report_file.read_text(encoding="utf-8")

    assert count_application_tracker_rows(database_file) == 1
    assert "- Track Status:" in report_text
    assert "  - Status: applied" in report_text
    assert "  - Follow up on: 2026-07-10" in report_text
    assert "  - Outcome: interviewing" in report_text
    assert "  - Notes: Already applied through company site." in report_text


def test_handle_scan_omits_track_status_for_untracked_job(
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

top_matches:
  min_score: 1
  excluded_title_keywords: []
  strong_signals:
    - title:infrastructure
""",
        encoding="utf-8",
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
        canonical_key="example-ai:senior-infrastructure-engineer:remote",
        content_hash="hash-linux-infrastructure",
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

    capsys.readouterr()
    report_text = report_file.read_text(encoding="utf-8")

    assert count_application_tracker_rows(database_file) == 0
    assert "- Track Status:\n  - Status:" not in report_text


def test_handle_scan_warns_and_continues_when_configured_history_workbook_is_missing(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config_file = tmp_path / "companies.yaml"
    settings_file = tmp_path / "settings.yaml"
    scoring_file = tmp_path / "scoring.yaml"
    workbook_file = tmp_path / "missing-job-history.xlsx"
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
job_history_workbook_path: {workbook_file}

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

    fake_posting = JobPosting(
        company_key="example_ai",
        company_name="Example AI",
        source_type="greenhouse",
        source_job_id="123",
        source_url="https://boards.greenhouse.io/exampleai/jobs/123",
        title="Senior Infrastructure Engineer",
        location="Remote",
        description="Build Linux infrastructure.",
        canonical_key="example-ai:senior-infrastructure-engineer:remote",
        content_hash="hash-linux-infrastructure",
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

    assert database_file.exists()
    assert report_file.exists()
    assert count_job_history_rows(database_file) == 0
    assert count_scan_run_rows(database_file) == 1

    assert "Application history import skipped" in output
    assert f"Workbook: {workbook_file}" in output
    assert "Reason: workbook file does not exist; using existing database history" in output
    assert "Scan summary:" in output
    assert "Actionable jobs stored: 1" in output


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


def test_parser_accepts_grouped_history_import_command() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "history",
            "import",
            "--workbook",
            "data/job-history.xlsx",
            "--settings",
            "config/settings.yaml",
        ]
    )

    assert args.command == "history"
    assert args.history_command == "import"
    assert args.workbook == "data/job-history.xlsx"
    assert args.settings == "config/settings.yaml"


def test_parser_accepts_grouped_history_summary_command() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "history",
            "summary",
            "--settings",
            "config/settings.yaml",
        ]
    )

    assert args.command == "history"
    assert args.history_command == "summary"
    assert args.settings == "config/settings.yaml"


def test_parser_accepts_grouped_db_init_command() -> None:
    parser = build_parser()

    args = parser.parse_args(["db", "init"])

    assert args.command == "db"
    assert args.db_command == "init"


def test_parser_keeps_legacy_history_commands() -> None:
    parser = build_parser()

    import_args = parser.parse_args(
        [
            "import-history",
            "--workbook",
            "data/job-history.xlsx",
            "--settings",
            "config/settings.yaml",
        ]
    )
    summary_args = parser.parse_args(
        [
            "history-summary",
            "--settings",
            "config/settings.yaml",
        ]
    )
    init_args = parser.parse_args(["init-db"])

    assert import_args.command == "import-history"
    assert import_args.workbook == "data/job-history.xlsx"
    assert summary_args.command == "history-summary"
    assert init_args.command == "init-db"


def test_parser_accepts_tracker_list_command() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "tracker",
            "list",
            "--settings",
            "config/settings.yaml",
        ]
    )

    assert args.command == "tracker"
    assert args.tracker_command == "list"
    assert args.settings == "config/settings.yaml"
    assert args.needs_action is False


def test_parser_accepts_tracker_list_needs_action_command() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "tracker",
            "list",
            "--needs-action",
            "--settings",
            "config/settings.yaml",
        ]
    )

    assert args.command == "tracker"
    assert args.tracker_command == "list"
    assert args.needs_action is True
    assert args.settings == "config/settings.yaml"


def test_handle_tracker_list_outputs_tracked_applications(
    tmp_path: Path,
    capsys,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

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

    initialize_database(database_file)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-stack-av-12345678",
            company_name="Stack AV",
            role_title="Senior Site Reliability Engineer",
            source_url="https://example.com/jobs/stack-av-sre",
            status="applied",
            follow_up_on="2026-07-10",
            outcome=None,
            notes="Applied through company site.",
        ),
    )

    handle_tracker_list(settings_path=str(settings_file))

    output = capsys.readouterr().out

    assert "Application tracker" in output
    assert f"Database: {database_file}" in output
    assert "Applications tracked: 1" in output
    assert "- Stack AV — Senior Site Reliability Engineer" in output
    assert "Job Radar ID: jr-stack-av-12345678" in output
    assert "Status: applied" in output
    assert "Workflow: follow_up_scheduled" in output
    assert "Follow up on: 2026-07-10" in output
    assert "URL: https://example.com/jobs/stack-av-sre" in output
    assert "Notes: Applied through company site." in output


def test_parser_accepts_tracker_update_command() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "tracker",
            "update",
            "--job-radar-id",
            "jr-stack-av-12345678",
            "--status",
            "applied",
            "--follow-up-on",
            "2026-07-10",
            "--outcome",
            "interviewing",
            "--notes",
            "Recruiter replied.",
            "--settings",
            "config/settings.yaml",
        ]
    )

    assert args.command == "tracker"
    assert args.tracker_command == "update"
    assert args.job_radar_id == "jr-stack-av-12345678"
    assert args.status == "applied"
    assert args.follow_up_on == "2026-07-10"
    assert args.outcome == "interviewing"
    assert args.notes == "Recruiter replied."
    assert args.settings == "config/settings.yaml"


def test_handle_tracker_list_filters_to_applications_needing_action(
    tmp_path: Path,
    capsys,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

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

    initialize_database(database_file)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-due-12345678",
            company_name="DueCo",
            role_title="Senior SRE",
            source_url="https://example.com/jobs/due",
            status="follow_up_due",
            follow_up_on="2026-07-04",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-active-12345678",
            company_name="ActiveCo",
            role_title="Infrastructure Engineer",
            source_url="https://example.com/jobs/active",
            status="interviewing",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-waiting-12345678",
            company_name="WaitingCo",
            role_title="Platform Engineer",
            source_url="https://example.com/jobs/waiting",
            status="applied",
        ),
    )

    handle_tracker_list(
        settings_path=str(settings_file),
        needs_action=True,
    )

    output = capsys.readouterr().out

    assert "Application tracker" in output
    assert "Filter: needs action" in output
    assert "Applications tracked: 2" in output
    assert "DueCo" in output
    assert "Workflow: follow_up_due" in output
    assert "ActiveCo" in output
    assert "Workflow: active_pipeline" in output
    assert "WaitingCo" not in output
    assert "Workflow: waiting" not in output


def test_handle_tracker_update_updates_existing_application(
    tmp_path: Path,
    capsys,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

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

    initialize_database(database_file)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-stack-av-12345678",
            company_name="Stack AV",
            role_title="Senior Site Reliability Engineer",
            source_url="https://example.com/jobs/stack-av-sre",
            status="review_needed",
            notes="Initial review.",
        ),
    )

    handle_tracker_update(
        settings_path=str(settings_file),
        job_radar_id="jr-stack-av-12345678",
        status="applied",
        follow_up_on="2026-07-10",
        outcome="interviewing",
        notes="Recruiter replied.",
    )

    output = capsys.readouterr().out

    assert "Application tracker updated" in output
    assert f"Database: {database_file}" in output
    assert "Job Radar ID: jr-stack-av-12345678" in output
    assert "Status: applied" in output
    assert "Follow up on: 2026-07-10" in output
    assert "Outcome: interviewing" in output
    assert "Notes: Recruiter replied." in output

    handle_tracker_list(settings_path=str(settings_file))
    list_output = capsys.readouterr().out

    assert "Applications tracked: 1" in list_output
    assert "Status: applied" in list_output
    assert "Workflow: follow_up_scheduled" in list_output
    assert "Follow up on: 2026-07-10" in list_output
    assert "Outcome: interviewing" in list_output
    assert "Notes: Recruiter replied." in list_output


def test_handle_tracker_update_reports_missing_application(
    tmp_path: Path,
    capsys,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

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

    handle_tracker_update(
        settings_path=str(settings_file),
        job_radar_id="jr-missing-00000000",
        status="applied",
    )

    output = capsys.readouterr().out

    assert "Application tracker update failed" in output
    assert f"Database: {database_file}" in output
    assert "Job Radar ID: jr-missing-00000000" in output
    assert "Reason: tracked application was not found" in output


def test_parser_accepts_tracker_add_command() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "tracker",
            "add",
            "--job-radar-id",
            "jr-manual-12345678",
            "--company",
            "Example AI",
            "--role",
            "Senior Site Reliability Engineer",
            "--url",
            "https://example.com/jobs/123",
            "--status",
            "applied",
            "--follow-up-on",
            "2026-07-10",
            "--outcome",
            "interviewing",
            "--notes",
            "Applied through company site.",
            "--settings",
            "config/settings.yaml",
        ]
    )

    assert args.command == "tracker"
    assert args.tracker_command == "add"
    assert args.job_radar_id == "jr-manual-12345678"
    assert args.company == "Example AI"
    assert args.role == "Senior Site Reliability Engineer"
    assert args.url == "https://example.com/jobs/123"
    assert args.status == "applied"
    assert args.follow_up_on == "2026-07-10"
    assert args.outcome == "interviewing"
    assert args.notes == "Applied through company site."
    assert args.settings == "config/settings.yaml"


def test_handle_tracker_add_creates_tracked_application(
    tmp_path: Path,
    capsys,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

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

    handle_tracker_add(
        settings_path=str(settings_file),
        job_radar_id="jr-manual-12345678",
        company_name="Example AI",
        role_title="Senior Site Reliability Engineer",
        source_url="https://example.com/jobs/123",
        status="applied",
        follow_up_on="2026-07-10",
        outcome="interviewing",
        notes="Applied through company site.",
    )

    output = capsys.readouterr().out

    assert "Application tracker entry saved" in output
    assert f"Database: {database_file}" in output
    assert "Result: new" in output
    assert "Job Radar ID: jr-manual-12345678" in output
    assert "Company: Example AI" in output
    assert "Role: Senior Site Reliability Engineer" in output
    assert "Status: applied" in output
    assert "Follow up on: 2026-07-10" in output
    assert "Outcome: interviewing" in output
    assert "URL: https://example.com/jobs/123" in output
    assert "Notes: Applied through company site." in output

    handle_tracker_list(settings_path=str(settings_file))
    list_output = capsys.readouterr().out

    assert "Applications tracked: 1" in list_output
    assert "- Example AI — Senior Site Reliability Engineer" in list_output
    assert "Job Radar ID: jr-manual-12345678" in list_output
    assert "Status: applied" in list_output
