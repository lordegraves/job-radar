"""Verify normal users can act on catalog recommendations through the GUI."""

from pathlib import Path

from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import upsert_employer_source
from job_radar.profile_models import ManagedProfile, ProfilePreferences
from job_radar.profile_storage import create_profile, get_profile, set_active_profile
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


def test_recommendations_page_explains_adds_and_hides_feedback(
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
    for employer_id, name in (
        ("example_kitchen", "Example Kitchen"),
        ("sample_bakery", "Sample Bakery"),
    ):
        upsert_employer_source(
            database_path,
            EmployerSource(
                employer_id=employer_id,
                name=name,
                source_type="html",
                source_config={
                    "source_url": f"https://{employer_id}.invalid/jobs",
                    "tags": ["cook"],
                },
            ),
        )
    client = create_app(
        settings_path=settings_path, base_directory=tmp_path
    ).test_client()

    page = client.get("/companies/recommendations")
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "Recommended companies for Culinary Profile" in html
    assert "Why Junior recommends this company" in html
    assert "recommendation_score" not in html

    hidden = client.post(
        "/companies/recommendations/sample_bakery/feedback",
        data={"state": "NOT_RELEVANT"},
        follow_redirects=True,
    ).get_data(as_text=True)
    assert "Sample Bakery" not in hidden
    assert "Example Kitchen" in hidden

    added = client.post(
        "/companies/recommendations/example_kitchen/add",
        follow_redirects=True,
    ).get_data(as_text=True)
    assert "Example Kitchen was added and will be scanned." in added
    assert get_profile(database_path, profile.profile_id).company_ids == (
        "example_kitchen",
    )
