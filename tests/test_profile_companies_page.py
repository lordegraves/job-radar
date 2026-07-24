"""Verify company pages display active-profile employer ownership."""

from pathlib import Path

from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import (
    get_employer_source,
    is_profile_employer_enabled,
    set_profile_employer_enabled,
    upsert_employer_source,
)
from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import create_profile, get_profile, set_active_profile
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
    assert "Add company" in html


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


def test_companies_page_can_pause_and_resume_active_profile_company(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    database_path = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_path, database_path)
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="example_cafe",
            name="Example Cafe",
            source_type="html",
            source_config={"source_url": "https://cafe.invalid/jobs"},
        ),
    )
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Culinary Profile",
        company_ids=("example_cafe",),
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    client = app.test_client()

    initial_html = client.get("/companies").get_data(as_text=True)
    assert "Pause" in initial_html
    assert "1</strong>" in initial_html

    paused_response = client.post(
        "/companies/example_cafe/scanning",
        data={"state": "paused"},
        follow_redirects=True,
    )
    paused_html = paused_response.get_data(as_text=True)

    assert paused_response.status_code == 200
    assert "Example Cafe is now paused for Culinary Profile&#39;s profile." in (
        paused_html
    )
    assert "Resume" in paused_html
    assert is_profile_employer_enabled(
        database_path, profile.profile_id, "example_cafe"
    ) is False

    resumed_response = client.post(
        "/companies/example_cafe/scanning",
        data={"state": "scanning"},
        follow_redirects=True,
    )

    assert resumed_response.status_code == 200
    assert "Example Cafe is now scanning" in resumed_response.get_data(
        as_text=True
    )
    assert is_profile_employer_enabled(
        database_path, profile.profile_id, "example_cafe"
    ) is True


def test_company_scanning_route_rejects_invalid_state_and_legacy_mode(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    database_path = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_path, database_path)
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="example_cafe",
            name="Example Cafe",
            source_type="html",
            source_config={"source_url": "https://cafe.invalid/jobs"},
        ),
    )
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Culinary Profile",
        company_ids=("example_cafe",),
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    client = app.test_client()

    invalid_response = client.post(
        "/companies/example_cafe/scanning",
        data={"state": "unexpected"},
        follow_redirects=True,
    )
    assert "Choose Pause or Resume" in invalid_response.get_data(as_text=True)
    assert is_profile_employer_enabled(
        database_path, profile.profile_id, "example_cafe"
    ) is True

    set_active_profile(database_path, None)
    legacy_response = client.post(
        "/companies/example_cafe/scanning",
        data={"state": "paused"},
    )
    assert legacy_response.status_code == 302
    assert "company_result=error" in legacy_response.headers["Location"]
    assert "Select+a+managed+profile" in legacy_response.headers["Location"]
    assert is_profile_employer_enabled(
        database_path, profile.profile_id, "example_cafe"
    ) is True


