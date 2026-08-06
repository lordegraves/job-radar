"""Verify About shows safe installed-version and schema information."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import job_radar.web_routes.settings as settings_routes
from job_radar import __version__
from job_radar.application_info_service import build_application_info
from job_radar.storage import initialize_database
from job_radar.source_health_service import ScanWarningItem
from job_radar.update_check_service import (
    UpdateCheckResult,
    check_for_stable_update,
    check_for_update,
)
from job_radar.update_install_service import (
    UpdateInstallError,
    download_verified_update,
    launch_windows_installer,
)
from job_radar.web_app import create_app


class _ReleaseResponse:
    def __init__(self, payload) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str]:
        return self.payload


def _write_settings(path: Path, database_path: Path) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(
        (
            f"database_path: {database_path}\n"
            f"reports_path: {path.parent.parent / 'reports'}\n"
            f"logs_path: {path.parent.parent / 'logs'}\n"
        ),
        encoding="utf-8",
    )


def test_application_info_reads_current_schema_without_user_content(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "junior.sqlite3"
    initialize_database(database_path)

    info = build_application_info(
        database_path=database_path,
        user_data_location=tmp_path,
    )

    assert info.version == __version__
    assert info.database_schema_version.isdigit()
    assert info.profile_schema_version == "1"
    assert info.user_data_location == str(tmp_path.resolve())


def test_about_page_shows_safe_version_and_update_details(tmp_path: Path) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    database_path = tmp_path / "data" / "junior.sqlite3"
    _write_settings(settings_path, database_path)
    app = create_app(settings_path=settings_path, base_directory=tmp_path)

    diagnostics_response = app.test_client().get("/settings/diagnostics")
    diagnostics_html = diagnostics_response.get_data(as_text=True)

    assert diagnostics_response.status_code == 200
    assert "About Junior and updates" not in diagnostics_html
    assert "Check for updates" not in diagnostics_html
    about_response = app.test_client().get("/settings/about")
    about_html = about_response.get_data(as_text=True)
    assert about_response.status_code == 200
    assert "Help & About" in about_html
    assert "What Junior does" in about_html
    assert "Scans &amp; results" in about_html
    assert "Privacy &amp; safety" in about_html
    assert "grid-template-columns: repeat(8, minmax(0, 1fr))" in about_html
    assert "white-space: nowrap" in about_html
    assert 'aria-label="Settings and diagnostics"' in about_html
    assert 'href="/settings/about" aria-current="page">Help</a>' in about_html
    assert 'href="/settings/diagnostics">Diagnostics</a>' in about_html
    assert "function showHelpSection" in about_html
    assert 'document.querySelectorAll(".help-card")' in about_html
    assert "card.open = card === target" in about_html
    assert 'event.target.closest(\'a[href^="#"]\')' in about_html
    assert 'showHelpSection("overview"' in about_html
    assert 'id="about-junior"' in about_html
    assert "Check for updates" in about_html
    assert "never downloads or installs an" in about_html
    assert "update without your approval" in about_html
    assert "Dawn Peacock" in about_html
    assert "GPL-3.0-only" in about_html
    assert __version__ in about_html
    assert str(tmp_path.resolve()) in about_html


def test_update_check_reports_newer_verified_stable_release() -> None:
    result = check_for_stable_update(
        "0.1.0",
        request_get=lambda *args, **kwargs: _ReleaseResponse(
            {
                "tag_name": "v0.2.0",
                "html_url": (
                    "https://github.com/lordegraves/junior/releases/tag/v0.2.0"
                ),
            }
        ),
    )

    assert result.status == "available"
    assert result.available_version == "0.2.0"
    assert "will not download or install" in result.message


def test_update_check_rejects_unverified_release_link() -> None:
    result = check_for_stable_update(
        "0.1.0",
        request_get=lambda *args, **kwargs: _ReleaseResponse(
            {
                "tag_name": "v9.9.9",
                "html_url": "https://example.com/download.exe",
            }
        ),
    )

    assert result.status == "unavailable"
    assert result.release_url is None
    assert "not changed" in result.message


def test_update_check_reports_newer_field_test_build() -> None:
    result = check_for_update(
        "0.2.0",
        installed_build="1.1",
        release_label="SP5",
        release_tag="v0.2.0-rc5",
        request_get=lambda *args, **kwargs: _ReleaseResponse(
            {
                "html_url": (
                    "https://github.com/lordegraves/junior/"
                    "releases/tag/v0.2.0-rc5"
                ),
                "assets": [
                    {
                        "name": "Junior-Setup-0.2.0-SP5-build-1.2.exe",
                        "browser_download_url": (
                            "https://github.com/lordegraves/junior/releases/"
                            "download/v0.2.0-rc5/"
                            "Junior-Setup-0.2.0-SP5-build-1.2.exe"
                        ),
                    },
                    {
                        "name": "SHA256-SP5-build-1.2.txt",
                        "browser_download_url": (
                            "https://github.com/lordegraves/junior/releases/"
                            "download/v0.2.0-rc5/"
                            "SHA256-SP5-build-1.2.txt"
                        ),
                    },
                ],
            }
        ),
    )

    assert result.status == "available"
    assert result.available_build == "1.2"
    assert "SP5 Build 1.2 is available" in result.message
    assert result.installer_name == "Junior-Setup-0.2.0-SP5-build-1.2.exe"
    assert result.installer_url is not None
    assert result.checksum_url is not None


def test_about_update_check_is_manual_and_displays_safe_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    database_path = tmp_path / "data" / "junior.sqlite3"
    _write_settings(settings_path, database_path)
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    monkeypatch.setattr(
        settings_routes,
        "check_for_update",
        lambda version, **kwargs: check_for_stable_update(
            "0.1.0",
            request_get=lambda *args, **kwargs: _ReleaseResponse(
                {
                        "tag_name": "v0.3.0",
                        "html_url": (
                            "https://github.com/lordegraves/junior/"
                            "releases/tag/v0.3.0"
                        ),
                }
            ),
        ),
    )

    client = app.test_client()
    before_check = client.get("/settings").get_data(as_text=True)
    response = client.post(
        "/settings/about/check-updates",
        follow_redirects=True,
    )
    after_check = response.get_data(as_text=True)

    assert "Junior 0.3.0 is available" not in before_check
    assert response.status_code == 200
    assert response.request.path == "/settings/about"
    assert "Junior 0.3.0 is available" in after_check
    assert 'id="about-junior"' in after_check


class _DownloadResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, *, chunk_size: int):
        del chunk_size
        yield self.content


def _installable_update(installer: bytes) -> UpdateCheckResult:
    del installer
    return UpdateCheckResult(
        status="available",
        message="SP5 Build 1.5 is available.",
        available_version="0.2.0",
        available_build="1.4",
        release_url=(
            "https://github.com/lordegraves/junior/releases/tag/v0.2.0-rc5"
        ),
        installer_name="Junior-Setup-0.2.0-SP5-build-1.5.exe",
        installer_url=(
            "https://github.com/lordegraves/junior/releases/download/"
            "v0.2.0-rc5/Junior-Setup-0.2.0-SP5-build-1.5.exe"
        ),
        checksum_url=(
            "https://github.com/lordegraves/junior/releases/download/"
            "v0.2.0-rc5/SHA256-SP5-build-1.5.txt"
        ),
    )


def test_update_download_verifies_checksum_before_replacing_file(
    tmp_path: Path,
) -> None:
    installer = b"verified installer"
    update = _installable_update(installer)
    checksum = (
        f"{hashlib.sha256(installer).hexdigest()}  {update.installer_name}\r\n"
    ).encode()

    def request_get(url: str, **kwargs):
        del kwargs
        return _DownloadResponse(
            checksum if "SHA256" in url else installer
        )

    result = download_verified_update(
        update,
        tmp_path,
        request_get=request_get,
    )

    assert result.read_bytes() == installer
    assert not result.with_suffix(".exe.part").exists()


def test_update_download_rejects_checksum_mismatch(tmp_path: Path) -> None:
    installer = b"untrusted installer"
    update = _installable_update(installer)

    def request_get(url: str, **kwargs):
        del kwargs
        if "SHA256" in url:
            return _DownloadResponse(
                f"{'0' * 64}  {update.installer_name}\n".encode()
            )
        return _DownloadResponse(installer)

    try:
        download_verified_update(update, tmp_path, request_get=request_get)
    except UpdateInstallError as error:
        assert "did not match" in str(error)
    else:
        raise AssertionError("checksum mismatch should be rejected")
    assert not (tmp_path / update.installer_name).exists()


def test_update_launcher_uses_no_command_shell(tmp_path: Path) -> None:
    installer = tmp_path / "Junior.exe"
    calls = []

    def record_launch(*args, **kwargs):
        calls.append((args, kwargs))
        command = args[0]
        confirmation_path = Path(
            command[command.index("-ConfirmationPath") + 1]
        )
        confirmation_path.write_text("started", encoding="utf-8")
        return type("_Process", (), {"poll": lambda self: None})()

    launch_windows_installer(
        installer,
        log_path=tmp_path / "junior-update.log",
        parent_process_id=4123,
        popen=record_launch,
    )

    assert len(calls) == 1
    command = calls[0][0][0]
    assert command[0].endswith(r"WindowsPowerShell\v1.0\powershell.exe")
    assert command[1:7] == [
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
    ]
    assert "-ParentProcessId" in command
    assert command[command.index("-ParentProcessId") + 1] == "4123"
    assert command[command.index("-InstallerPath") + 1] == str(installer)
    assert calls[0][1]["close_fds"] is True
    assert calls[0][1]["creationflags"] == (
        subprocess.CREATE_NEW_PROCESS_GROUP
        | subprocess.CREATE_NO_WINDOW
    )
    helper_path = tmp_path / "junior-update-handoff.ps1"
    helper_text = helper_path.read_text(encoding="utf-8")
    assert "$ShutdownDeadline = (Get-Date).AddSeconds(45)" in helper_text
    assert "Get-Process -Id $ParentProcessId" in helper_text
    assert "Get-Process -Name 'Junior'" in helper_text
    assert "the update was not installed" in helper_text
    assert "Start-Sleep -Milliseconds 1000" in helper_text
    assert "Start-Process -FilePath $InstallerPath" in helper_text
    assert "-PassThru -Wait" in helper_text
    assert "Start-Process -FilePath $ApplicationPath" in helper_text
    assert "Set-Content -LiteralPath $ResultPath" in helper_text
    assert "'/NOCLOSEAPPLICATIONS'" in helper_text
    assert "'/AUTOLAUNCH'" not in helper_text
    assert "Write-SafeUpdateEvent" in helper_text
    assert "Set-Content -LiteralPath $ConfirmationPath" in helper_text
    assert "-ConfirmationPath" in command
    assert "-LogPath" in command
    assert "-ApplicationVersion" in command
    assert "schema_version = 1" in helper_text
    assert "subsystem = 'update'" in helper_text
    update_log = tmp_path / "junior-update.log"
    assert update_log.is_file()
    update_payload = json.loads(update_log.read_text(encoding="utf-8"))
    assert update_payload["event"] == "update_handoff_prepared"
    assert update_payload["subsystem"] == "update"
    assert update_payload["severity"] == "info"
    assert update_payload["schema_version"] == 1


def test_update_launcher_rejects_a_helper_that_never_starts(
    tmp_path: Path,
) -> None:
    installer = tmp_path / "Junior.exe"
    update_log = tmp_path / "junior-update.log"

    try:
        launch_windows_installer(
            installer,
            log_path=update_log,
            parent_process_id=4123,
            popen=lambda *args, **kwargs: type(
                "_Process",
                (),
                {"poll": lambda self: 0},
            )(),
        )
    except UpdateInstallError as error:
        assert "did not start the installer handoff" in str(error)
    else:
        raise AssertionError("a helper that never starts must be rejected")

    events = [
        json.loads(line)
        for line in update_log.read_text(encoding="utf-8").splitlines()
    ]
    assert [event["event"] for event in events] == [
        "update_handoff_prepared",
        "update_handoff_launch_failed",
    ]
    assert events[-1]["severity"] == "error"


def test_desktop_update_downloads_verifies_launches_and_closes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    database_path = tmp_path / "data" / "junior.sqlite3"
    _write_settings(settings_path, database_path)
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    shutdown_event = type("_Event", (), {"set": lambda self: None})()
    update_exit_event = type("_Event", (), {"set": lambda self: None})()
    app.config["JOB_RADAR_DESKTOP_SHUTDOWN_EVENT"] = shutdown_event
    app.config["JOB_RADAR_DESKTOP_UPDATE_EXIT_EVENT"] = update_exit_event
    app.config["JOB_RADAR_DESKTOP_UPDATE_AVAILABLE"] = True
    update = _installable_update(b"installer")
    launched = []
    monkeypatch.setattr(settings_routes, "check_for_update", lambda *a, **k: update)
    monkeypatch.setattr(
        settings_routes,
        "download_verified_update",
        lambda *a, **k: tmp_path / update.installer_name,
    )
    monkeypatch.setattr(
        settings_routes,
        "launch_windows_installer",
        lambda path, **kwargs: launched.append((path, kwargs)),
    )
    monkeypatch.setattr(
        settings_routes.threading,
        "Timer",
        lambda *a, **k: type(
            "_Timer",
            (),
            {"daemon": False, "start": lambda self: None},
        )(),
    )

    response = app.test_client().post("/settings/install-update")

    assert response.status_code == 200
    assert "Installing Junior update" in response.get_data(as_text=True)
    assert launched[0][0] == tmp_path / update.installer_name
    assert launched[0][1]["application_path"] == Path(sys.executable)
    assert launched[0][1]["log_path"] == (
        tmp_path / "logs" / "junior-update.log"
    )
    assert launched[0][1]["expected_build"] == (
        f"RC6 Build {update.available_build}"
    )


def test_diagnostics_links_to_read_only_source_and_scan_details(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    database_path = tmp_path / "data" / "junior.sqlite3"
    _write_settings(settings_path, database_path)
    monkeypatch.setattr(
        settings_routes,
        "build_latest_scan_warnings",
        lambda _database_path: (
            ScanWarningItem(
                employer_id="microsoft",
                employer_name="Microsoft",
                source_type="eightfold",
                source_label="Eightfold",
                category="Network",
                failure_stage="Initial job-search request",
                message=(
                    "Junior reached the recruiting service, but the initial "
                    "job-search request was rate-limited (HTTP 429) before a "
                    "usable results page was received."
                ),
                created_at="2026-07-29T12:00:30+00:00",
            ),
        ),
    )
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    client = app.test_client()

    diagnostics = client.get("/settings/diagnostics").get_data(as_text=True)
    source_health_response = client.get(
        "/settings/diagnostics/sources"
    )
    scan_details = client.get(
        "/settings/diagnostics/latest-scan"
    ).get_data(as_text=True)

    assert "/companies" in diagnostics
    assert "/settings/diagnostics/latest-scan" in diagnostics
    assert source_health_response.status_code == 302
    assert source_health_response.headers["Location"].endswith(
        "/companies#company-sources"
    )
    assert "Microsoft" in scan_details
    assert "Initial job-search request" in scan_details
    assert "HTTP 429" in scan_details
