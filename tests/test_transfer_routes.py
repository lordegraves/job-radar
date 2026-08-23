"""Exercise profile and company transfers through the normal GUI routes."""

from io import BytesIO
from pathlib import Path

from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import list_employer_sources, upsert_employer_source
from job_radar.config import ConfigError
from job_radar.profile_models import ManagedProfile
from job_radar.profile_scoring import build_neutral_scoring_config
from job_radar.profile_storage import create_profile, get_active_profile, list_profiles, set_active_profile
from job_radar.web_app import create_app


def _settings(path: Path, database: Path) -> None:
    path.write_text(
        f"database_path: {database}\nreports_path: {path.parent / 'reports'}\nlogs_path: {path.parent / 'logs'}\n",
        encoding="utf-8",
    )


def test_profile_page_exports_named_profile_and_imports_inactive_copy(tmp_path: Path) -> None:
    settings = tmp_path / "settings.yaml"
    database = tmp_path / "junior.sqlite3"
    _settings(settings, database)
    first = ManagedProfile(
        profile_id="profile_11111111",
        display_name="First Profile",
    )
    second = ManagedProfile(
        profile_id="profile_22222222",
        display_name="Tester Profile",
    )
    create_profile(database, first)
    create_profile(database, second)
    set_active_profile(database, first.profile_id)
    client = create_app(settings_path=settings, base_directory=tmp_path).test_client()

    page = client.get("/profile").get_data(as_text=True)
    assert "Import or export a profile" in page
    assert "First Profile" in page
    assert "Tester Profile" in page
    exported = client.post("/profile/export", data={"profile_id": second.profile_id})
    assert exported.status_code == 200
    assert exported.headers["Content-Disposition"].endswith(
        'filename="junior-profile-configuration.json"'
    )

    imported = client.post(
        "/profile/import",
        data={
            "profile_file": (
                BytesIO(exported.data),
                "junior-profile-configuration.json",
            )
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert imported.status_code == 200
    assert "Profile imported." in imported.get_data(as_text=True)
    assert len(list_profiles(database)) == 3
    assert get_active_profile(database) == first
    assert any(
        profile.display_name == "Tester Profile (Imported)"
        and profile.resume is None
        for profile in list_profiles(database)
    )


def test_profile_route_exports_legacy_scoring_without_internal_error(
    tmp_path: Path,
) -> None:
    settings = tmp_path / "settings.yaml"
    database = tmp_path / "junior.sqlite3"
    _settings(settings, database)
    scoring = build_neutral_scoring_config()
    del scoring["top_matches"]["review_signals"]
    profile = ManagedProfile(
        profile_id="profile_11111111",
        display_name="Legacy Profile",
        scoring_config=scoring,
    )
    create_profile(database, profile)
    client = create_app(settings_path=settings, base_directory=tmp_path).test_client()

    response = client.post(
        "/profile/export",
        data={"profile_id": profile.profile_id},
    )

    assert response.status_code == 200
    assert response.headers["Content-Disposition"].endswith(
        'filename="junior-profile-configuration.json"'
    )


def test_profile_route_reports_expected_export_failure_safely(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = tmp_path / "settings.yaml"
    database = tmp_path / "junior.sqlite3"
    _settings(settings, database)
    profile = ManagedProfile(
        profile_id="profile_11111111",
        display_name="Saved Profile",
    )
    create_profile(database, profile)
    set_active_profile(database, profile.profile_id)

    def fail_export(*_args, **_kwargs):
        raise ConfigError("private export detail")

    monkeypatch.setattr(
        "job_radar.web_routes.profile.export_profile",
        fail_export,
    )
    client = create_app(settings_path=settings, base_directory=tmp_path).test_client()

    response = client.post(
        "/profile/export",
        data={"profile_id": profile.profile_id},
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Junior could not export that profile." in html
    assert "claytonmgraves@outlook.com" in html
    assert "private export detail" not in html


def test_companies_page_import_appends_global_catalog_only(tmp_path: Path) -> None:
    source_settings = tmp_path / "source-settings.yaml"
    source_database = tmp_path / "source.sqlite3"
    destination_settings = tmp_path / "destination-settings.yaml"
    destination_database = tmp_path / "destination.sqlite3"
    _settings(source_settings, source_database)
    _settings(destination_settings, destination_database)
    upsert_employer_source(
        source_database,
        EmployerSource(
            employer_id="new_company",
            name="New Company",
            source_type="greenhouse",
            source_config={"source_slug": "new-company"},
        ),
    )
    current = ManagedProfile(
        profile_id="profile_11111111",
        display_name="Current Profile",
    )
    create_profile(destination_database, current)
    set_active_profile(destination_database, current.profile_id)
    source_client = create_app(
        settings_path=source_settings,
        base_directory=tmp_path,
    ).test_client()
    destination_client = create_app(
        settings_path=destination_settings,
        base_directory=tmp_path,
    ).test_client()

    exported = source_client.get("/companies/export")
    imported = destination_client.post(
        "/companies/import",
        data={
            "company_file": (
                BytesIO(exported.data),
                "junior-company-catalog.json",
            )
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    html = imported.get_data(as_text=True)
    assert "Added 1 companies to the global catalog" in html
    assert "No profile company list was changed" in html
    assert len(list_employer_sources(destination_database)) == 51
    assert get_active_profile(destination_database).company_ids == ()
