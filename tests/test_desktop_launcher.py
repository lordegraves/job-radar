"""Verify desktop startup, workspace ownership, readiness, and error handling.

Browser and server interactions are replaced with controlled test doubles so
the suite can prove launcher decisions without opening a real browser or using
the operator's live Job Radar workspace.
"""

import sys
import threading
from pathlib import Path
from types import SimpleNamespace
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened_urls: list[str] = []
    settings_path = tmp_path / "config" / "settings.yaml"

    monkeypatch.setattr(
        sys,
        "argv",
        ["job-radar-desktop", "--browser"],
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
        lambda: settings_path,
    )

    desktop_launcher.launch_desktop()

    assert opened_urls == ["http://127.0.0.1:5000/"]


def test_second_launcher_uses_locked_workspace_instance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    lock_path = tmp_path / "runtime" / desktop_launcher.INSTANCE_LOCK_NAME
    readiness_urls: list[str] = []
    notices: list[str] = []

    monkeypatch.setattr(
        sys,
        "argv",
        ["job-radar-desktop", "--port", "5999"],
    )
    monkeypatch.setattr(
        desktop_launcher,
        "ensure_desktop_workspace",
        lambda: settings_path,
    )
    monkeypatch.setattr(
        desktop_launcher,
        "wait_until_ready",
        lambda url: readiness_urls.append(url),
    )
    monkeypatch.setattr(
        desktop_launcher,
        "show_desktop_notice",
        lambda message: notices.append(message),
    )
    monkeypatch.setattr(
        desktop_launcher,
        "is_job_radar_running",
        lambda _url: pytest.fail("second instance must not probe another port"),
    )

    with desktop_launcher.DesktopInstanceLock(
        lock_path,
        "http://127.0.0.1:5019/",
    ) as first_instance:
        assert first_instance.acquired
        desktop_launcher.launch_desktop()

    assert readiness_urls == ["http://127.0.0.1:5019/"]
    assert notices == [
        "Junior is already open. Return to the existing Junior window."
    ]


def test_main_bootstraps_starts_native_job_radar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    fake_server = object()
    calls: dict[str, Any] = {}
    fake_runner = SimpleNamespace(
        wait=lambda: calls.update({"scan_waited": True})
    )
    fake_app = SimpleNamespace(
        config={},
        extensions={"junior_scan_runner": fake_runner},
    )

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
        "run_native_window",
        lambda server, *, url, shutdown_event, window_state_path: calls.update(
            {
                "server": server,
                "url": url,
                "shutdown_event": shutdown_event,
                "window_state_path": window_state_path,
            }
        ),
    )

    desktop_launcher.launch_desktop()

    shutdown_event = calls.pop("shutdown_event")
    assert isinstance(shutdown_event, desktop_launcher.threading.Event)
    assert calls == {
        "settings_path": settings_path,
        "base_directory": tmp_path,
        "host": "127.0.0.1",
        "port": 5000,
        "app": fake_app,
        "server": fake_server,
        "url": "http://127.0.0.1:5000/",
        "window_state_path": tmp_path
        / "runtime"
        / desktop_launcher.WINDOW_STATE_NAME,
        "scan_waited": True,
    }


