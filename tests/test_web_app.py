from pathlib import Path

from job_radar.storage import initialize_database
from job_radar.tracker.models import ApplicationRecord
from job_radar.tracker.storage import get_application, upsert_application
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
    assert "Applications shown:</strong> 1" in html
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
    assert "Applications shown:</strong> 0" in html
    assert "No tracked applications." in html


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

    response = client.get("/tracker")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert html.index("ActionCo") < html.index("WaitingCo")
    assert html.index("WaitingCo") < html.index("ClosedCo")


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
            outcome="interviewing",
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
    assert 'name="status" value="applied"' in html
    assert 'name="follow_up_on" value="2026-07-10"' in html
    assert 'name="applied_on" value="2026-07-03"' in html
    assert 'name="last_activity_on" value="2026-07-05"' in html
    assert 'name="outcome" value="interviewing"' in html
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
            outcome="interviewing",
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
