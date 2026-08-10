"""Verify company pages display active-profile employer ownership."""

import json
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


def test_companies_page_shows_global_catalog_with_profile_scan_state(
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
    assert "Unassigned Bakery" in html
    assert "Scanning" in html
    assert "Not scanning" in html
    assert "Legacy config file:" not in html
    assert "Source type" not in html
    assert "https://law.invalid/jobs" not in html
    assert "Local legal employer." not in html
    assert "Add company" in html
    assert "Companies and source health" in html
    assert '<details class="page-card company-health-section" id="company-sources">' in html
    assert '<details class="page-card company-health-section" id="company-sources" open>' not in html
    assert "Verification needed: 3 sources have not been tested." in html
    assert "Test all untested sources" in html
    assert "Test selected sources" in html
    assert 'class="test-selection-column"' in html
    assert 'class="source-select"' in html
    assert 'class="profile-scan-switch" aria-hidden="true"' in html
    assert ".company-health-table .test-selection-column { width: 42px; }" in html
    assert ".company-health-table.selection-mode .test-selection-column" not in html
    assert 'class="button-secondary source-test-one"' not in html
    assert "Scan selected companies" not in html
    assert 'id="source-test-meter"' in html
    assert 'X-Junior-Background-Test": "1"' in html
    assert 'submittedButton.textContent = "Starting tests..."' in html
    assert "let startedOnThisPage = false;" in html
    assert "window.location.reload();" in html
    assert "testButtons.forEach((button) => { button.disabled = true; });" in html
    assert ">Remove</button>" not in html
    assert "Find a company" in html
    assert '<option value="healthy">Healthy</option>' in html
    assert (
        '<option value="attention">Not healthy (attention or untested)</option>'
        in html
    )
    assert '<option value="untested">Not tested</option>' in html
    assert 'aria-label="Select all visible company sources"' in html
    assert 'data-health-state="not_tested"' in html
    assert 'row.dataset.healthState === "error"' in html
    assert 'row.dataset.healthState === "not_tested"' in html
    assert "if (checkbox && !row.hidden)" in html
    assert "if (checkbox) checkbox.checked = false;" in html
    assert "Run selected tests" in html
    assert "<summary>More</summary>" not in html


def test_companies_page_collapsed_source_health_summary_turns_green(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    database_path = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_path, database_path)
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="healthy_company",
            name="Healthy Company",
            source_type="greenhouse",
            source_config={"source_slug": "healthy-company"},
        ),
    )
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Test Profile",
        company_ids=("healthy_company",),
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    monkeypatch.setattr(
        "job_radar.employer_connection_service.collect_jobs_for_company",
        lambda config: [object()],
    )
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    client = app.test_client()

    client.post("/companies/healthy_company/test-source")
    html = client.get("/companies").get_data(as_text=True)

    assert "Healthy: all 1 company source is working." in html
    assert 'class="company-health-overall status-enabled"' in html


def test_company_source_test_normal_form_submission_returns_to_companies(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    database_path = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_path, database_path)

    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Test Profile",
        company_ids=("assigned_law",),
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="assigned_law",
            name="Assigned Law Firm",
            source_type="html",
            source_config={"source_url": "https://law.invalid/jobs"},
        ),
    )

    monkeypatch.setattr(
        "job_radar.source_test_runner.SourceTestRunner.start",
        lambda _self, *_args, **_kwargs: True,
    )
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    client = app.test_client()

    response = client.post(
        "/companies/test-sources",
        data={"employer_id": "assigned_law", "test_scope": "selected"},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/companies")


def test_company_source_test_background_request_returns_status_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    database_path = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_path, database_path)

    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Test Profile",
        company_ids=("assigned_law",),
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="assigned_law",
            name="Assigned Law Firm",
            source_type="html",
            source_config={"source_url": "https://law.invalid/jobs"},
        ),
    )

    monkeypatch.setattr(
        "job_radar.source_test_runner.SourceTestRunner.start",
        lambda _self, *_args, **_kwargs: True,
    )
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    client = app.test_client()

    response = client.post(
        "/companies/test-sources",
        data={"employer_id": "assigned_law", "test_scope": "selected"},
        headers={"X-Junior-Background-Test": "1"},
    )

    assert response.status_code == 202
    assert response.get_json() == {"status": "starting", "total": 1}


def test_company_source_test_waits_for_running_scan(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.yaml"
    database_path = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_path, database_path)
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Test Profile",
        company_ids=("assigned_law",),
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="assigned_law",
            name="Assigned Law Firm",
            source_type="html",
            source_config={"source_url": "https://law.invalid/jobs"},
        ),
    )
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    app.extensions["junior_scan_runner"]._running = True
    client = app.test_client()

    response = client.post(
        "/companies/test-sources",
        data={"employer_id": "assigned_law", "test_scope": "selected"},
        headers={"X-Junior-Background-Test": "1"},
    )

    assert response.status_code == 409
    assert "Wait for the current scan to finish" in response.get_json()["message"]