def test_main_no_browser_starts_without_opening_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    fake_server = object()
    calls: dict[str, Any] = {}
    fake_app = SimpleNamespace(
        config={},
        extensions={
            "junior_scan_runner": SimpleNamespace(
                wait=lambda: calls.update({"scan_waited": True})
            )
        },
    )

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
        lambda **_kwargs: fake_app,
    )
    monkeypatch.setattr(
        desktop_launcher,
        "make_server",
        lambda *_args: fake_server,
    )
    monkeypatch.setattr(
        desktop_launcher,
        "run_desktop_server",
        lambda server, *, url, open_browser, shutdown_event: calls.update(
            {
                "server": server,
                "url": url,
                "open_browser": open_browser,
                "shutdown_event": shutdown_event,
            }
        ),
    )

    desktop_launcher.launch_desktop()

    shutdown_event = calls.pop("shutdown_event")
    assert isinstance(shutdown_event, desktop_launcher.threading.Event)
    assert calls == {
        "server": fake_server,
        "url": "http://127.0.0.1:5000/",
        "open_browser": False,
        "scan_waited": True,
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


def test_native_window_uses_shared_url_icon_and_normal_chrome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shutdown_event = threading.Event()
    server_stopped = threading.Event()
    calls: dict[str, Any] = {}

    class FakeServer:
        def serve_forever(self) -> None:
            server_stopped.wait(timeout=2)

        def shutdown(self) -> None:
            server_stopped.set()

    class FakeEvent:
        def __init__(self) -> None:
            self.handlers: list[object] = []

        def __iadd__(self, handler: object) -> "FakeEvent":
            self.handlers.append(handler)
            return self

    class FakeEvents:
        closing = FakeEvent()

    class FakeWindow:
        events = FakeEvents()
        width = 1440
        height = 900
        x = 120
        y = 80

        def destroy(self) -> None:
            calls["destroyed"] = True

    class FakeWebview:
        settings: dict[str, object] = {}

        @staticmethod
        def create_window(title: str, url: str, **kwargs: Any) -> FakeWindow:
            calls["window"] = (title, url, kwargs)
            return FakeWindow()

        @staticmethod
        def start(**kwargs: Any) -> None:
            calls["start"] = kwargs

    monkeypatch.setattr(
        desktop_launcher,
        "wait_until_ready",
        lambda _url: None,
    )
    icon_path = tmp_path / "junior.ico"
    monkeypatch.setattr(
        desktop_launcher,
        "_desktop_icon_path",
        lambda: icon_path,
    )

    desktop_launcher.run_native_window(
        FakeServer(),
        url="http://127.0.0.1:5000/",
        shutdown_event=shutdown_event,
        window_state_path=tmp_path / "runtime" / "desktop-window.json",
        webview_module=FakeWebview,
    )

    title, url, options = calls["window"]
    assert title == "Junior — SP5 Build 1.5"
    assert url == "http://127.0.0.1:5000/"
    assert options["resizable"] is True
    assert options["min_size"] == (960, 640)
    assert options["width"] == 1440
    assert options["height"] == 900
    assert options["x"] is None
    assert options["y"] is None
    assert options["background_color"] == "#101114"
    assert len(FakeEvents.closing.handlers) == 1
    assert calls["start"] == {
        "icon": str(icon_path),
        "private_mode": True,
    }
    assert FakeWebview.settings["ALLOW_DOWNLOADS"] is True
    assert shutdown_event.is_set()
    assert server_stopped.is_set()

    monkeypatch.setattr(desktop_launcher.sys, "platform", "linux")
    assert desktop_launcher._webview_start_options() == {
        "icon": str(icon_path),
        "private_mode": True,
    }
    monkeypatch.setattr(desktop_launcher.sys, "platform", "darwin")
    assert desktop_launcher._webview_start_options() == {
        "private_mode": True,
    }


def test_window_state_round_trip_and_invalid_state_falls_back(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "runtime" / "desktop-window.json"

    assert desktop_launcher.load_window_state(state_path) == {
        "width": 1440,
        "height": 900,
    }

    desktop_launcher.save_window_state(
        state_path,
        width=1440,
        height=900,
        x=90,
        y=45,
    )

    assert desktop_launcher.load_window_state(state_path) == {
        "width": 1440,
        "height": 900,
        "x": 90,
        "y": 45,
    }

    state_path.write_text(
        '{"width":200,"height":100,"x":0,"y":0}\n',
        encoding="utf-8",
    )

    assert desktop_launcher.load_window_state(state_path) == {
        "width": 1440,
        "height": 900,
    }


def test_native_window_restores_and_saves_geometry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shutdown_event = threading.Event()
    server_stopped = threading.Event()
    calls: dict[str, Any] = {}
    state_path = tmp_path / "runtime" / "desktop-window.json"
    desktop_launcher.save_window_state(
        state_path,
        width=1460,
        height=910,
        x=130,
        y=75,
    )

    class FakeServer:
        def serve_forever(self) -> None:
            server_stopped.wait(timeout=2)

        def shutdown(self) -> None:
            server_stopped.set()

    class FakeEvent:
        def __init__(self) -> None:
            self.handlers: list[object] = []

        def __iadd__(self, handler: object) -> "FakeEvent":
            self.handlers.append(handler)
            return self

    class FakeEvents:
        closing = FakeEvent()

    class FakeWindow:
        events = FakeEvents()
        width = 1510
        height = 940
        x = 160
        y = 100

        def destroy(self) -> None:
            pass

    class FakeWebview:
        settings: dict[str, object] = {}

        @staticmethod
        def create_window(title: str, url: str, **kwargs: Any) -> FakeWindow:
            calls["window"] = (title, url, kwargs)
            return FakeWindow()

        @staticmethod
        def start(**_kwargs: Any) -> None:
            for handler in FakeEvents.closing.handlers:
                handler()

    monkeypatch.setattr(
        desktop_launcher,
        "wait_until_ready",
        lambda _url: None,
    )

    desktop_launcher.run_native_window(
        FakeServer(),
        url="http://127.0.0.1:5000/",
        shutdown_event=shutdown_event,
        window_state_path=state_path,
        webview_module=FakeWebview,
    )

    _, _, options = calls["window"]
    assert options["width"] == 1460
    assert options["height"] == 910
    assert options["x"] == 130
    assert options["y"] == 75
    assert desktop_launcher.load_window_state(state_path) == {
        "width": 1510,
        "height": 940,
        "x": 160,
        "y": 100,
    }


def test_windows_native_window_sets_junior_taskbar_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identities: list[str] = []

    class FakeShell32:
        @staticmethod
        def SetCurrentProcessExplicitAppUserModelID(identity: str) -> None:
            identities.append(identity)

    class FakeWindll:
        shell32 = FakeShell32()

    monkeypatch.setattr(desktop_launcher.sys, "platform", "win32")
    monkeypatch.setattr(desktop_launcher.ctypes, "windll", FakeWindll())

    desktop_launcher.set_windows_app_identity()

    assert identities == ["Junior.JobRadar"]


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

    assert "junior could not start" in message
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
            "junior could not start",
            0x00000010,
        )
    ]


def test_show_desktop_error_falls_back_to_standard_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class UnavailableWebview:
        @staticmethod
        def create_window(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("GUI toolkit unavailable")

    monkeypatch.setattr(desktop_launcher.sys, "platform", "linux")

    desktop_launcher.show_desktop_error(
        "Helpful failure message",
        webview_module=UnavailableWebview,
    )

    captured = capsys.readouterr()

    assert captured.out == ""
    assert "junior could not start" in captured.err
    assert "Helpful failure message" in captured.err


def test_non_windows_startup_error_uses_safe_graphical_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    class FakeWebview:
        @staticmethod
        def create_window(title: str, **kwargs: Any) -> None:
            calls["window"] = (title, kwargs)

        @staticmethod
        def start(**kwargs: Any) -> None:
            calls["start"] = kwargs

    monkeypatch.setattr(desktop_launcher.sys, "platform", "linux")

    desktop_launcher.show_desktop_error(
        "Safe guidance <without raw markup>",
        webview_module=FakeWebview,
    )

    title, options = calls["window"]
    assert title == "Junior could not start"
    assert "Safe guidance &lt;without raw markup&gt;" in options["html"]
    assert calls["start"] == {"private_mode": True}
