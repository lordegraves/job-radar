"""Verify one-time import of legacy YAML employers into active profiles."""

from pathlib import Path

import pytest

from job_radar.config import ConfigError
from job_radar.database import connect_database
from job_radar.employer_import import import_pending_legacy_employers
from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import (
    get_employer_source,
    list_employer_sources,
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
  - company_key: example_bakery
    name: Example Bakery
    source_type: greenhouse
    source_slug: example-bakery
    enabled: true
    notes: Local bakery target.
  - company_key: example_law
    name: Example Law
    source_type: workday
    source_url: https://example.invalid/jobs
    source_base_url: https://example.invalid
    enabled: false
    query_params:
      location: Carrollton
    page_size: 25
    max_pages: 3
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


def test_import_pending_legacy_employers_assigns_complete_sources_once(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    company_config_path = tmp_path / "config" / "target-companies.yaml"
    write_company_file(company_config_path)
    initialize_database(database_path)

    active_profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Existing Active Profile",
    )
    other_profile = ManagedProfile(
        profile_id="profile_bbbbbbbb",
        display_name="Existing Other Profile",
    )
    create_profile(database_path, active_profile)
    create_profile(database_path, other_profile)
    set_active_profile(database_path, active_profile.profile_id)
    mark_company_import_pending(database_path, active_profile.profile_id)

    imported_profile_id = import_pending_legacy_employers(
        database_path,
        company_config_path,
    )

    stored_active = get_profile(database_path, active_profile.profile_id)
    stored_other = get_profile(database_path, other_profile.profile_id)
    employers = list_employer_sources(database_path)

    assert imported_profile_id == active_profile.profile_id
    assert stored_active is not None
    assert stored_active.company_ids == (
        "example_bakery",
        "example_law",
    )
    assert stored_other is not None
    assert stored_other.company_ids == ()
    assert [employer.employer_id for employer in employers] == [
        "example_bakery",
        "example_law",
    ]

    bakery = get_employer_source(database_path, "example_bakery")
    law = get_employer_source(database_path, "example_law")

    assert bakery == EmployerSource(
        employer_id="example_bakery",
        name="Example Bakery",
        source_type="greenhouse",
        enabled=True,
        source_config={
            "source_slug": "example-bakery",
        },
        notes="Local bakery target.",
    )
    assert law == EmployerSource(
        employer_id="example_law",
        name="Example Law",
        source_type="workday",
        enabled=False,
        source_config={
            "source_url": "https://example.invalid/jobs",
            "source_base_url": "https://example.invalid",
            "query_params": {
                "location": "Carrollton",
            },
            "page_size": 25,
            "max_pages": 3,
        },
    )

    with connect_database(database_path) as connection:
        pending_value = connection.execute(
            """
            SELECT legacy_company_import_pending
            FROM profiles
            WHERE profile_id = ?
            """,
            (active_profile.profile_id,),
        ).fetchone()

    assert pending_value == (0,)
    assert (
        import_pending_legacy_employers(
            database_path,
            company_config_path,
        )
        is None
    )


def test_import_does_not_overwrite_existing_app_owned_employer(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    company_config_path = tmp_path / "config" / "target-companies.yaml"
    write_company_file(company_config_path)
    initialize_database(database_path)

    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Existing Active Profile",
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    mark_company_import_pending(database_path, profile.profile_id)

    app_owned_employer = EmployerSource(
        employer_id="example_bakery",
        name="User Edited Bakery",
        source_type="html",
        enabled=False,
        source_config={
            "source_url": "https://user.invalid/careers",
        },
        notes="User-owned edit must survive import.",
    )
    upsert_employer_source(database_path, app_owned_employer)

    imported_profile_id = import_pending_legacy_employers(
        database_path,
        company_config_path,
    )

    assert imported_profile_id == profile.profile_id
    assert (
        get_employer_source(database_path, "example_bakery")
        == app_owned_employer
    )

    stored_profile = get_profile(database_path, profile.profile_id)
    assert stored_profile is not None
    assert stored_profile.company_ids == (
        "example_bakery",
        "example_law",
    )


def test_new_profile_does_not_import_legacy_company_file(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    initialize_database(database_path)

    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="New Baker Profile",
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)

    imported_profile_id = import_pending_legacy_employers(
        database_path,
        tmp_path / "missing-target-companies.yaml",
    )

    assert imported_profile_id is None
    assert list_employer_sources(database_path) == []

    stored_profile = get_profile(database_path, profile.profile_id)
    assert stored_profile is not None
    assert stored_profile.company_ids == ()


def test_failed_legacy_import_preserves_pending_state_and_writes_nothing(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    company_config_path = tmp_path / "config" / "target-companies.yaml"
    company_config_path.parent.mkdir(parents=True)
    company_config_path.write_text(
        """
companies:
  - company_key: duplicate
    name: First Employer
    source_type: greenhouse
    source_slug: first
  - company_key: duplicate
    name: Second Employer
    source_type: lever
    source_slug: second
""".strip()
        + "\n",
        encoding="utf-8",
    )
    initialize_database(database_path)

    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Existing Active Profile",
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    mark_company_import_pending(database_path, profile.profile_id)

    with pytest.raises(ConfigError, match="Duplicate company_key"):
        import_pending_legacy_employers(
            database_path,
            company_config_path,
        )

    assert list_employer_sources(database_path) == []

    stored_profile = get_profile(database_path, profile.profile_id)
    assert stored_profile is not None
    assert stored_profile.company_ids == ()

    with connect_database(database_path) as connection:
        pending_value = connection.execute(
            """
            SELECT legacy_company_import_pending
            FROM profiles
            WHERE profile_id = ?
            """,
            (profile.profile_id,),
        ).fetchone()

    assert pending_value == (1,)
