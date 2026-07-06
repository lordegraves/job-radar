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

    response = client.get("/tracker")
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

    response = client.get("/tracker")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert html.index("ActionCo") < html.index("WaitingCo")
    assert html.index("WaitingCo") < html.index("ClosedCo")


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


def test_tracker_filter_links_preserve_search_and_sort(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    database_file = tmp_path / "job_radar.sqlite3"

    write_settings_file(settings_file, database_file)

    app = create_app(settings_path=str(settings_file))
    client = app.test_client()

    response = client.get("/tracker?filter=needs_review&sort=applied_desc&q=hpc")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "/tracker?filter=all&amp;sort=applied_desc&amp;q=hpc" in html
    assert "/tracker?filter=active&amp;sort=applied_desc&amp;q=hpc" in html
    assert 'value="hpc"' in html
    assert '<option value="applied_desc" selected>' in html


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