def test_company_detail_allows_global_catalog_employer_not_scanned_by_profile(
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
    assert "https://contractor.invalid/jobs" in assigned_response.get_data(
        as_text=True
    )
    assert unassigned_response.status_code == 200


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
    assert "Scan for this profile" in initial_html
    assert "1</strong>" in initial_html

    paused_response = client.post(
        "/companies/example_cafe/scanning",
        data={"state": "paused"},
        follow_redirects=True,
    )
    paused_html = paused_response.get_data(as_text=True)

    assert paused_response.status_code == 200
    assert "Example Cafe is now not scanned for Culinary Profile&#39;s profile." in (
        paused_html
    )
    assert 'class="flash-dismiss"' in paused_html
    assert "Example Cafe is now not scanned" not in client.get(
        "/companies"
    ).get_data(as_text=True)
    assert "Not scanning" in paused_html
    assert is_profile_employer_enabled(
        database_path, profile.profile_id, "example_cafe"
    ) is False

    resumed_response = client.post(
        "/companies/example_cafe/scanning",
        data={"state": "scanning"},
        follow_redirects=True,
    )

    assert resumed_response.status_code == 200
    assert "Example Cafe is now included in scans" in resumed_response.get_data(
        as_text=True
    )
    assert is_profile_employer_enabled(
        database_path, profile.profile_id, "example_cafe"
    ) is True

    background_response = client.post(
        "/companies/example_cafe/scanning",
        data={"state": "not_scanning"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert background_response.status_code == 200
    assert background_response.get_json() == {
        "company": "Example Cafe",
        "scanning": False,
        "state_label": "not scanned",
        "status": "saved",
    }
    assert is_profile_employer_enabled(
        database_path, profile.profile_id, "example_cafe"
    ) is False


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
    assert "Choose whether this profile should scan" in invalid_response.get_data(as_text=True)
    assert is_profile_employer_enabled(
        database_path, profile.profile_id, "example_cafe"
    ) is True

    set_active_profile(database_path, None)
    legacy_response = client.post(
        "/companies/example_cafe/scanning",
        data={"state": "paused"},
    )
    assert legacy_response.status_code == 302
    assert legacy_response.headers["Location"] == "/companies"
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
    assert "Confirm the company change" in missing_confirmation.get_data(as_text=True)
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
    assert "Example Cafe is no longer scanned for Culinary Profile" in html
    assert "Existing history was kept." in html
    assert "Example Cafe" in html
    assert "Not scanning" in html
    assert get_profile(database_path, active_profile.profile_id).company_ids == ()
    assert get_profile(database_path, other_profile.profile_id).company_ids == (
        "example_cafe",
    )
    assert get_employer_source(database_path, "example_cafe") is not None
    assert client.get("/companies/example_cafe").status_code == 200


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

    assert "paste any official" in page_html
    assert "company webpage to add a new one" in page_html
    assert "homepage, careers page, department page" in page_html

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


def test_name_only_addition_searches_catalog_only(
    tmp_path: Path,
    monkeypatch,
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
        data={"company": "Example Kitchens"},
    )

    assert response.status_code == 200
    assert "paste any official company webpage" in response.get_data(as_text=True)
    assert get_profile(database_path, profile.profile_id).company_ids == ()


def test_add_company_by_careers_url_requires_detected_source_confirmation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "job_radar.employer_resolution_service.collect_jobs_for_company",
        lambda config: [object()],
    )
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
    assert confirmed.headers["Location"] == "/companies"
    assert get_profile(database_path, profile.profile_id).company_ids == (
        "example-kitchens",
    )


def test_add_company_by_complete_adp_url_requests_name_and_adds_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "job_radar.employer_resolution_service.collect_jobs_for_company",
        lambda config: [object(), object()],
    )
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
    assert confirmed.headers["Location"] == "/companies"
    employer = get_employer_source(database_path, "example-hospitality")
    assert employer is not None
    assert employer.source_type == "adp"
    assert get_profile(database_path, profile.profile_id).company_ids == (
        "example-hospitality",
    )


def test_unknown_company_source_explains_compatibility_limit(
    tmp_path: Path,
    monkeypatch,
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
    monkeypatch.setattr(
        "job_radar.employer_resolution_service._discover_branded_sources",
        lambda url, **kwargs: [],
    )
    monkeypatch.setattr(
        "job_radar.employer_resolution_service.collect_jobs_for_company",
        lambda config: [],
    )

    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    client = app.test_client()

    response = client.post(
        "/companies/add/confirm-detected",
        data={
            "company_name": "Example Kitchens",
            "careers_url": (
                "https://careers.example.invalid/jobs?tenant=hidden"
            ),
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "could not yet identify and validate its job platform" in html
    assert "You do not need to find another URL" in html
    assert "claytonmgraves@outlook.com" in html
    assert get_profile(database_path, profile.profile_id).company_ids == ()
    events = [
        json.loads(line)
        for line in (tmp_path / "logs" / "junior-application.log")
        .read_text(encoding="utf-8")
        .splitlines()
        if '"subsystem": "company_discovery"' in line
    ]
    assert events[0]["stage"] == "attempt_started"
    assert events[-1]["stage"] == "attempt_finished"
    assert events[-1]["attempt_id"] == events[0]["attempt_id"]
    assert events[-1]["submission_type"] == "confirmed_url"
    assert events[-1]["submitted_host"] == "careers.example.invalid"
    assert events[-1]["final_status"] == "UNSUPPORTED_SITE"
    assert events[-1]["company_created"] is False
    assert events[-1]["company_assigned"] is False
    assert events[-1]["elapsed_seconds"] >= 0


def test_company_detail_shows_and_refreshes_safe_source_health(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    database_path = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_path, database_path)
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="example_company",
            name="Example Company",
            source_type="workday",
            source_config={
                "source_url": "https://example.invalid/api/jobs",
                "source_base_url": "https://example.invalid/jobs",
            },
        ),
    )
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Test Profile",
        company_ids=("example_company",),
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    monkeypatch.setattr(
        "job_radar.employer_connection_service.collect_jobs_for_company",
        lambda config: [object()] * 12,
    )
    app = create_app(settings_path=settings_path, base_directory=tmp_path)
    client = app.test_client()

    initial_html = client.get(
        "/companies/example_company"
    ).get_data(as_text=True)
    tested = client.post(
        "/companies/example_company/test-source",
        follow_redirects=True,
    )
    tested_html = tested.get_data(as_text=True)

    assert "Not tested" in initial_html
    assert "Workday" in initial_html
    assert "Source Junior scans" in initial_html
    assert "https://example.invalid/api/jobs" in initial_html
    assert "Test job source" in initial_html
    assert 'data-submit-pending-label="Testing job source..."' in initial_html
    assert "Connection succeeded and returned 12 jobs." in tested_html
    assert "Connected" in tested_html
    assert "Jobs returned" in tested_html
    assert tested_html.count("Connection succeeded and returned 12 jobs.") == 1
    assert 'class="flash-dismiss"' not in tested_html
    assert "Unlock Administration to edit the job source" in initial_html

    client.post(
        "/administration/unlock",
        data={
            "confirmation": "ADMIN",
            "next": "/companies/example_company",
        },
    )
    admin_html = client.get("/companies/example_company").get_data(as_text=True)

    assert "Edit job source" in admin_html
    assert (
        'href="/administration/employers/example_company/edit"' in admin_html
    )


def test_company_detail_withholds_credential_bearing_source_url(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    database_path = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_path, database_path)
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="private_source",
            name="Private Source",
            source_type="html",
            source_config={
                "source_url": "https://example.invalid/jobs?access_token=hidden",
            },
        ),
    )
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Test Profile",
        company_ids=("private_source",),
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    app = create_app(settings_path=settings_path, base_directory=tmp_path)

    html = app.test_client().get("/companies/private_source").get_data(as_text=True)

    assert "access_token" not in html
    assert "public request address is not available" in html


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


