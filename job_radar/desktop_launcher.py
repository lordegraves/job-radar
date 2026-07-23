"""Launch Job Radar's browser-based interface as a desktop-style application.

The launcher prepares the user-owned workspace, starts a local-only web server,
waits for readiness, and then opens the browser. It reuses an existing Job Radar
instance when possible and presents safe graphical startup errors on Windows.
"""

import argparse
import ctypes
import json
import os
import sys
import threading
import time
import webbrowser
from contextlib import AbstractContextManager
from pathlib import Path
from typing import BinaryIO
from urllib.error import URLError
from urllib.request import urlopen

from werkzeug.serving import BaseWSGIServer, make_server

from job_radar.runtime_paths import UserDataPaths
from job_radar.user_data_bootstrap import bootstrap_packaged_user_configuration
from job_radar.web_app import (
    _format_unexpected_startup_error,
    _write_startup_diagnostic_log,
    create_app,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000
DEFAULT_STARTUP_TIMEOUT_SECONDS = 10.0
DESKTOP_ERROR_TITLE = "junior could not start"
INSTANCE_LOCK_NAME = "desktop-instance.lock"


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
        prog="job-radar-desktop",
        description="Launch the junior desktop interface",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="Host interface for the local junior server",
    )
    parser.add_argument(
        "--port",
        default=DEFAULT_PORT,
        type=int,
        help="Port for the local junior server",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start junior without opening the default web browser",
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


def is_job_radar_running(url: str) -> bool:
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
        if is_job_radar_running(url):
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
        name="job-radar-local-server",
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


def show_desktop_error(message: str) -> None:
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

    sys.stderr.write(f"{DESKTOP_ERROR_TITLE}\n\n{message}")


def launch_desktop() -> None:
    args = build_parser().parse_args()
    url = build_local_url(args.host, args.port)
    settings_path = ensure_desktop_workspace()
    lock_path = settings_path.parent.parent / "runtime" / INSTANCE_LOCK_NAME

    with DesktopInstanceLock(lock_path, url) as instance:
        if not instance.acquired:
            existing_url = instance.existing_url or url
            wait_until_ready(existing_url)
            if not args.no_browser:
                webbrowser.open(existing_url)
            return

        if is_job_radar_running(url):
            if not args.no_browser:
                webbrowser.open(url)
            return

        # Packaged settings use paths relative to the user-owned workspace, not
        # the launcher's working directory or immutable installation location.
        app = create_app(
            settings_path=settings_path,
            base_directory=settings_path.parent.parent,
        )
        shutdown_event = threading.Event()
        app.config["JOB_RADAR_DESKTOP_SHUTDOWN_EVENT"] = shutdown_event
        server = make_server(args.host, args.port, app)

        try:
            run_desktop_server(
                server,
                url=url,
                open_browser=not args.no_browser,
                shutdown_event=shutdown_event,
            )
        finally:
            # GUI scans use a non-daemon worker. Keep the instance lock until
            # its durable database/report writes finish instead of allowing a
            # second launcher to open the same workspace during shutdown.
            app.extensions["junior_scan_runner"].wait()


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


def main() -> None:
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