def test_companies_page_removes_only_confirmed_active_profile_assignment(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    database_path = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_path, database_path)
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="example_cafe",
            name="Example Cafe",
            source_type="html",
            source_config={"source_url": "https://cafe.invalid/jobs"},
        ),
    )
    active_profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Culinary Profile",
        company_ids=("example_cafe",),
    )
    other_profile = ManagedProfile(
        profile_id="profile_bbbbbbbb",
        display_name="Other Profile",
        company_ids=("example_cafe",),
    )
    create_profile(database_path, active_profile)
    create_profile(database_path, other_profile)
    set_active_profile(database_path, active_profile.profile_id)
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    client = app.test_client()

    missing_confirmation = client.post(
        "/companies/example_cafe/remove",
        data={},
        follow_redirects=True,
    )
    assert "Type REMOVE to confirm" in missing_confirmation.get_data(as_text=True)
    assert get_profile(
        database_path, active_profile.profile_id
    ).company_ids == ("example_cafe",)

    response = client.post(
        "/companies/example_cafe/remove",
        data={"confirmation": "REMOVE"},
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Example Cafe was removed from Culinary Profile&#39;s company list" in html
    assert "Existing jobs and application history were kept." in html
    assert "No companies have been added to this search yet." in html
    assert get_profile(database_path, active_profile.profile_id).company_ids == ()
    assert get_profile(database_path, other_profile.profile_id).company_ids == (
        "example_cafe",
    )
    assert get_employer_source(database_path, "example_cafe") is not None
    assert client.get("/companies/example_cafe").status_code == 404


def test_add_company_page_searches_safe_catalog_and_adds_available_employer(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    database_path = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_path, database_path)
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="example_cafe",
            name="Example Cafe",
            source_type="html",
            source_config={"source_url": "https://cafe.invalid/jobs"},
            notes="Internal collector note.",
        ),
    )
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="incomplete_bakery",
            name="Incomplete Bakery",
            source_type="html",
            source_config={},
        ),
    )
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Culinary Profile",
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    client = app.test_client()

    page_response = client.get("/companies/add?q=cafe")
    page_html = page_response.get_data(as_text=True)

    assert page_response.status_code == 200
    assert "Add a company" in page_html
    assert "Example Cafe" in page_html
    assert "Incomplete Bakery" not in page_html
    assert "Available" in page_html
    assert "Internal collector note." not in page_html
    assert "source_type" not in page_html

    response = client.post(
        "/companies/add",
        data={"employer_id": "example_cafe"},
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Example Cafe was added to Culinary Profile&#39;s company list" in html
    assert "will be scanned" in html
    assert get_profile(database_path, profile.profile_id).company_ids == (
        "example_cafe",
    )
    assert is_profile_employer_enabled(
        database_path,
        profile.profile_id,
        "example_cafe",
    ) is True


def test_add_company_page_blocks_incomplete_and_duplicate_employers(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    database_path = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_path, database_path)
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="assigned_cafe",
            name="Assigned Cafe",
            source_type="html",
            source_config={"source_url": "https://assigned.invalid/jobs"},
        ),
    )
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="incomplete_bakery",
            name="Incomplete Bakery",
            source_type="html",
            source_config={},
        ),
    )
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Culinary Profile",
        company_ids=("assigned_cafe",),
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    client = app.test_client()

    assigned_page = client.get("/companies/add?q=assigned").get_data(as_text=True)
    incomplete_page = client.get("/companies/add?q=incomplete").get_data(
        as_text=True
    )
    assert "Already added" in assigned_page
    assert "Needs setup" in incomplete_page
    assert "needs administrator setup" in incomplete_page

    incomplete_response = client.post(
        "/companies/add",
        data={"employer_id": "incomplete_bakery"},
        follow_redirects=True,
    )
    duplicate_response = client.post(
        "/companies/add",
        data={"employer_id": "assigned_cafe"},
        follow_redirects=True,
    )

    assert "needs administrator setup" in incomplete_response.get_data(
        as_text=True
    )
    assert "already included" in duplicate_response.get_data(as_text=True)
    assert get_profile(database_path, profile.profile_id).company_ids == (
        "assigned_cafe",
    )


def test_add_company_by_careers_url_requires_detected_source_confirmation(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    database_path = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_path, database_path)
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Culinary Profile",
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    client = app.test_client()

    response = client.post(
        "/companies/add/resolve",
        data={
            "company": "https://jobs.lever.co/example-kitchens",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "What Junior found" in html
    assert "Detected job source" in html
    assert "Lever career site" in html
    assert "has not added or scanned this company yet" in html
    assert "source_slug" not in html
    assert "Platform:" not in html
    assert get_profile(database_path, profile.profile_id).company_ids == ()

    confirmed = client.post(
        "/companies/add/confirm-detected",
        data={
            "company_name": "Example Kitchens",
            "careers_url": "https://jobs.lever.co/example-kitchens",
        },
    )
    assert confirmed.status_code == 302
    assert confirmed.headers["Location"].startswith("/companies?")
    assert get_profile(database_path, profile.profile_id).company_ids == (
        "example-kitchens",
    )


def test_add_company_by_complete_adp_url_requests_name_and_adds_source(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    database_path = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_path, database_path)
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Culinary Profile",
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    client = app.test_client()
    careers_url = (
        "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/"
        "recruitment.html?cid=example-tenant"
        "&ccId=19000101_000001&lang=en_US"
    )

    response = client.post(
        "/companies/add/resolve",
        data={"company": careers_url},
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "ADP career site" in html
    assert "ADP uses a shared careers address" in html
    assert 'name="company_name"' in html
    assert 'placeholder="Enter the employer\'s name"' in html
    assert "needs an administrator" not in html

    confirmed = client.post(
        "/companies/add/confirm-detected",
        data={
            "company_name": "Example Hospitality",
            "careers_url": careers_url,
        },
    )
    assert confirmed.status_code == 302
    assert confirmed.headers["Location"].startswith("/companies?")
    employer = get_employer_source(database_path, "example-hospitality")
    assert employer is not None
    assert employer.source_type == "adp"
    assert get_profile(database_path, profile.profile_id).company_ids == (
        "example-hospitality",
    )


def test_profile_can_correct_company_name_without_changing_source(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    database_path = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_path, database_path)
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="example_company",
            name="Exampel Company",
            source_type="lever",
            source_config={"source_slug": "example-company"},
        ),
    )
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Test Profile",
        company_ids=("example_company",),
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    client = app.test_client()

    response = client.post(
        "/companies/example_company/name",
        data={"company_name": "Example Company"},
        follow_redirects=True,
    )
    employer = get_employer_source(database_path, "example_company")

    assert response.status_code == 200
    assert "shared company name is now Example Company" in response.get_data(
        as_text=True
    )
    assert employer is not None
    assert employer.name == "Example Company"
    assert employer.source_type == "lever"
    assert employer.source_config == {"source_slug": "example-company"}
