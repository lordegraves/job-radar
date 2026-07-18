"""Verify desktop startup, workspace ownership, readiness, and error handling.

Browser and server interactions are replaced with controlled test doubles so
the suite can prove launcher decisions without opening a real browser or using
the operator's live Job Radar workspace.
"""

import sys
from pathlib import Path
from typing import Any

import pytest

from job_radar import desktop_launcher
from job_radar.runtime_paths import UserDataPaths


def test_ensure_desktop_workspace_bootstraps_packaged_defaults(
    tmp_path: Path,
) -> None:
    user_data_paths = UserDataPaths.from_root(tmp_path / "JobRadar")

    settings_path = desktop_launcher.ensure_desktop_workspace(
        user_data_paths,
    )

    assert settings_path.is_file()
    assert (
        user_data_paths.config / "target-companies.yaml"
    ).is_file()
    assert (user_data_paths.config / "scoring.yaml").is_file()
    assert user_data_paths.data.is_dir()
    assert user_data_paths.logs.is_dir()
    assert user_data_paths.profiles.is_dir()
    assert user_data_paths.reports.is_dir()


def test_ensure_desktop_workspace_preserves_existing_settings(
    tmp_path: Path,
) -> None:
    user_data_paths = UserDataPaths.from_root(tmp_path / "JobRadar")
    settings_path = user_data_paths.config / "settings.yaml"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        "existing user settings\n",
        encoding="utf-8",
    )

    resolved_settings_path = desktop_launcher.ensure_desktop_workspace(
        user_data_paths,
    )

    assert resolved_settings_path == settings_path
    assert settings_path.read_text(encoding="utf-8") == (
        "existing user settings\n"
    )


@pytest.mark.parametrize(
    ("host", "expected_url"),
    [
        ("127.0.0.1", "http://127.0.0.1:5000/"),
        ("localhost", "http://localhost:5000/"),
        ("0.0.0.0", "http://127.0.0.1:5000/"),
        ("::", "http://127.0.0.1:5000/"),
    ],
)
def test_build_local_url_uses_browser_safe_host(
    host: str,
    expected_url: str,
) -> None:
    assert desktop_launcher.build_local_url(host, 5000) == expected_url


def test_main_reuses_running_job_radar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened_urls: list[str] = []

    monkeypatch.setattr(
        sys,
        "argv",
        ["job-radar-desktop"],
    )
    monkeypatch.setattr(
        desktop_launcher,
        "is_job_radar_running",
        lambda _url: True,
    )
    monkeypatch.setattr(
        desktop_launcher.webbrowser,
        "open",
        lambda url: opened_urls.append(url),
    )
    monkeypatch.setattr(
        desktop_launcher,
        "ensure_desktop_workspace",
        lambda: pytest.fail("workspace should not be bootstrapped"),
    )

    desktop_launcher.launch_desktop()

    assert opened_urls == ["http://127.0.0.1:5000/"]


def test_main_bootstraps_starts_and_opens_job_radar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    fake_app = object()
    fake_server = object()
    calls: dict[str, Any] = {}

    monkeypatch.setattr(
        sys,
        "argv",
        ["job-radar-desktop"],
    )
    monkeypatch.setattr(
        desktop_launcher,
        "is_job_radar_running",
        lambda _url: False,
    )
    monkeypatch.setattr(
        desktop_launcher,
        "ensure_desktop_workspace",
        lambda: settings_path,
    )
    monkeypatch.setattr(
        desktop_launcher,
        "create_app",
        lambda *, settings_path, base_directory: (
            calls.update(
                {
                    "settings_path": settings_path,
                    "base_directory": base_directory,
                }
            ),
            fake_app,
        )[1],
    )
    monkeypatch.setattr(
        desktop_launcher,
        "make_server",
        lambda host, port, app: (
            calls.update(
                {
                    "host": host,
                    "port": port,
                    "app": app,
                }
            ),
            fake_server,
        )[1],
    )
    monkeypatch.setattr(
        desktop_launcher,
        "run_desktop_server",
        lambda server, *, url, open_browser: calls.update(
            {
                "server": server,
                "url": url,
                "open_browser": open_browser,
            }
        ),
    )

    desktop_launcher.launch_desktop()

    assert calls == {
        "settings_path": settings_path,
        "base_directory": tmp_path,
        "host": "127.0.0.1",
        "port": 5000,
        "app": fake_app,
        "server": fake_server,
        "url": "http://127.0.0.1:5000/",
        "open_browser": True,
    }


