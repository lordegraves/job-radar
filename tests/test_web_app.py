from pathlib import Path

import job_radar.web_app as web_app_module

from job_radar.job_history import JobHistoryRecord
from job_radar.storage import initialize_database, upsert_job_history_record
from job_radar.tracker.models import ApplicationRecord
from job_radar.tracker.storage import get_application, upsert_application
from job_radar.web_app import create_app


def write_settings_file(
    settings_file: Path,
    database_file: Path,
    reports_path: Path | None = None,
) -> None:
    resolved_reports_path = reports_path or settings_file.parent

    settings_file.write_text(
        f"""
database_path: {database_file}
reports_path: {resolved_reports_path}
logs_path: {settings_file.parent}

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


def test_tracker_page_lists_tracked_applications(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
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
            applied_on="2026-07-03",
            last_activity_on="2026-07-05",
            outcome="Interviewing",
            notes="Applied through company site.",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Application Tracker" in html
    assert f"<code>{database_file}</code>" in html
    assert "Applications shown:</strong> 1" in html
    assert "Stack AV" in html
    assert "Senior Site Reliability Engineer" in html
    assert "applied" in html
    assert "follow_up_scheduled" in html
    assert "2026-07-03" in html
    assert "2026-07-05" in html
    assert "2026-07-10" in html
    assert "Interviewing" in html
    assert "outcome-cell" in html
    assert "jr-stack-av-12345678" in html
    assert "https://example.com/jobs/stack-av-sre" in html
    assert "Applied through company site." in html


def test_tracker_page_handles_empty_tracker(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Application Tracker" in html
    assert "Applications shown:</strong> 0" in html
    assert "No tracked applications." in html


def test_index_page_links_to_history_archive(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<a href="/history">Job history archive</a>' in html


def test_history_page_lists_imported_history_records(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_job_history_record(
        database_file,
        JobHistoryRecord(
            history_type="Reviewed",
            company="ArchiveCo",
            role="Senior Linux Engineer",
            source="LinkedIn",
            ats_platform=None,
            work_arrangement=None,
            location=None,
            comp_range=None,
            event_date="2026-07-01",
            status="Skipped",
            outcome_category="Skipped / Avoid",
            recruiter_contact="Example Recruiter",
            technical_match=None,
            hiring_probability=None,
            skills_signals=None,
            primary_blocker=None,
            secondary_blocker=None,
            revisit=None,
            include_in_job_radar=True,
            import_key="manual:archiveco:senior-linux-engineer",
            notes="Skipped because the role was onsite outside target area.",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/history")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Job History Archive" in html
    assert f"<code>{database_file}</code>" in html
    assert "History records shown:</strong> 1" in html
    assert "ArchiveCo" in html
    assert "Senior Linux Engineer" in html
    assert "Reviewed" in html
    assert "Skipped" in html
    assert "Skipped / Avoid" in html
    assert "outcome-cell" in html
    assert "LinkedIn" in html
    assert "Example Recruiter" in html
    assert "manual:archiveco:senior-linux-engineer" in html
    assert "Skipped because the role was onsite outside target area." in html
    assert "Viewing these records does not add them to the active application tracker." in html


def test_history_page_sorts_by_company_status_role_outcome_and_date(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_job_history_record(
        database_file,
        JobHistoryRecord(
            history_type="Reviewed",
            company="ZetaCo",
            role="Linux Engineer",
            source="LinkedIn",
            ats_platform=None,
            work_arrangement=None,
            location=None,
            comp_range=None,
            event_date="2026-06-01",
            status="Passed",
            outcome_category="N/A",
            recruiter_contact=None,
            technical_match=None,
            hiring_probability=None,
            skills_signals=None,
            primary_blocker=None,
            secondary_blocker=None,
            revisit=None,
            include_in_job_radar=True,
            import_key="manual:zetaco:linux-engineer",
            notes=None,
        ),
    )
    upsert_job_history_record(
        database_file,
        JobHistoryRecord(
            history_type="Pipeline",
            company="AlphaCo",
            role="Platform Engineer",
            source="Job Radar",
            ats_platform=None,
            work_arrangement=None,
            location=None,
            comp_range=None,
            event_date="2026-07-01",
            status="Withdrawn",
            outcome_category="Withdrawn",
            recruiter_contact=None,
            technical_match=None,
            hiring_probability=None,
            skills_signals=None,
            primary_blocker=None,
            secondary_blocker=None,
            revisit=None,
            include_in_job_radar=True,
            import_key="manual:alphaco:platform-engineer",
            notes=None,
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    default_response = client.get("/history")
    default_html = default_response.get_data(as_text=True)
    assert default_response.status_code == 200
    assert '<option value="event_desc" selected>' in default_html
    assert default_html.index("AlphaCo") < default_html.index("ZetaCo")

    date_asc_response = client.get("/history?sort=event_asc")
    date_asc_html = date_asc_response.get_data(as_text=True)
    assert date_asc_response.status_code == 200
    assert '<option value="event_asc" selected>' in date_asc_html
    assert date_asc_html.index("ZetaCo") < date_asc_html.index("AlphaCo")

    company_response = client.get("/history?sort=company")
    company_html = company_response.get_data(as_text=True)
    assert company_response.status_code == 200
    assert '<option value="company" selected>' in company_html
    assert company_html.index("AlphaCo") < company_html.index("ZetaCo")

    role_response = client.get("/history?sort=role")
    role_html = role_response.get_data(as_text=True)
    assert role_response.status_code == 200
    assert '<option value="role" selected>' in role_html
    assert role_html.index("Linux Engineer") < role_html.index("Platform Engineer")

    status_response = client.get("/history?sort=status")
    status_html = status_response.get_data(as_text=True)
    assert status_response.status_code == 200
    assert '<option value="status" selected>' in status_html
    assert status_html.index("ZetaCo") < status_html.index("AlphaCo")

    outcome_response = client.get("/history?sort=outcome")
    outcome_html = outcome_response.get_data(as_text=True)
    assert outcome_response.status_code == 200
    assert '<option value="outcome" selected>' in outcome_html
    assert outcome_html.index("ZetaCo") < outcome_html.index("AlphaCo")


def test_history_page_searches_and_filters_records(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_job_history_record(
        database_file,
        JobHistoryRecord(
            history_type="Pipeline",
            company="Hydra Host",
            role="HPC Solutions Engineer",
            source="Recruiter",
            ats_platform=None,
            work_arrangement=None,
            location=None,
            comp_range=None,
            event_date="2026-07-01",
            status="Applied",
            outcome_category="Pending / In Progress",
            recruiter_contact="Hydra Recruiter",
            technical_match=None,
            hiring_probability=None,
            skills_signals=None,
            primary_blocker=None,
            secondary_blocker=None,
            revisit=None,
            include_in_job_radar=True,
            import_key="manual:hydra-host:hpc-solutions-engineer",
            notes="Strong InfiniBand and Slurm fit.",
        ),
    )
    upsert_job_history_record(
        database_file,
        JobHistoryRecord(
            history_type="Reviewed",
            company="SkipCo",
            role="Desktop Support Engineer",
            source="LinkedIn",
            ats_platform=None,
            work_arrangement=None,
            location=None,
            comp_range=None,
            event_date="2026-06-01",
            status="Passed",
            outcome_category="Closed Before Application",
            recruiter_contact=None,
            technical_match=None,
            hiring_probability=None,
            skills_signals=None,
            primary_blocker=None,
            secondary_blocker=None,
            revisit=None,
            include_in_job_radar=True,
            import_key="manual:skipco:desktop-support-engineer",
            notes="Wrong role family.",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    search_response = client.get("/history?q=infiniband")
    search_html = search_response.get_data(as_text=True)

    assert search_response.status_code == 200
    assert "History records shown:</strong> 1" in search_html
    assert "Hydra Host" in search_html
    assert "SkipCo" not in search_html
    assert 'value="infiniband"' in search_html

    filter_response = client.get(
        "/history",
        query_string={
            "decision_filter": "Applied",
            "outcome_filter": "Pending / In Progress",
            "sort": "company",
        },
    )
    filter_html = filter_response.get_data(as_text=True)

    assert filter_response.status_code == 200
    assert "History records shown:</strong> 1" in filter_html
    assert "Hydra Host" in filter_html
    assert "SkipCo" not in filter_html
    assert '<option value="Applied" selected>' in filter_html
    assert '<option value="Passed"' in filter_html
    assert '<option value="Withdrawn"' in filter_html
    assert '<option value="Revisit"' in filter_html
    assert '<option value="Pending / In Progress" selected>' in filter_html
    assert '<option value="Interview Scheduled"' in filter_html
    assert '<option value="Interview Completed"' in filter_html
    assert '<option value="Waiting For Feedback"' in filter_html
    assert '<option value="Offer"' in filter_html
    assert '<option value="Dormant"' in filter_html
    assert '<option value="Closed Before Application"' in filter_html
    assert '<option value="Rejected - No Interview"' in filter_html
    assert '<option value="Rejected - After Interview"' in filter_html
    assert '<option value="Withdrawn"' in filter_html
    assert '<option value="N/A"' in filter_html
    assert '<option value="company" selected>' in filter_html
    assert "Skipped / Avoid" not in filter_html
    assert "Clear search/filters/sort" in filter_html


def test_history_page_rejects_unknown_sort(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/history?sort=unknown")

    assert response.status_code == 404


def test_history_page_handles_empty_history(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/history")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Job History Archive" in html
    assert "History records shown:</strong> 0" in html
    assert "No imported job history records." in html


def test_index_page_links_to_scan(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<a href="/scan">Scan</a>' in html


def test_scan_page_shows_manual_scan_command(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/scan")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    normalized_html = " ".join(html.split())

    assert "Scan" in html
    assert "This page shows the safe manual scan command" in normalized_html
    assert "GUI scan execution does not send email." in normalized_html
    assert "Run scan now" in html
    assert "Scan is running. This may take a few minutes." in normalized_html
    assert "python -m job_radar scan" in html
    assert "--config config/target-companies.yaml" in html
    assert f"--settings {settings_file}" in html
    assert "--report reports/target-scan.md" in html
    assert "--email-preview reports/target-email-preview.txt" in html


def test_scan_run_calls_handle_scan_and_redirects(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    calls = []

    write_settings_file(settings_file, database_file)

    def fake_handle_scan(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(web_app_module, "handle_scan", fake_handle_scan)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.post("/scan/run")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/scan?scan_result=success")
    assert calls == [
        {
            "config_path": "config/target-companies.yaml",
            "settings_path": str(settings_file),
            "report_path": "reports/target-scan.md",
            "scoring_path": "config/scoring.yaml",
            "email_preview_path": "reports/target-email-preview.txt",
            "send_email": False,
        }
    ]


def test_scan_run_reports_busy_when_scan_is_already_running(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    web_app_module.SCAN_RUN_LOCK.acquire()

    try:
        app = create_app(settings_path=str(settings_file))
        client = app.test_client()

        response = client.post("/scan/run", follow_redirects=True)
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Scan already running." in html
        assert "Wait for the current scan to finish before starting another one." in html
    finally:
        web_app_module.SCAN_RUN_LOCK.release()


def test_scan_run_reports_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    def fake_handle_scan(**kwargs):
        raise RuntimeError("scan exploded")

    monkeypatch.setattr(web_app_module, "handle_scan", fake_handle_scan)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.post("/scan/run", follow_redirects=True)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Scan failed." in html
    assert "scan exploded" in html


def test_index_page_links_to_reports(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<a href="/reports">Reports</a>' in html


def test_reports_page_lists_existing_report_files(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    reports_path = tmp_path / "reports"
    reports_path.mkdir()

    (reports_path / "target-scan.html").write_text(
        "<html><body>Target scan</body></html>",
        encoding="utf-8",
    )
    (reports_path / "target-scan.md").write_text(
        "# Target scan",
        encoding="utf-8",
    )
    (reports_path / "target-email-preview.txt").write_text(
        "Email preview",
        encoding="utf-8",
    )
    (reports_path / "code-audit.md").write_text(
        "# Code audit",
        encoding="utf-8",
    )
    (reports_path / "job_radar.sqlite3").write_text(
        "not a report",
        encoding="utf-8",
    )

    write_settings_file(settings_file, database_file, reports_path=reports_path)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/reports")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Reports" in html
    assert f"<code>{reports_path}</code>" in html
    assert "Report files shown:</strong> 4" in html
    assert "Primary scan outputs" in html
    assert "Other report files" in html
    assert "target-scan.html" in html
    assert "/reports/view/target-scan.html" in html
    assert "Main scan report. Open this first." in html
    assert "target-scan.md" in html
    assert "Markdown version of the main scan report." in html
    assert "target-email-preview.txt" in html
    assert "Plain-text email preview generated by the scan." in html
    assert "code-audit.md" in html
    assert "Additional generated report or support artifact." in html
    assert "job_radar.sqlite3" not in html
    assert "It does not start a scan or send email." in html


def test_reports_page_handles_missing_reports_directory(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    reports_path = tmp_path / "missing-reports"

    write_settings_file(settings_file, database_file, reports_path=reports_path)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/reports")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Report files shown:</strong> 0" in html
    assert "No primary scan outputs found yet. Run a scan first." in html
    assert "No other report files found." in html


def test_report_view_embeds_report_inside_app_shell(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    reports_path = tmp_path / "reports"
    reports_path.mkdir()
    report_file = reports_path / "target-scan.html"
    report_file.write_text("<html><body>Target scan</body></html>", encoding="utf-8")

    write_settings_file(settings_file, database_file, reports_path=reports_path)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/reports/view/target-scan.html")
    html = response.get_data(as_text=True)

    normalized_html = " ".join(html.split())

    assert response.status_code == 200
    assert "Report Viewer" in html
    assert "Back to Reports" in html
    assert "<code>target-scan.html</code>" in html
    assert 'src="/reports/target-scan.html"' in html
    assert '<a href="/reports">Back to Reports</a>' in normalized_html


def test_report_view_rejects_non_report_file(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    reports_path = tmp_path / "reports"
    reports_path.mkdir()
    (reports_path / "job_radar.sqlite3").write_text("private db", encoding="utf-8")

    write_settings_file(settings_file, database_file, reports_path=reports_path)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/reports/view/job_radar.sqlite3")

    assert response.status_code == 404


def test_report_file_serves_allowed_report_file(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    reports_path = tmp_path / "reports"
    reports_path.mkdir()
    report_file = reports_path / "target-scan.md"
    report_file.write_text("# Target scan", encoding="utf-8")

    write_settings_file(settings_file, database_file, reports_path=reports_path)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/reports/target-scan.md")

    assert response.status_code == 200
    assert "# Target scan" in response.get_data(as_text=True)


def test_report_file_rejects_non_report_file(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    reports_path = tmp_path / "reports"
    reports_path.mkdir()
    (reports_path / "job_radar.sqlite3").write_text("private db", encoding="utf-8")

    write_settings_file(settings_file, database_file, reports_path=reports_path)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/reports/job_radar.sqlite3")

    assert response.status_code == 404


def test_tracker_page_expands_long_notes(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"
    long_note = (
        "This is a long tracker note with important context. "
        "It should not be hidden from the GUI because the notes field often "
        "contains fit concerns, recruiter context, rejection details, and "
        "manual review comments."
    )

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-notes-12345678",
            company_name="NotesCo",
            role_title="Senior Infrastructure Engineer",
            status="applied",
            notes=long_note,
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker?sort=workflow")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Show full note" in html
    assert "This is a long tracker note with important context." in html
    assert "manual review comments." in html


def test_tracker_page_sorts_by_workflow_priority(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-waiting-12345678",
            company_name="WaitingCo",
            role_title="Cluster Engineer",
            status="applied",
            last_activity_on="2026-07-01",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-action-12345678",
            company_name="ActionCo",
            role_title="SRE",
            status="follow_up_due",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-closed-12345678",
            company_name="ClosedCo",
            role_title="Linux Engineer",
            status="rejected",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker?sort=workflow")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert html.index("ActionCo") < html.index("WaitingCo")
    assert html.index("WaitingCo") < html.index("ClosedCo")


def test_tracker_page_defaults_to_applied_date_descending(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-old-12345678",
            company_name="OldCo",
            role_title="Linux Engineer",
            status="applied",
            applied_on="2026-05-01",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-new-12345678",
            company_name="NewCo",
            role_title="Platform Engineer",
            status="applied",
            applied_on="2026-07-05",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<option value="applied_desc" selected>' in html
    assert html.index("NewCo") < html.index("OldCo")


def test_tracker_page_sorts_by_company_status_role_and_outcome(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-zeta-12345678",
            company_name="ZetaCo",
            role_title="Linux Engineer",
            status="dormant",
            outcome="Dormant",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-alpha-12345678",
            company_name="AlphaCo",
            role_title="Platform Engineer",
            status="applied",
            outcome="Pending / In Progress",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    company_response = client.get("/tracker?sort=company")
    company_html = company_response.get_data(as_text=True)
    assert company_response.status_code == 200
    assert '<option value="company" selected>' in company_html
    assert company_html.index("AlphaCo") < company_html.index("ZetaCo")

    role_response = client.get("/tracker?sort=role")
    role_html = role_response.get_data(as_text=True)
    assert role_response.status_code == 200
    assert '<option value="role" selected>' in role_html
    assert role_html.index("Linux Engineer") < role_html.index("Platform Engineer")

    status_response = client.get("/tracker?sort=status")
    status_html = status_response.get_data(as_text=True)
    assert status_response.status_code == 200
    assert '<option value="status" selected>' in status_html
    assert status_html.index("AlphaCo") < status_html.index("ZetaCo")

    outcome_response = client.get("/tracker?sort=outcome")
    outcome_html = outcome_response.get_data(as_text=True)
    assert outcome_response.status_code == 200
    assert '<option value="outcome" selected>' in outcome_html
    assert outcome_html.index("ZetaCo") < outcome_html.index("AlphaCo")


def test_tracker_page_sorts_by_applied_date_descending(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-old-12345678",
            company_name="OldCo",
            role_title="Linux Engineer",
            status="applied",
            applied_on="2026-05-01",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-new-12345678",
            company_name="NewCo",
            role_title="Platform Engineer",
            status="applied",
            applied_on="2026-07-05",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker?sort=applied_desc")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Applied date newest first" in html
    assert html.index("NewCo") < html.index("OldCo")


def test_tracker_page_sorts_by_applied_date_ascending(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-old-12345678",
            company_name="OldCo",
            role_title="Linux Engineer",
            status="applied",
            applied_on="2026-05-01",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-new-12345678",
            company_name="NewCo",
            role_title="Platform Engineer",
            status="applied",
            applied_on="2026-07-05",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker?sort=applied_asc")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Applied date oldest first" in html
    assert html.index("OldCo") < html.index("NewCo")


def test_tracker_page_searches_tracker_text(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-hpc-12345678",
            company_name="Hydra Host",
            role_title="HPC Solutions Engineer",
            status="applied",
            notes="GPU, InfiniBand, Slurm, and distributed machine learning.",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-platform-12345678",
            company_name="PlatformCo",
            role_title="Platform Engineer",
            status="applied",
            notes="Generic platform role.",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker?q=infiniband")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Applications shown:</strong> 1" in html
    assert "Hydra Host" in html
    assert "PlatformCo" not in html


def test_tracker_filter_links_preserve_search_sort_and_field_filters(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-hpc-12345678",
            company_name="Hydra Host",
            role_title="HPC Solutions Engineer",
            status="applied",
            outcome="Pending / In Progress",
            notes="InfiniBand and Slurm fit.",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get(
        "/tracker",
        query_string={
            "filter": "needs_review",
            "sort": "company",
            "q": "hpc",
            "status_filter": "Applied",
            "outcome_filter": "Pending / In Progress",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "/tracker?filter=all" in html
    assert "/tracker?filter=active" in html
    assert "status_filter=Applied" in html
    assert "outcome_filter=Pending+" in html
    assert 'value="hpc"' in html
    assert '<option value="Applied" selected>' in html
    assert '<option value="Pending / In Progress" selected>' in html
    assert '<option value="company" selected>' in html


def test_tracker_page_filters_by_status_and_outcome(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-active-12345678",
            company_name="ActiveCo",
            role_title="Platform Engineer",
            status="applied",
            outcome="Pending / In Progress",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-rejected-12345678",
            company_name="RejectedCo",
            role_title="Linux Engineer",
            status="rejected",
            outcome="Rejected - No Interview",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get(
        "/tracker",
        query_string={
            "status_filter": "Applied",
            "outcome_filter": "Pending / In Progress",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Applications shown:</strong> 1" in html
    assert "ActiveCo" in html
    assert "RejectedCo" not in html
    assert '<option value="Applied" selected>' in html
    assert '<option value="Pending / In Progress" selected>' in html
    assert '<option value="Passed"' in html
    assert '<option value="Withdrawn"' in html
    assert '<option value="Revisit"' in html
    assert '<option value="Rejected - No Interview"' in html
    assert "Clear search/field filters/sort" in html


def test_tracker_page_rejects_unknown_sort(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker?sort=unknown")

    assert response.status_code == 404


def test_tracker_page_filters_to_needs_action(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-action-12345678",
            company_name="ActionCo",
            role_title="SRE",
            status="follow_up_due",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-waiting-12345678",
            company_name="WaitingCo",
            role_title="Cluster Engineer",
            status="applied",
            last_activity_on="2026-07-01",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker?filter=needs_action")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Applications shown:</strong> 1" in html
    assert "ActionCo" in html
    assert "WaitingCo" not in html


def test_tracker_page_filters_to_needs_review(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)

    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-stale-12345678",
            company_name="StaleCo",
            role_title="Platform Engineer",
            status="applied",
            last_activity_on="2026-03-01",
        ),
    )
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-waiting-12345678",
            company_name="WaitingCo",
            role_title="Cluster Engineer",
            status="applied",
            last_activity_on="2026-07-01",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker?filter=needs_review")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Applications shown:</strong> 1" in html
    assert "StaleCo" in html
    assert "WaitingCo" not in html


def test_tracker_edit_page_shows_application_form(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
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
            applied_on="2026-07-03",
            last_activity_on="2026-07-05",
            outcome="Interviewing",
            notes="Applied through company site.",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker/jr-stack-av-12345678/edit?filter=needs_action")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Edit Application" in html
    assert "Stack AV" in html
    assert "Senior Site Reliability Engineer" in html
    assert 'name="return_filter" value="needs_action"' in html
    assert '<option value="applied" selected>' in html
    assert 'name="follow_up_on" value="2026-07-10"' in html
    assert 'name="applied_on" value="2026-07-03"' in html
    assert 'name="last_activity_on" value="2026-07-05"' in html
    assert '<option value="Interviewing" selected>' in html
    assert "Applied through company site." in html


def test_tracker_edit_page_updates_application_and_redirects(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
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
            applied_on="2026-07-03",
            last_activity_on="2026-07-05",
            outcome="Interviewing",
            notes="Applied through company site.",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.post(
        "/tracker/jr-stack-av-12345678/edit",
        data={
            "return_filter": "needs_action",
            "status": "rejected",
            "follow_up_on": "",
            "applied_on": "2026-07-03",
            "last_activity_on": "2026-07-12",
            "outcome": "Rejected - No Interview",
            "notes": "Rejected by email.",
        },
    )

    application = get_application(database_file, "jr-stack-av-12345678")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/tracker?filter=needs_action")
    assert application is not None
    assert application.status == "rejected"
    assert application.applied_on == "2026-07-03"
    assert application.last_activity_on == "2026-07-12"
    assert application.outcome == "Rejected - No Interview"
    assert application.notes == "Rejected by email."


def test_tracker_edit_quick_action_marks_application_rejected(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)
    initialize_database(database_file)
    upsert_application(
        database_file,
        ApplicationRecord(
            job_radar_id="jr-stack-av-12345678",
            company_name="Stack AV",
            role_title="Senior Site Reliability Engineer",
            status="applied",
            outcome="Pending / In Progress",
            notes="Applied through company site.",
        ),
    )

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.post(
        "/tracker/jr-stack-av-12345678/edit",
        data={
            "return_filter": "needs_review",
            "status": "applied",
            "follow_up_on": "",
            "applied_on": "",
            "last_activity_on": "2026-07-12",
            "outcome": "Pending / In Progress",
            "notes": "Rejected by email.",
            "quick_action": "rejected",
        },
    )

    application = get_application(database_file, "jr-stack-av-12345678")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/tracker?filter=needs_review")
    assert application is not None
    assert application.status == "rejected"
    assert application.last_activity_on == "2026-07-12"
    assert application.outcome == "Rejected - No Interview"
    assert application.notes == "Rejected by email."


def test_tracker_page_links_to_add_application(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<a href="/tracker/add">Add application</a>' in html


def test_tracker_add_page_shows_application_form(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker/add")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Add Application" in html
    assert 'name="job_radar_id"' in html
    assert 'name="company_name"' in html
    assert 'name="role_title"' in html
    assert 'name="source_url"' in html
    assert '<option value="applied" selected>' in html
    assert '<option value="Pending / In Progress" selected>' in html
    assert 'name="follow_up_on"' in html
    assert 'name="applied_on"' in html
    assert 'name="last_activity_on"' in html
    assert 'name="notes"' in html


def test_tracker_add_page_saves_application_and_redirects(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.post(
        "/tracker/add",
        data={
            "job_radar_id": "jr-manual-example-12345678",
            "company_name": "ManualCo",
            "role_title": "Senior Infrastructure Engineer",
            "source_url": "https://example.com/jobs/manual",
            "status": "applied",
            "follow_up_on": "2026-07-15",
            "applied_on": "2026-07-05",
            "last_activity_on": "2026-07-05",
            "outcome": "Pending / In Progress",
            "notes": "Added manually from GUI.",
        },
    )

    application = get_application(database_file, "jr-manual-example-12345678")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/tracker?filter=all")
    assert application is not None
    assert application.company_name == "ManualCo"
    assert application.role_title == "Senior Infrastructure Engineer"
    assert application.source_url == "https://example.com/jobs/manual"
    assert application.status == "applied"
    assert application.follow_up_on == "2026-07-15"
    assert application.applied_on == "2026-07-05"
    assert application.last_activity_on == "2026-07-05"
    assert application.outcome == "Pending / In Progress"
    assert application.notes == "Added manually from GUI."
