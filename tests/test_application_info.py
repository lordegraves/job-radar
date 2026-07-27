"""Verify About shows safe installed-version and schema information."""

from pathlib import Path

import job_radar.web_routes.settings as settings_routes
from job_radar import __version__
from job_radar.application_info_service import build_application_info
from job_radar.storage import initialize_database
from job_radar.web_app import create_app
from job_radar.update_check_service import (
    check_for_stable_update,
    check_for_update,
)


class _ReleaseResponse:
    def __init__(self, payload: dict[str, str]) -> None:
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


def test_settings_page_shows_safe_version_and_update_details(tmp_path: Path) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    database_path = tmp_path / "data" / "junior.sqlite3"
    _write_settings(settings_path, database_path)
    app = create_app(settings_path=settings_path, base_directory=tmp_path)

    response = app.test_client().get("/settings")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "About junior and updates" in html
    assert __version__ in html
    assert "Database / profile schema" in html
    assert "Check for updates" in html
    assert "never downloads or installs" in html
    assert "Dawn Peacock" in html
    assert "GPL-3.0-only" in html
    assert app.test_client().get("/settings/about").status_code == 302


def test_update_check_reports_newer_verified_stable_release() -> None:
    result = check_for_stable_update(
        "0.1.0",
        request_get=lambda *args, **kwargs: _ReleaseResponse(
            {
                "tag_name": "v0.2.0",
                "html_url": (
                    "https://github.com/lordegraves/job-radar/releases/tag/v0.2.0"
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
                    "https://github.com/lordegraves/job-radar/"
                    "releases/tag/v0.2.0-rc5"
                ),
                "assets": [
                    {"name": "Junior-Setup-0.2.0-SP5-build-1.2.exe"},
                    {"name": "SHA256.txt"},
                ],
            }
        ),
    )

    assert result.status == "available"
    assert result.available_build == "1.2"
    assert "SP5 Build 1.2 is available" in result.message


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
                            "https://github.com/lordegraves/job-radar/"
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
    assert "Junior 0.3.0 is available" in after_check
    assert "will not download or install it automatically" in after_check


def test_diagnostics_links_to_read_only_source_and_scan_details(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    database_path = tmp_path / "data" / "junior.sqlite3"
    _write_settings(settings_path, database_path)
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    client = app.test_client()

    diagnostics = client.get("/settings/diagnostics").get_data(as_text=True)
    source_health = client.get(
        "/settings/diagnostics/sources"
    ).get_data(as_text=True)
    scan_details = client.get(
        "/settings/diagnostics/latest-scan"
    ).get_data(as_text=True)

    assert "/settings/diagnostics/sources" in diagnostics
    assert "/settings/diagnostics/latest-scan" in diagnostics
    assert "Company Source Health" in source_health
    assert "View the read-only Collector Catalog" in source_health
    assert "Scan selected companies" in source_health
    assert "No company-source warnings" in scan_details
