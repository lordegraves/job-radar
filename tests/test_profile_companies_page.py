"""Verify company pages display active-profile employer ownership."""

from pathlib import Path

from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import (
    set_profile_employer_enabled,
    upsert_employer_source,
)
from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import create_profile, set_active_profile
from job_radar.web_app import create_app


def write_settings_file(path: Path, database_path: Path) -> None:
    path.write_text(
        f"""
database_path: {database_path}
reports_path: {path.parent / "reports"}
logs_path: {path.parent / "logs"}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_companies_page_shows_only_active_profile_employers(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    database_path = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_path, database_path)

    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Paralegal Profile",
        company_ids=("assigned_law", "disabled_insurance"),
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)

    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="assigned_law",
            name="Assigned Law Firm",
            source_type="html",
            source_config={
                "source_url": "https://law.invalid/jobs",
            },
            notes="Local legal employer.",
        ),
    )
    set_profile_employer_enabled(
        database_path,
        profile.profile_id,
        "disabled_insurance",
        enabled=False,
    )
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="disabled_insurance",
            name="Disabled Insurance",
            source_type="greenhouse",
            enabled=False,
            source_config={
                "source_slug": "disabled-insurance",
            },
        ),
    )
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="unassigned_bakery",
            name="Unassigned Bakery",
            source_type="lever",
            source_config={
                "source_slug": "unassigned-bakery",
            },
        ),
    )

    app = create_app(
        settings_path=settings_path,
        base_directory=tmp_path,
    )
    client = app.test_client()

    response = client.get("/companies")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Your Companies" in html
    assert "Paralegal Profile" in html
    assert "Assigned Law Firm" in html
    assert "Disabled Insurance" in html
    assert "Unassigned Bakery" not in html
    assert "Scanning" in html
    assert "Paused" in html
    assert "Legacy config file:" not in html
    assert "Source type" not in html
    assert "https://law.invalid/jobs" not in html
    assert "Local legal employer." not in html
    assert "Adding companies will be available" in html


def test_company_detail_rejects_employer_not_assigned_to_active_profile(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    database_path = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_path, database_path)

    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Electrician Profile",
        company_ids=("assigned_contractor",),
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)

    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="assigned_contractor",
            name="Assigned Contractor",
            source_type="html",
            source_config={
                "source_url": "https://contractor.invalid/jobs",
            },
        ),
    )
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="unassigned_utility",
            name="Unassigned Utility",
            source_type="html",
            source_config={
                "source_url": "https://utility.invalid/jobs",
            },
        ),
    )

    app = create_app(
        settings_path=settings_path,
        base_directory=tmp_path,
    )
    client = app.test_client()

    assigned_response = client.get(
        "/companies/assigned_contractor"
    )
    unassigned_response = client.get(
        "/companies/unassigned_utility"
    )

    assert assigned_response.status_code == 200
    assert "Electrician Profile" in assigned_response.get_data(
        as_text=True
    )
    assert "Source detail" not in assigned_response.get_data(as_text=True)
    assert "https://contractor.invalid/jobs" not in assigned_response.get_data(
        as_text=True
    )
    assert unassigned_response.status_code == 404


def test_companies_page_shows_empty_profile_guidance(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    database_path = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_path, database_path)

    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="New Secretary Profile",
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)

    app = create_app(
        settings_path=settings_path,
        base_directory=tmp_path,
    )
    client = app.test_client()

    response = client.get("/companies")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "No companies have been added to this search yet." in html
    assert "will not scan employers from another profile" in html
