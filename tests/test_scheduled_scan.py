"""Verify the unattended entry point reuses the shared scan service safely."""

from pathlib import Path

from job_radar.schedule_service import save_scan_schedule
from job_radar.scheduled_scan import run_saved_schedule


def _write_settings(root: Path) -> Path:
    settings_path = root / "config" / "settings.yaml"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
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
    return settings_path


def test_scheduled_entrypoint_exits_when_schedule_is_off(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_settings(tmp_path)
    save_scan_schedule(
        tmp_path / "data" / "junior.sqlite3",
        enabled=False,
        run_time="08:00",
        weekdays=[],
        email_delivery=False,
    )
    calls = []
    monkeypatch.setattr(
        "job_radar.scheduled_scan.handle_scan",
        lambda **kwargs: calls.append(kwargs),
    )

    assert run_saved_schedule(user_data_root=tmp_path) is False
    assert calls == []


def test_scheduled_entrypoint_marks_origin_and_honors_email_choice(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_path = _write_settings(tmp_path)
    save_scan_schedule(
        tmp_path / "data" / "junior.sqlite3",
        enabled=True,
        run_time="08:00",
        weekdays=["monday"],
        email_delivery=True,
    )
    calls = []
    monkeypatch.setattr(
        "job_radar.scheduled_scan.handle_scan",
        lambda **kwargs: calls.append(kwargs),
    )

    assert run_saved_schedule(user_data_root=tmp_path) is True
    assert len(calls) == 1
    assert calls[0]["settings_path"] == str(settings_path)
    assert calls[0]["send_email"] is True
    assert calls[0]["trigger_source"] == "scheduled"
    assert calls[0]["base_directory"] == str(tmp_path)
