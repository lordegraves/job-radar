"""Verify durable scan scheduling with only fictional, disposable data."""

from datetime import datetime
from pathlib import Path

import pytest

from job_radar.database import connect_database
from job_radar.schedule_service import (
    ScanSchedule,
    ScheduleIntegrationStatus,
    ScheduleError,
    build_schedule_view,
    calculate_next_run,
    load_scan_schedule,
    save_scan_schedule,
)
from job_radar.storage import complete_scan_run, start_scan_run
from job_radar.web_app import create_app


def _write_settings(path: Path) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(
        """
database_path: data/junior.sqlite3
reports_path: reports
logs_path: logs
email:
  enabled: false
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_schedule_defaults_off_and_has_no_next_run(tmp_path: Path) -> None:
    database_path = tmp_path / "junior.sqlite3"

    view = build_schedule_view(database_path)

    assert view.schedule == ScanSchedule(
        enabled=False,
        run_time="09:00",
        weekdays=(),
        email_delivery=False,
    )
    assert view.next_run == "Scheduling is off"
    assert view.last_run.status == "Not run yet"


def test_save_schedule_normalizes_weekday_order_and_calculates_next_run(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"

    saved = save_scan_schedule(
        database_path,
        enabled=True,
        run_time="08:30",
        weekdays=["friday", "monday"],
        email_delivery=True,
    )
    next_run = calculate_next_run(
        saved,
        now=datetime(2026, 7, 20, 9, 0),
    )

    assert saved.weekdays == ("monday", "friday")
    assert load_scan_schedule(database_path) == saved
    assert next_run == datetime(2026, 7, 24, 8, 30)


def test_enabled_schedule_requires_a_weekday(tmp_path: Path) -> None:
    with pytest.raises(
        ScheduleError,
        match="Choose at least one weekday",
    ):
        save_scan_schedule(
            tmp_path / "junior.sqlite3",
            enabled=True,
            run_time="09:00",
            weekdays=[],
            email_delivery=False,
        )


def test_schedule_view_reports_last_scheduled_failure_without_raw_details(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    save_scan_schedule(
        database_path,
        enabled=False,
        run_time="09:00",
        weekdays=[],
        email_delivery=False,
    )
    scan_run_id = start_scan_run(
        database_path,
        requested_at="2026-07-23T13:00:00+00:00",
        companies_requested=1,
        companies_enabled=1,
        trigger_source="scheduled",
    )
    with connect_database(database_path) as connection:
        connection.execute(
            """
            UPDATE scan_runs
            SET status = 'failed',
                finished_at = '2026-07-23T13:02:00+00:00',
                failure_summary = 'private internal failure text'
            WHERE id = ?
            """,
            (scan_run_id,),
        )

    view = build_schedule_view(database_path)

    assert view.last_run.status == "Failed"
    assert "private internal failure text" not in view.last_run.message
    assert view.last_run.message == (
        "The last scheduled scan did not finish. "
        "Open Scan for safe failure details."
    )


def test_schedule_page_saves_and_discloses_automation_boundary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    _write_settings(settings_path)
    monkeypatch.setattr(
        "job_radar.web_routes.settings.inspect_scheduler",
        lambda: ScheduleIntegrationStatus(
            platform_name="Windows",
            available=True,
            installed=False,
            enabled=False,
            state="Not installed",
            message="Junior's Windows scheduled task is not installed.",
        ),
    )
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    client = app.test_client()

    page = client.get("/settings?section=schedule")
    saved = client.post(
        "/settings/schedule",
        data={
            "enabled": "yes",
            "run_time": "07:15",
            "weekdays": ["monday", "wednesday", "friday"],
            "email_delivery": "yes",
        },
        follow_redirects=True,
    )

    assert page.status_code == 200
    assert "When Junior should scan" in page.get_data(as_text=True)
    assert "Windows connection" in page.get_data(as_text=True)
    assert "Apply schedule to Windows" in page.get_data(as_text=True)
    assert "Junior does not need to be open." in page.get_data(as_text=True)
    assert "computer is locked" in page.get_data(as_text=True)
    assert "signed in" in page.get_data(as_text=True)
    html = saved.get_data(as_text=True)
    assert "Scan schedule saved." in html
    assert 'value="07:15"' in html
    assert load_scan_schedule(tmp_path / "data" / "junior.sqlite3").weekdays == (
        "monday",
        "wednesday",
        "friday",
    )


def test_schedule_page_can_apply_disable_and_remove_windows_task(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    _write_settings(settings_path)
    calls: list[str] = []
    monkeypatch.setattr(
        "job_radar.web_routes.settings.inspect_scheduler",
        lambda: ScheduleIntegrationStatus(
            platform_name="Windows",
            available=True,
            installed=True,
            enabled=True,
            state="Installed and enabled",
            message="Windows is ready.",
        ),
    )
    monkeypatch.setattr(
        "job_radar.web_routes.settings.apply_scheduler",
        lambda schedule, user_data_root: calls.append("apply")
        or "Windows task updated.",
    )
    monkeypatch.setattr(
        "job_radar.web_routes.settings.disable_scheduler",
        lambda: calls.append("disable") or "Windows task disabled.",
    )
    monkeypatch.setattr(
        "job_radar.web_routes.settings.remove_scheduler",
        lambda: calls.append("remove") or "Windows task removed.",
    )
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    client = app.test_client()

    responses = [
        client.post(path, follow_redirects=True)
        for path in (
            "/settings/schedule/system/apply",
            "/settings/schedule/system/disable",
            "/settings/schedule/system/remove",
        )
    ]

    assert calls == ["apply", "disable", "remove"]
    assert all(response.status_code == 200 for response in responses)
    assert "Windows task updated." in responses[0].get_data(as_text=True)
    assert "Windows task disabled." in responses[1].get_data(as_text=True)
    assert "Windows task removed." in responses[2].get_data(as_text=True)


def test_manual_scan_does_not_appear_as_last_scheduled_run(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    save_scan_schedule(
        database_path,
        enabled=False,
        run_time="09:00",
        weekdays=[],
        email_delivery=False,
    )
    run_id = start_scan_run(
        database_path,
        requested_at="2026-07-23T13:00:00+00:00",
        companies_requested=0,
        companies_enabled=0,
    )
    complete_scan_run(
        database_path,
        scan_run_id=run_id,
        generated_at="2026-07-23T13:00:01+00:00",
        finished_at="2026-07-23T13:00:02+00:00",
        companies_scanned=0,
        jobs_collected=0,
        actionable_jobs_stored=0,
        jobs_not_actionable=0,
        jobs_new=0,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=0,
        top_matches_count=0,
        review_needed_count=0,
        report_status="completed",
        email_status="not_requested",
    )

    assert build_schedule_view(database_path).last_run.status == "Not run yet"
