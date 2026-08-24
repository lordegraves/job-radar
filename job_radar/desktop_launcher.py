"""Launch Junior's shared local interface in a native desktop window.

The launcher prepares the user-owned workspace, starts a local-only web server,
waits for readiness, and then opens the native shell or requested browser mode.
It reuses an existing Junior instance and presents safe startup errors.
"""

import argparse
import ctypes
import hashlib
import html
import json
import multiprocessing
import os
import platform
import sys
import threading
import time
import webbrowser
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, BinaryIO
from urllib.error import URLError
from urllib.request import urlopen

import webview
from werkzeug.serving import BaseWSGIServer, make_server

from job_radar import __build__
from job_radar.runtime_paths import UserDataPaths
from job_radar.user_data_bootstrap import bootstrap_packaged_user_configuration
from job_radar.web_app import (
    _format_unexpected_startup_error,
    _write_startup_diagnostic_log,
    create_app,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000
DEFAULT_MACOS_PORT = 5050
DEFAULT_STARTUP_TIMEOUT_SECONDS = 10.0
DESKTOP_ERROR_TITLE = "junior could not start"
INSTANCE_LOCK_NAME = "desktop-instance.lock"
WINDOW_STATE_NAME = "desktop-window.json"
DEFAULT_WINDOW_WIDTH = 1440
DEFAULT_WINDOW_HEIGHT = 900
MINIMUM_WINDOW_WIDTH = 960
MINIMUM_WINDOW_HEIGHT = 640
MAXIMUM_WINDOW_WIDTH = 7680
MAXIMUM_WINDOW_HEIGHT = 4320


def default_desktop_port() -> int:
    """Avoid macOS AirPlay's normal port without changing other platforms."""

    if sys.platform == "darwin":
        return DEFAULT_MACOS_PORT
    return DEFAULT_PORT


class DesktopInstanceLock(AbstractContextManager["DesktopInstanceLock"]):
    """Hold one OS-managed lock for a Junior user-data workspace."""

    def __init__(self, path: Path, requested_url: str) -> None:
        self.path = path
        self.requested_url = requested_url
        self.existing_url: str | None = None
        self.acquired = False
        self._stream: BinaryIO | None = None

    def __enter__(self) -> "DesktopInstanceLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open("a+b")
        self._stream = stream
        if self.path.stat().st_size == 0:
            stream.seek(0)
            stream.write(b" ")
            stream.flush()
        stream.seek(0)
        try:
            _lock_stream(stream)
        except OSError:
            self.existing_url = _read_instance_url(stream)
            return self
        self.acquired = True
        stream.seek(0)
        stream.truncate()
        stream.write(b" ")
        stream.write(
            json.dumps({"url": self.requested_url}).encode("utf-8")
        )
        stream.flush()
        os.fsync(stream.fileno())
        return self

    def __exit__(self, *_args: object) -> None:
        if self._stream is None:
            return
        try:
            if self.acquired:
                self._stream.seek(0)
                _unlock_stream(self._stream)
        finally:
            self._stream.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="junior-desktop",
        description="Launch the junior desktop interface",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="Host interface for the local junior server",
    )
    parser.add_argument(
        "--port",
        default=default_desktop_port(),
        type=int,
        help="Port for the local junior server",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start junior without opening the default web browser",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Open junior in the default browser instead of its native window",
    )
    return parser


def ensure_desktop_workspace(
    user_data_paths: UserDataPaths | None = None,
) -> Path:
    resolved_user_data_paths = user_data_paths or UserDataPaths.default()
    settings_path = resolved_user_data_paths.config / "settings.yaml"

    if not settings_path.is_file():
        bootstrap_packaged_user_configuration(
            user_data_paths=resolved_user_data_paths,
        )

    return settings_path


def build_local_url(host: str, port: int) -> str:
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    return f"http://{browser_host}:{port}/"


def is_junior_running(url: str) -> bool:
    try:
        with urlopen(url, timeout=1.0) as response:
            response_text = response.read(65536).decode(
                "utf-8",
                errors="replace",
            )
    except (OSError, URLError):
        return False

    return response.status == 200 and "junior" in response_text


def wait_until_ready(
    url: str,
    *,
    timeout_seconds: float = DEFAULT_STARTUP_TIMEOUT_SECONDS,
) -> None:
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        if is_junior_running(url):
            return

        time.sleep(0.05)

    raise RuntimeError(
        "junior started its local server, but the interface did not become "
        f"available within {timeout_seconds:g} seconds."
    )


