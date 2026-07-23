"""Verify About shows safe installed-version and schema information."""

from pathlib import Path

from job_radar import __version__
from job_radar.application_info_service import build_application_info
from job_radar.storage import initialize_database
from job_radar.web_app import create_app


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


def test_about_page_shows_safe_support_and_version_details(tmp_path: Path) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    database_path = tmp_path / "data" / "junior.sqlite3"
    _write_settings(settings_path, database_path)
    app = create_app(settings_path=settings_path, base_directory=tmp_path)

    response = app.test_client().get("/settings/about")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "About junior" in html
    assert __version__ in html
    assert str(tmp_path.resolve()) in html
    assert "Database schema version" in html
    assert "Profile/configuration schema version" in html
    assert "claytonmgraves@outlook.com" in html
    assert "Do not include passwords" in html