def test_profile_can_save_and_open_company_links_without_changing_source(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    database_path = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_path, database_path)
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="example_company",
            name="Example Company",
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
        "/companies/example_company/links",
        data={
            "website_url": "https://example.invalid",
            "careers_link_url": "https://example.invalid/careers",
            "linkedin_url": (
                "https://www.linkedin.com/company/example-company"
            ),
            "glassdoor_url": (
                "https://www.glassdoor.com/Overview/example-company"
            ),
        },
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)
    employer = get_employer_source(database_path, "example_company")

    assert response.status_code == 200
    assert "working job source was not changed" in html
    assert "Open website" in html
    assert "Open careers" in html
    assert "Open LinkedIn" in html
    assert "Open Glassdoor" in html
    assert employer is not None
    assert employer.source_type == "lever"
    assert employer.source_config["source_slug"] == "example-company"
    assert employer.source_config["linkedin_url"].startswith(
        "https://www.linkedin.com/"
    )


def test_company_links_reject_wrong_social_domain_and_preserve_source(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    database_path = tmp_path / "job_radar.sqlite3"
    write_settings_file(settings_path, database_path)
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="example_company",
            name="Example Company",
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
        "/companies/example_company/links",
        data={"linkedin_url": "https://example.invalid/not-linkedin"},
        follow_redirects=True,
    )
    employer = get_employer_source(database_path, "example_company")

    assert response.status_code == 200
    assert "must use an official linkedin.com address" in response.get_data(
        as_text=True
    )
    assert employer is not None
    assert employer.source_config == {"source_slug": "example-company"}