def run_desktop_server(
    server: BaseWSGIServer,
    *,
    url: str,
    open_browser: bool,
    shutdown_event: threading.Event | None = None,
) -> None:
    server_thread = threading.Thread(
        target=server.serve_forever,
        name="junior-local-server",
        daemon=True,
    )
    server_thread.start()

    try:
        wait_until_ready(url)

        if open_browser:
            webbrowser.open(url)

        if shutdown_event is None:
            server_thread.join()
        else:
            while server_thread.is_alive():
                if shutdown_event.wait(timeout=0.1):
                    server.shutdown()
                    break
            server_thread.join()
    except BaseException:
        server.shutdown()
        server_thread.join(timeout=5.0)
        raise


def run_native_window(
    server: BaseWSGIServer,
    *,
    url: str,
    shutdown_event: threading.Event,
    window_state_path: Path | None = None,
    settings_path: Path | None = None,
    webview_module: Any = webview,
) -> None:
    """Run the shared Flask UI inside one normal native application window."""
    set_windows_app_identity()
    server_thread = threading.Thread(
        target=server.serve_forever,
        name="junior-local-server",
        daemon=True,
    )
    server_thread.start()
    try:
        wait_until_ready(url)
        # pywebview disables attachment downloads by default. Junior enables
        # them so Download links use the platform's normal download workflow.
        webview_module.settings["ALLOW_DOWNLOADS"] = True
        window_state = load_window_state(window_state_path)
        window = webview_module.create_window(
            f"Junior — {__build__}",
            url,
            width=window_state["width"],
            height=window_state["height"],
            x=window_state.get("x"),
            y=window_state.get("y"),
            min_size=(960, 640),
            resizable=True,
            background_color="#101114",
            text_select=True,
        )

        if window_state_path is not None:
            window.events.closing += lambda: save_window_state(
                window_state_path,
                width=window.width,
                height=window.height,
                x=window.x,
                y=window.y,
            )

        def close_window_when_requested() -> None:
            shutdown_event.wait()
            try:
                window.destroy()
            except Exception:
                # The user may have already closed the native window.
                return

        close_monitor = threading.Thread(
            target=close_window_when_requested,
            name="junior-window-shutdown",
            daemon=True,
        )
        close_monitor.start()
        try:
            webview_module.start(**_webview_start_options())
        except Exception as error:
            # A failed native shell must not make the local application
            # unusable. The shared server is already ready, so retain it and
            # move the user to the same interface in their normal browser.
            diagnostic_log_path = _write_startup_diagnostic_log(
                error,
                settings_path=settings_path,
                failure_stage="native_window_initialization",
                safe_details=_desktop_runtime_diagnostic_details(),
            )
            log_guidance = (
                f" Diagnostic details were saved to {diagnostic_log_path}."
                if diagnostic_log_path is not None
                else ""
            )
            show_desktop_notice(
                "Junior's desktop window could not start, so Junior will "
                "open in your normal web browser instead. Your data and "
                f"settings are unaffected.{log_guidance}"
            )
            webbrowser.open(url)
            while server_thread.is_alive():
                if shutdown_event.wait(timeout=0.1):
                    server.shutdown()
                    break
            server_thread.join()
    finally:
        shutdown_event.set()
        server.shutdown()
        server_thread.join(timeout=5.0)


def load_window_state(path: Path | None) -> dict[str, int]:
    """Load safe desktop geometry, falling back to the reviewed first-run size."""

    default_state = {
        "width": DEFAULT_WINDOW_WIDTH,
        "height": DEFAULT_WINDOW_HEIGHT,
    }
    if path is None or not path.is_file():
        return default_state
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default_state
    if not isinstance(payload, dict):
        return default_state

    width = payload.get("width")
    height = payload.get("height")
    x = payload.get("x")
    y = payload.get("y")
    if (
        not _is_plain_int(width)
        or not _is_plain_int(height)
        or not _is_plain_int(x)
        or not _is_plain_int(y)
        or not MINIMUM_WINDOW_WIDTH <= width <= MAXIMUM_WINDOW_WIDTH
        or not MINIMUM_WINDOW_HEIGHT <= height <= MAXIMUM_WINDOW_HEIGHT
        or not -10000 <= x <= 10000
        or not -10000 <= y <= 10000
    ):
        return default_state
    return {"width": width, "height": height, "x": x, "y": y}


