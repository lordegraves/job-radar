"""Verify normal users are not presented with employer-market recommendations."""

from pathlib import Path

from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import upsert_employer_source
from job_radar.profile_models import ManagedProfile, ProfilePreferences
from job_radar.profile_storage import create_profile, set_active_profile
from job_radar.web_app import create_app


def _write_settings(path: Path, database_path: Path) -> None:
    path.write_text(
        "\n".join(
            (
                f"database_path: {database_path}",
                f"reports_path: {path.parent / 'reports'}",
                f"logs_path: {path.parent / 'logs'}",
            )
        )
        + "\n",
        encoding="utf-8",
    )


def test_companies_centers_user_selected_employers_not_recommendations(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    settings_path = tmp_path / "settings.yaml"
    _write_settings(settings_path, database_path)
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Culinary Profile",
        preferences=ProfilePreferences(target_roles=("cook",)),
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="sample_bakery",
            name="Sample Bakery",
            source_type="html",
            source_config={"source_url": "https://sample.invalid/jobs"},
        ),
    )
    client = create_app(
        settings_path=settings_path,
        base_directory=tmp_path,
    ).test_client()

    companies_html = client.get("/companies").get_data(as_text=True)

    assert "Add company" in companies_html
    assert "View recommendations" not in companies_html
    assert "View catalog suggestions" not in companies_html
    assert client.get("/companies/recommendations").status_code == 404
    assert (
        client.post(
            "/companies/recommendations/sample_bakery/add"
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/companies/recommendations/sample_bakery/feedback"
        ).status_code
        == 404
    )