def test_main_no_browser_starts_without_opening_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    fake_server = object()
    calls: dict[str, Any] = {}

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "job-radar-desktop",
            "--no-browser",
        ],
    )
    monkeypatch.setattr(
        desktop_launcher,
        "is_job_radar_running",
        lambda _url: False,
    )
    monkeypatch.setattr(
        desktop_launcher,
        "ensure_desktop_workspace",
        lambda: settings_path,
    )
    monkeypatch.setattr(
        desktop_launcher,
        "create_app",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(
        desktop_launcher,
        "make_server",
        lambda *_args: fake_server,
    )
    monkeypatch.setattr(
        desktop_launcher,
        "run_desktop_server",
        lambda server, *, url, open_browser: calls.update(
            {
                "server": server,
                "url": url,
                "open_browser": open_browser,
            }
        ),
    )

    desktop_launcher.launch_desktop()

    assert calls == {
        "server": fake_server,
        "url": "http://127.0.0.1:5000/",
        "open_browser": False,
    }


def test_wait_until_ready_reports_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = iter([0.0, 0.0, 0.05, 0.1])

    monkeypatch.setattr(
        desktop_launcher.time,
        "monotonic",
        lambda: next(times),
    )
    monkeypatch.setattr(
        desktop_launcher.time,
        "sleep",
        lambda _seconds: None,
    )
    monkeypatch.setattr(
        desktop_launcher,
        "is_job_radar_running",
        lambda _url: False,
    )

    with pytest.raises(
        RuntimeError,
        match="interface did not become available",
    ):
        desktop_launcher.wait_until_ready(
            "http://127.0.0.1:5000/",
            timeout_seconds=0.1,
        )


def test_main_shows_graphical_support_error_for_unexpected_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostic_log_path = tmp_path / "logs" / "startup-errors.log"
    shown_messages: list[str] = []

    monkeypatch.setattr(
        desktop_launcher,
        "launch_desktop",
        lambda: (_ for _ in ()).throw(
            RuntimeError("private unexpected detail")
        ),
    )
    monkeypatch.setattr(
        desktop_launcher,
        "_write_startup_diagnostic_log",
        lambda *_args, **_kwargs: diagnostic_log_path,
    )
    monkeypatch.setattr(
        desktop_launcher,
        "show_desktop_error",
        lambda message: shown_messages.append(message),
    )

    with pytest.raises(SystemExit) as exit_error:
        desktop_launcher.main()

    assert exit_error.value.code == 1
    assert len(shown_messages) == 1

    message = shown_messages[0]

    assert "Job Radar could not start" in message
    assert "claytonmgraves@outlook.com" in message
    assert str(diagnostic_log_path) in message
    assert "Error type: RuntimeError" in message
    assert "private unexpected detail" not in message
    assert "exception message was omitted" in message


def test_show_desktop_error_uses_windows_message_box(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, str, str, int]] = []

    class FakeUser32:
        def MessageBoxW(
            self,
            parent: object,
            message: str,
            title: str,
            flags: int,
        ) -> None:
            calls.append((parent, message, title, flags))

    class FakeWindll:
        user32 = FakeUser32()

    monkeypatch.setattr(desktop_launcher.sys, "platform", "win32")
    monkeypatch.setattr(desktop_launcher.ctypes, "windll", FakeWindll())

    desktop_launcher.show_desktop_error("Helpful failure message")

    assert calls == [
        (
            None,
            "Helpful failure message",
            "Job Radar could not start",
            0x00000010,
        )
    ]


def test_show_desktop_error_falls_back_to_standard_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(desktop_launcher.sys, "platform", "linux")

    desktop_launcher.show_desktop_error("Helpful failure message")

    captured = capsys.readouterr()

    assert captured.out == ""
    assert "Job Radar could not start" in captured.err
    assert "Helpful failure message" in captured.err