def save_window_state(
    path: Path,
    *,
    width: int,
    height: int,
    x: int,
    y: int,
) -> None:
    """Atomically save only non-sensitive native-window geometry."""

    if (
        not _is_plain_int(width)
        or not _is_plain_int(height)
        or not _is_plain_int(x)
        or not _is_plain_int(y)
        or not MINIMUM_WINDOW_WIDTH <= width <= MAXIMUM_WINDOW_WIDTH
        or not MINIMUM_WINDOW_HEIGHT <= height <= MAXIMUM_WINDOW_HEIGHT
        or not -10000 <= x <= 10000
        or not -10000 <= y <= 10000
    ):
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(
            {"width": width, "height": height, "x": x, "y": y},
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_path, path)


def _is_plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def set_windows_app_identity() -> None:
    """Give an unpackaged Windows window Junior's own taskbar identity."""

    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Junior.JobRadar"
        )
    except (AttributeError, OSError):
        # Packaged builds receive their identity from the application manifest.
        return


def show_desktop_error(
    message: str,
    *,
    webview_module: Any = webview,
) -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.MessageBoxW(
                None,
                message,
                DESKTOP_ERROR_TITLE,
                0x00000010,
            )
            return
        except (AttributeError, OSError):
            pass

    try:
        safe_message = html.escape(message).replace("\n", "<br>")
        webview_module.create_window(
            "Junior could not start",
            html=(
                "<html><body style=\"background:#101114;color:#f2f4f7;"
                "font-family:system-ui;padding:24px;line-height:1.5\">"
                f"<h2>Junior could not start</h2><p>{safe_message}</p>"
                "</body></html>"
            ),
            width=620,
            height=420,
            resizable=True,
            background_color="#101114",
        )
        webview_module.start(private_mode=True)
        return
    except Exception:
        # If the platform GUI toolkit is itself unavailable, the terminal is
        # the only place left to provide the already-sanitized guidance.
        pass

    sys.stderr.write(f"{DESKTOP_ERROR_TITLE}\n\n{message}")


def launch_desktop() -> None:
    args = build_parser().parse_args()
    if args.browser and args.no_browser:
        raise ValueError("Choose either --browser or --no-browser, not both.")
    url = build_local_url(args.host, args.port)
    settings_path = ensure_desktop_workspace()
    lock_path = settings_path.parent.parent / "runtime" / INSTANCE_LOCK_NAME
    window_state_path = (
        settings_path.parent.parent / "runtime" / WINDOW_STATE_NAME
    )
    update_exit_event = threading.Event()

    with DesktopInstanceLock(lock_path, url) as instance:
        if not instance.acquired:
            existing_url = instance.existing_url or url
            wait_until_ready(existing_url)
            if args.browser:
                webbrowser.open(existing_url)
            elif not args.no_browser:
                show_desktop_notice(
                    "Junior is already open. Return to the existing Junior window."
                )
            return

        if is_junior_running(url):
            if args.browser:
                webbrowser.open(url)
            elif not args.no_browser:
                show_desktop_notice(
                    "Junior is already open at this local address."
                )
            return

        # Packaged settings use paths relative to the user-owned workspace, not
        # the launcher's working directory or immutable installation location.
        app = create_app(
            settings_path=settings_path,
            base_directory=settings_path.parent.parent,
            isolate_scan_process=True,
        )
        shutdown_event = threading.Event()
        app.config["JOB_RADAR_DESKTOP_SHUTDOWN_EVENT"] = shutdown_event
        app.config["JOB_RADAR_DESKTOP_UPDATE_EXIT_EVENT"] = update_exit_event
        app.config["JOB_RADAR_DESKTOP_UPDATE_AVAILABLE"] = bool(
            os.name == "nt" and getattr(sys, "frozen", False)
        )
        # Scoring is intentionally performed by a background worker. The local
        # server must also accept concurrent requests so a slow status read can
        # never prevent navigation or another progress request.
        server = make_server(args.host, args.port, app, threaded=True)

        try:
            if args.browser or args.no_browser:
                run_desktop_server(
                    server,
                    url=url,
                    open_browser=args.browser,
                    shutdown_event=shutdown_event,
                )
            else:
                run_native_window(
                    server,
                    url=url,
                    shutdown_event=shutdown_event,
                    window_state_path=window_state_path,
                    settings_path=settings_path,
                )
        finally:
            # GUI scans use a non-daemon worker. Keep the instance lock until
            # its durable database/report writes finish instead of allowing a
            # second launcher to open the same workspace during shutdown.
            app.extensions["junior_scan_runner"].wait()

    if update_exit_event.is_set():
        # pywebview/WebView2 can retain platform threads after its visible
        # window closes. At this point protected scan writes have finished and
        # the instance lock is released, so an approved updater handoff may
        # terminate the wrapper without risking user data.
        _exit_for_verified_update()


