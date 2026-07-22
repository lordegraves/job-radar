"""Verify global employer creation and active-profile assignment."""

from pathlib import Path

import pytest

from job_radar.employer_management import (
    EmployerManagementError,
    add_employer_to_active_profile,
)
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


def create_active_profile(database_path: Path) -> ManagedProfile:
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Example Profile",
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    return profile


def test_add_employer_creates_global_record_and_assigns_active_profile(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    profile = create_active_profile(database_path)

    result = add_employer_to_active_profile(
        database_path,
        name="Example Bakery",
        source_type="html",
        source_config={
            "source_url": "https://example.invalid/careers",
        },
        notes="Local bakery employer.",
    )

    assert result.created is True
    assert result.assigned is True
    assert result.employer.employer_id == "example_bakery"
    assert get_employer_source(
        database_path,
        result.employer.employer_id,
    ) == result.employer

    stored_profile = get_profile(database_path, profile.profile_id)

    assert stored_profile is not None
    assert stored_profile.company_ids == ("example_bakery",)


def test_add_employer_reuses_existing_global_record(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    profile = create_active_profile(database_path)
    existing = EmployerSource(
        employer_id="existing_bakery",
        name="Example Bakery",
        source_type="greenhouse",
        source_config={
            "source_slug": "example-bakery",
        },
    )
    upsert_employer_source(database_path, existing)

    result = add_employer_to_active_profile(
        database_path,
        name="  example bakery  ",
        source_type="html",
        source_config={
            "source_url": "https://replacement.invalid/careers",
        },
    )

    assert result.employer == existing
    assert result.created is False
    assert result.assigned is True
    assert list_employer_sources(database_path) == [existing]

    stored_profile = get_profile(database_path, profile.profile_id)

    assert stored_profile is not None
    assert stored_profile.company_ids == ("existing_bakery",)


def test_add_employer_reports_existing_profile_assignment(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    create_active_profile(database_path)

    first_result = add_employer_to_active_profile(
        database_path,
        name="Example Employer",
        source_type="html",
        source_config={
            "source_url": "https://example.invalid/careers",
        },
    )
    second_result = add_employer_to_active_profile(
        database_path,
        name="Example Employer",
        source_type="html",
        source_config={
            "source_url": "https://example.invalid/careers",
        },
    )

    assert first_result.created is True
    assert first_result.assigned is True
    assert second_result.created is False
    assert second_result.assigned is False
    assert second_result.employer == first_result.employer


def test_add_employer_requires_active_profile(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"

    with pytest.raises(
        EmployerManagementError,
        match="active profile is required",
    ):
        add_employer_to_active_profile(
            database_path,
            name="Example Employer",
            source_type="html",
            source_config={
                "source_url": "https://example.invalid/careers",
            },
        )


def test_add_employer_requires_nonempty_name(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    create_active_profile(database_path)

    with pytest.raises(
        EmployerManagementError,
        match="name cannot be empty",
    ):
        add_employer_to_active_profile(
            database_path,
            name="   ",
            source_type="html",
            source_config={
                "source_url": "https://example.invalid/careers",
            },
        )
