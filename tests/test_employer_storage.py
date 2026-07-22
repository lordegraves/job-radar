"""Verify app-owned employer source persistence."""

from pathlib import Path

from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import (
    assign_employer_to_profile,
    delete_employer_source,
    get_employer_source,
    is_profile_employer_enabled,
    list_employer_sources,
    list_profile_employer_assignments,
    set_profile_employer_enabled,
    unassign_employer_from_profile,
    upsert_employer_source,
)


def make_employer(
    *,
    employer_id: str = "example_bakery",
    name: str = "Example Bakery",
    enabled: bool = True,
) -> EmployerSource:
    return EmployerSource(
        employer_id=employer_id,
        name=name,
        source_type="greenhouse",
        enabled=enabled,
        source_config={
            "source_slug": employer_id,
            "query_params": {
                "location": "Carrollton",
            },
            "page_size": 50,
        },
        notes="Synthetic employer used only for tests.",
    )


def test_employer_source_round_trip_preserves_complete_config(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    employer = make_employer()

    upsert_employer_source(database_path, employer)

    assert get_employer_source(database_path, employer.employer_id) == employer


def test_upsert_employer_source_replaces_editable_values(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    original = make_employer()
    updated = EmployerSource(
        employer_id=original.employer_id,
        name="Updated Bakery",
        source_type="html",
        enabled=False,
        source_config={
            "source_url": "https://example.invalid/careers",
        },
        notes="Updated synthetic employer.",
    )

    upsert_employer_source(database_path, original)
    upsert_employer_source(database_path, updated)

    assert get_employer_source(database_path, original.employer_id) == updated


def test_list_employer_sources_filters_enabled_and_orders_by_name(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    disabled = make_employer(
        employer_id="disabled_law",
        name="Zeta Law",
        enabled=False,
    )
    enabled = make_employer(
        employer_id="enabled_bakery",
        name="Alpha Bakery",
    )

    upsert_employer_source(database_path, disabled)
    upsert_employer_source(database_path, enabled)

    assert list_employer_sources(database_path) == [enabled, disabled]
    assert list_employer_sources(database_path, enabled_only=True) == [enabled]


def test_assign_and_unassign_employer_for_profile(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    employer = make_employer()
    upsert_employer_source(database_path, employer)

    from job_radar.profile_models import ManagedProfile
    from job_radar.profile_storage import create_profile, get_profile

    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Example Profile",
    )
    create_profile(database_path, profile)

    assert (
        assign_employer_to_profile(
            database_path,
            profile.profile_id,
            employer.employer_id,
        )
        is True
    )
    assert (
        assign_employer_to_profile(
            database_path,
            profile.profile_id,
            employer.employer_id,
        )
        is False
    )

    stored_profile = get_profile(database_path, profile.profile_id)

    assert stored_profile is not None
    assert stored_profile.company_ids == (employer.employer_id,)

    assert (
        unassign_employer_from_profile(
            database_path,
            profile.profile_id,
            employer.employer_id,
        )
        is True
    )
    assert (
        unassign_employer_from_profile(
            database_path,
            profile.profile_id,
            employer.employer_id,
        )
        is False
    )

    stored_profile = get_profile(database_path, profile.profile_id)

    assert stored_profile is not None
    assert stored_profile.company_ids == ()


def test_profile_employer_assignment_defaults_to_enabled(
    tmp_path: Path,
) -> None:
    from job_radar.employer_models import ProfileEmployerAssignment
    from job_radar.profile_models import ManagedProfile
    from job_radar.profile_storage import create_profile

    database_path = tmp_path / "job_radar.sqlite3"
    employer = make_employer()
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Example Profile",
    )

    upsert_employer_source(database_path, employer)
    create_profile(database_path, profile)
    assign_employer_to_profile(
        database_path,
        profile.profile_id,
        employer.employer_id,
    )

    assert list_profile_employer_assignments(
        database_path,
        profile.profile_id,
    ) == [
        ProfileEmployerAssignment(
            profile_id=profile.profile_id,
            employer_id=employer.employer_id,
            enabled=True,
        )
    ]
    assert (
        is_profile_employer_enabled(
            database_path,
            profile.profile_id,
            employer.employer_id,
        )
        is True
    )


def test_profile_employer_assignment_enabled_state_can_be_changed(
    tmp_path: Path,
) -> None:
    from job_radar.employer_models import ProfileEmployerAssignment
    from job_radar.profile_models import ManagedProfile
    from job_radar.profile_storage import create_profile

    database_path = tmp_path / "job_radar.sqlite3"
    employer = make_employer()
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Example Profile",
    )

    upsert_employer_source(database_path, employer)
    create_profile(database_path, profile)
    assign_employer_to_profile(
        database_path,
        profile.profile_id,
        employer.employer_id,
    )

    assert (
        set_profile_employer_enabled(
            database_path,
            profile.profile_id,
            employer.employer_id,
            enabled=False,
        )
        is True
    )
    assert (
        is_profile_employer_enabled(
            database_path,
            profile.profile_id,
            employer.employer_id,
        )
        is False
    )
    assert list_profile_employer_assignments(
        database_path,
        profile.profile_id,
    ) == [
        ProfileEmployerAssignment(
            profile_id=profile.profile_id,
            employer_id=employer.employer_id,
            enabled=False,
        )
    ]

    assert (
        set_profile_employer_enabled(
            database_path,
            profile.profile_id,
            employer.employer_id,
            enabled=True,
        )
        is True
    )
    assert (
        is_profile_employer_enabled(
            database_path,
            profile.profile_id,
            employer.employer_id,
        )
        is True
    )


def test_profile_employer_assignment_state_requires_existing_assignment(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"

    assert (
        is_profile_employer_enabled(
            database_path,
            "profile_missing",
            "employer_missing",
        )
        is False
    )
    assert (
        set_profile_employer_enabled(
            database_path,
            "profile_missing",
            "employer_missing",
            enabled=False,
        )
        is False
    )
    assert (
        list_profile_employer_assignments(
            database_path,
            "profile_missing",
        )
        == []
    )


def test_delete_employer_source_returns_whether_record_existed(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    employer = make_employer()
    upsert_employer_source(database_path, employer)

    assert delete_employer_source(database_path, employer.employer_id) is True
    assert delete_employer_source(database_path, employer.employer_id) is False
    assert get_employer_source(database_path, employer.employer_id) is None