def _exit_for_verified_update() -> None:
    """Guarantee that the verified Windows installer can observe process exit."""

    os._exit(0)


def _lock_stream(stream: BinaryIO) -> None:
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_stream(stream: BinaryIO) -> None:
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _read_instance_url(stream: BinaryIO) -> str | None:
    # Byte zero is the OS lock; metadata starts after it so Windows permits a
    # second process to read the existing instance's local-only address.
    stream.seek(1)
    try:
        payload = json.loads(stream.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    url = payload.get("url") if isinstance(payload, dict) else None
    if (
        isinstance(url, str)
        and url.startswith(("http://127.0.0.1:", "http://localhost:"))
        and url.endswith("/")
    ):
        return url
    return None


def _desktop_icon_path() -> Path:
    static_directory = Path(__file__).resolve().parent / "static"
    if sys.platform == "win32":
        # WinForms requires a real multi-resolution ICO, not a PNG renamed or
        # decoded at runtime. Packaged macOS applications receive their icon
        # from the application bundle.
        return static_directory / "junior.ico"
    return static_directory / "junior_icon_v2.png"


def _webview_start_options() -> dict[str, object]:
    options: dict[str, object] = {"private_mode": True}
    if sys.platform == "win32" or sys.platform.startswith("linux"):
        # WinForms and Linux GTK/Qt accept runtime icon paths. Packaged macOS
        # applications receive Junior's icon from their application bundle.
        options["icon"] = str(_desktop_icon_path())
    return options


def _desktop_runtime_diagnostic_details() -> dict[str, str]:
    """Describe only public runtime facts needed to diagnose packaged startup."""

    details = {
        "frozen_package": str(bool(getattr(sys, "frozen", False))).lower(),
        "operating_system": platform.system() or "unknown",
        "operating_system_release": platform.release() or "unknown",
        "operating_system_version": platform.version() or "unknown",
        "processor_architecture": platform.machine() or "unknown",
        "python_architecture": str(ctypes.sizeof(ctypes.c_void_p) * 8) + "-bit",
    }
    runtime_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    required_files = {
        "python_runtime": runtime_root / "pythonnet" / "runtime" / "Python.Runtime.dll",
        "clr_loader_x64": runtime_root
        / "clr_loader"
        / "ffi"
        / "dlls"
        / "amd64"
        / "ClrLoader.dll",
        "webview2_core": runtime_root
        / "webview"
        / "lib"
        / "Microsoft.Web.WebView2.Core.dll",
        "webview2_winforms": runtime_root
        / "webview"
        / "lib"
        / "Microsoft.Web.WebView2.WinForms.dll",
    }
    for label, path in required_files.items():
        try:
            if not path.is_file():
                details[f"{label}_file"] = "missing"
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            details[f"{label}_file"] = (
                f"present; {path.stat().st_size} bytes; sha256={digest}"
            )
        except OSError:
            details[f"{label}_file"] = "could not be inspected"
    return details


def show_desktop_notice(message: str) -> None:
    """Report a harmless launcher condition without exposing technical detail."""
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.MessageBoxW(
                None,
                message,
                "Junior",
                0x00000040,
            )
            return
        except (AttributeError, OSError):
            pass
    sys.stderr.write(f"Junior\n\n{message}")


def main() -> None:
    # Frozen Windows children must identify themselves before argument parsing.
    # This lets scoring run separately without opening a second Junior window.
    multiprocessing.freeze_support()
    try:
        launch_desktop()
    except Exception as error:
        diagnostic_log_path = _write_startup_diagnostic_log(
            error,
            settings_path=None,
        )
        message = _format_unexpected_startup_error(
            error,
            settings_path=None,
            diagnostic_log_path=diagnostic_log_path,
        )
        show_desktop_error(message)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
