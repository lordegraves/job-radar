"""Verify profile-aware company-page source resolution."""

from pathlib import Path

from job_radar.company_view_resolution import resolve_company_page_source
from job_radar.database import connect_database
from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import upsert_employer_source
from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import create_profile, set_active_profile


def write_company_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
companies:
  - company_key: legacy_company
    name: Legacy Company
    source_type: greenhouse
    source_slug: legacy-company
    enabled: true
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_company_page_source_preserves_yaml_without_active_profile(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    company_config_path = tmp_path / "config" / "target-companies.yaml"
    write_company_file(company_config_path)

    source = resolve_company_page_source(
        database_path,
        company_config_path,
    )

    assert source.active_profile is None
    assert source.uses_legacy_yaml is True
    assert [company.company_key for company in source.companies] == [
        "legacy_company"
    ]


def test_company_page_source_uses_active_profile_assignments_only(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    company_config_path = tmp_path / "config" / "target-companies.yaml"
    write_company_file(company_config_path)

    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Baker Profile",
        company_ids=("local_bakery", "disabled_market"),
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)

    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="local_bakery",
            name="Local Bakery",
            source_type="html",
            enabled=True,
            source_config={
                "source_url": "https://bakery.invalid/jobs",
            },
        ),
    )
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="disabled_market",
            name="Disabled Market",
            source_type="greenhouse",
            enabled=False,
            source_config={
                "source_slug": "disabled-market",
            },
        ),
    )
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="unassigned_law",
            name="Unassigned Law Firm",
            source_type="lever",
            source_config={
                "source_slug": "unassigned-law",
            },
        ),
    )

    source = resolve_company_page_source(
        database_path,
        company_config_path,
    )

    assert source.active_profile is not None
    assert source.active_profile.profile_id == profile.profile_id
    assert source.active_profile.display_name == profile.display_name
    assert source.active_profile.company_ids == (
        "disabled_market",
        "local_bakery",
    )
    assert source.uses_legacy_yaml is False
    assert [company.company_key for company in source.companies] == [
        "disabled_market",
        "local_bakery",
    ]
    assert source.companies[0].enabled is False
    assert source.companies[1].source_detail == (
        "source_url: https://bakery.invalid/jobs"
    )


def test_company_page_source_imports_pending_legacy_companies(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    company_config_path = tmp_path / "config" / "target-companies.yaml"
    write_company_file(company_config_path)

    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Existing Profile",
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)

    with connect_database(database_path) as connection:
        connection.execute(
            """
            UPDATE profiles
            SET legacy_company_import_pending = 1
            WHERE profile_id = ?
            """,
            (profile.profile_id,),
        )

    source = resolve_company_page_source(
        database_path,
        company_config_path,
    )

    assert source.active_profile is not None
    assert [company.company_key for company in source.companies] == [
        "legacy_company"
    ]
