"""Verify normal users can act on catalog recommendations through the GUI."""

from pathlib import Path

from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import upsert_employer_source
from job_radar.models import JobPosting
from job_radar.profile_models import ManagedProfile, ProfilePreferences
from job_radar.profile_storage import create_profile, get_profile, set_active_profile
from job_radar.web_app import create_app
from job_radar.storage import start_scan_run, upsert_job_posting


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


def test_empty_recommendations_page_gives_role_specific_starting_point(
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

    client = create_app(
        settings_path=settings_path,
        base_directory=tmp_path,
    ).test_client()
    page = client.get("/companies/recommendations")
    html = page.get_data(as_text=True)

    assert page.status_code == 200
    assert "Start building your company list" in html
    assert "selected work: cook" in html
    assert "starting directions" in html
    assert "Add company" in html


def test_recommendations_page_reviews_fresh_outside_catalog_company(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    settings_path = tmp_path / "settings.yaml"
    _write_settings(settings_path, database_path)
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Culinary Profile",
        preferences=ProfilePreferences(target_roles=("Baker",)),
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    scan_id = start_scan_run(
        database_path,
        requested_at="2026-07-23T12:00:00+00:00",
        companies_requested=1,
        companies_enabled=1,
        profile_id=profile.profile_id,
    )
    upsert_job_posting(
        database_path,
        JobPosting(
            company_key="outside_bakery",
            company_name="Outside Bakery",
            source_type="html",
            source_job_id="outside-1",
            source_url="https://outside.invalid/jobs/1",
            title="Baker",
            location="Remote",
            description="Fictional job.",
            canonical_key="outside-1",
            content_hash="outside-hash-1",
        ),
        scan_run_id=scan_id,
    )
    client = create_app(
        settings_path=settings_path, base_directory=tmp_path
    ).test_client()

    page = client.get("/companies/recommendations").get_data(as_text=True)
    assert "Companies Junior found outside your catalog" in page
    assert "Outside Bakery" in page
    assert "Review company" in page

    reviewed = client.post(
        "/companies/recommendations/external/outside_bakery/review",
        follow_redirects=True,
    ).get_data(as_text=True)
    assert "needs an administrator to finish setting up this company" in reviewed
