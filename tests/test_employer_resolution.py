"""Verify profile-aware employer resolution for scans."""

from pathlib import Path

import pytest

from job_radar.config import ConfigError
from job_radar.database import connect_database
from job_radar.employer_models import EmployerSource
from job_radar.employer_resolution import resolve_scan_companies
from job_radar.employer_storage import (
    set_profile_employer_enabled,
    upsert_employer_source,
)
from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import (
    create_profile,
    get_profile,
    set_active_profile,
)
from job_radar.storage import initialize_database


def write_company_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
companies:
  - company_key: legacy_enabled
    name: Legacy Enabled
    source_type: greenhouse
    source_slug: legacy-enabled
    enabled: true
  - company_key: legacy_disabled
    name: Legacy Disabled
    source_type: lever
    source_slug: legacy-disabled
    enabled: false
""".strip()
        + "\n",
        encoding="utf-8",
    )


def mark_company_import_pending(
    database_path: Path,
    profile_id: str,
) -> None:
    with connect_database(database_path) as connection:
        connection.execute(
            """
            UPDATE profiles
            SET legacy_company_import_pending = 1
            WHERE profile_id = ?
            """,
            (profile_id,),
        )


def test_resolve_scan_companies_preserves_yaml_fallback_without_active_profile(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    company_config_path = tmp_path / "config" / "target-companies.yaml"
    write_company_file(company_config_path)

    companies = resolve_scan_companies(
        database_path,
        company_config_path,
    )

    assert companies == [
        {
            "company_key": "legacy_enabled",
            "name": "Legacy Enabled",
            "source_type": "greenhouse",
            "source_slug": "legacy-enabled",
            "enabled": True,
        }
    ]


def test_resolve_scan_companies_uses_only_active_profile_enabled_employers(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    company_config_path = tmp_path / "config" / "target-companies.yaml"
    write_company_file(company_config_path)

    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Baker Profile",
        company_ids=(
            "local_bakery",
            "disabled_grocery",
        ),
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
            employer_id="disabled_grocery",
            name="Disabled Grocery",
            source_type="greenhouse",
            enabled=False,
            source_config={
                "source_slug": "disabled-grocery",
            },
        ),
    )

    companies = resolve_scan_companies(
        database_path,
        company_config_path,
    )

    assert companies == [
        {
            "company_key": "local_bakery",
            "name": "Local Bakery",
            "source_type": "html",
            "enabled": True,
            "source_url": "https://bakery.invalid/jobs",
        }
    ]


def test_resolve_scan_companies_can_limit_scan_to_selected_profile_employer(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    company_config_path = tmp_path / "config" / "target-companies.yaml"
    write_company_file(company_config_path)
    profile = ManagedProfile(
        profile_id="profile_selected",
        display_name="Selected Scan",
        company_ids=("first_company", "second_company"),
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    for employer_id in profile.company_ids:
        upsert_employer_source(
            database_path,
            EmployerSource(
                employer_id=employer_id,
                name=employer_id.replace("_", " ").title(),
                source_type="greenhouse",
                source_config={"source_slug": employer_id},
            ),
        )

    companies = resolve_scan_companies(
        database_path,
        company_config_path,
        selected_employer_ids={"second_company"},
    )

    assert [item["company_key"] for item in companies] == ["second_company"]


def test_resolve_scan_companies_skips_profile_disabled_employer(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    company_config_path = tmp_path / "config" / "target-companies.yaml"
    write_company_file(company_config_path)

    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Baker Profile",
        company_ids=(
            "local_bakery",
            "disabled_market",
        ),
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
            enabled=True,
            source_config={
                "source_slug": "disabled-market",
            },
        ),
    )

    set_profile_employer_enabled(
        database_path,
        profile.profile_id,
        "disabled_market",
        enabled=False,
    )

    companies = resolve_scan_companies(
        database_path,
        company_config_path,
    )

    assert companies == [
        {
            "company_key": "local_bakery",
            "name": "Local Bakery",
            "source_type": "html",
            "enabled": True,
            "source_url": "https://bakery.invalid/jobs",
        }
    ]


def test_resolve_scan_companies_runs_pending_legacy_import_once(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    company_config_path = tmp_path / "config" / "target-companies.yaml"
    write_company_file(company_config_path)
    initialize_database(database_path)

    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Existing Profile",
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    mark_company_import_pending(database_path, profile.profile_id)

    companies = resolve_scan_companies(
        database_path,
        company_config_path,
    )

    assert companies == [
        {
            "company_key": "legacy_enabled",
            "name": "Legacy Enabled",
            "source_type": "greenhouse",
            "source_slug": "legacy-enabled",
            "enabled": True,
        }
    ]

    stored_profile = get_profile(database_path, profile.profile_id)

    assert stored_profile is not None
    assert stored_profile.company_ids == (
        "legacy_disabled",
        "legacy_enabled",
    )

    company_config_path.unlink()

    assert resolve_scan_companies(
        database_path,
        company_config_path,
    ) == companies


def test_resolve_scan_companies_rejects_active_profile_without_enabled_employers(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    company_config_path = tmp_path / "missing-target-companies.yaml"

    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="New Paralegal Profile",
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)

    with pytest.raises(
        ConfigError,
        match="has no enabled employers",
    ):
        resolve_scan_companies(
            database_path,
            company_config_path,
        )


def test_resolve_scan_companies_rejects_missing_assigned_employer(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    company_config_path = tmp_path / "missing-target-companies.yaml"

    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Electrician Profile",
        company_ids=("missing_contractor",),
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)

    with pytest.raises(
        ConfigError,
        match="missing_contractor",
    ):
        resolve_scan_companies(
            database_path,
            company_config_path,
        )
