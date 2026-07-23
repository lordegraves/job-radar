"""Verify only a genuinely empty installation enters first-run setup."""

from pathlib import Path

from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import upsert_employer_source
from job_radar.first_run_service import needs_first_run_setup
from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import create_profile
from job_radar.web_app import create_app


def _app(tmp_path: Path):
    settings = tmp_path / "settings.yaml"
    settings.write_text(
        (
            f"database_path: {tmp_path / 'junior.sqlite3'}\n"
            f"reports_path: {tmp_path / 'reports'}\n"
            f"logs_path: {tmp_path / 'logs'}\n"
        ),
        encoding="utf-8",
    )
    return create_app(settings_path=settings, base_directory=tmp_path)


def test_empty_installation_opens_setup_welcome(tmp_path: Path) -> None:
    app = _app(tmp_path)
    client = app.test_client()

    response = client.get("/")
    setup = client.get(response.headers["Location"])

    assert response.status_code == 302
    assert response.headers["Location"] == "/setup"
    assert setup.status_code == 200
    html = setup.get_data(as_text=True)
    assert "Welcome to junior" in html
    assert "Nothing has been saved yet" in " ".join(html.split())
    assert 'href="/profile/new"' in html


def test_existing_profile_does_not_reenter_first_run(tmp_path: Path) -> None:
    app = _app(tmp_path)
    database_path = tmp_path / "junior.sqlite3"
    create_profile(
        database_path,
        ManagedProfile(
            profile_id="profile_aaaaaaaa",
            display_name="Test User",
        ),
    )
    client = app.test_client()

    assert needs_first_run_setup(database_path) is False
    assert client.get("/").status_code == 200
    assert client.get("/setup").headers["Location"] == "/profile"


def test_existing_employer_is_not_mistaken_for_new_installation(
    tmp_path: Path,
) -> None:
    app = _app(tmp_path)
    database_path = tmp_path / "junior.sqlite3"
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="example_employer",
            name="Example Employer",
            source_type="greenhouse",
            source_config={"source_slug": "example"},
        ),
    )

    assert needs_first_run_setup(database_path) is False
    assert app.test_client().get("/").status_code == 200
