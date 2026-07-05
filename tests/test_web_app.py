from pathlib import Path

from job_radar.storage import initialize_database
from job_radar.tracker.models import ApplicationRecord
from job_radar.tracker.storage import upsert_application
from job_radar.web_app import create_app


def write_settings_file(settings_file: Path, database_file: Path) -> None:
    settings_file.write_text(
        f"""
database_path: {database_file}
reports_path: {settings_file.parent}
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
            outcome="interviewing",
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
    assert "Applications tracked:</strong> 1" in html
    assert "Stack AV" in html
    assert "Senior Site Reliability Engineer" in html
    assert "applied" in html
    assert "follow_up_scheduled" in html
    assert "2026-07-03" in html
    assert "2026-07-05" in html
    assert "2026-07-10" in html
    assert "interviewing" in html
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
    assert "Applications tracked:</strong> 0" in html
    assert "No tracked applications." in html