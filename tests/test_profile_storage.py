"""Tests managed profile persistence using only synthetic temporary databases."""

import sqlite3
from pathlib import Path

import pytest

from job_radar.profile_models import (
    LocationPreference,
    ManagedProfile,
    OccupationPreference,
    ProfilePreferences,
    build_managed_resume,
)
from job_radar.profile_storage import (
    ProfileAlreadyExistsError,
    ProfileSelectionError,
    create_profile,
    get_active_profile,
    get_profile,
    list_profiles,
    set_active_profile,
    set_profile_archived,
    update_profile,
)
from job_radar.storage import initialize_database


def make_profile(
    *,
    profile_id: str = "profile_1a2b3c4d",
    display_name: str = "Example Candidate",
    archived: bool = False,
) -> ManagedProfile:
    return ManagedProfile(
        profile_id=profile_id,
        display_name=display_name,
        preferences=ProfilePreferences(
            target_roles=("Technical Writer",),
            seniority_levels=("Senior",),
            core_strengths=("Documentation systems",),
            credible_adjacent=("Developer education",),
            learning_or_gap=("Product marketing",),
            exclusions=("Commission sales",),
            preferred_locations=("Remote",),
            work_arrangements=("remote",),
            employment_types=("full-time",),
            schedule_preference="Weekdays",
            occupation_selections=(
                OccupationPreference(
                    value="15-1252.00", label="Software Developers"
                ),
            ),
            location_selections=(
                LocationPreference(
                    value="place:0827425",
                    label="Fort Collins, Colorado",
                    latitude=40.5853,
                    longitude=-105.0844,
                    radius_miles=25,
                ),
            ),
            compensation_floor_usd=120000,
            compensation_target_usd=145000,
            travel_tolerance="limited",
            on_call_preference="Not willing to participate",
        ),
        resume=build_managed_resume(".pdf"),
        company_ids=("example_company", "second_company"),
        report_settings={"retention": "latest_only"},
        archived=archived,
    )


def test_create_and_load_profile_round_trip(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    profile = make_profile()

    create_profile(database_path, profile)

    assert get_profile(database_path, profile.profile_id) == profile


def test_create_profile_rejects_duplicate_stable_id(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    profile = make_profile()
    create_profile(database_path, profile)

    with pytest.raises(ProfileAlreadyExistsError, match=profile.profile_id):
        create_profile(database_path, profile)

    assert list_profiles(database_path) == [profile]


def test_list_profiles_excludes_archived_profiles_by_default(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    active_profile = make_profile(
        profile_id="profile_11111111",
        display_name="Active Example",
    )
    archived_profile = make_profile(
        profile_id="profile_22222222",
        display_name="Archived Example",
        archived=True,
    )
    create_profile(database_path, active_profile)
    create_profile(database_path, archived_profile)

    assert list_profiles(database_path) == [active_profile]
    assert list_profiles(database_path, include_archived=True) == [
        active_profile,
        archived_profile,
    ]


def test_update_profile_replaces_editable_owned_data(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    original = make_profile()
    updated = ManagedProfile(
        profile_id=original.profile_id,
        display_name="Updated Example",
        preferences=ProfilePreferences(
            target_roles=("Research Engineer",),
            compensation_floor_usd=150000,
        ),
        resume=build_managed_resume(".docx"),
        company_ids=("updated_company",),
        report_settings={"retention": "latest_plus_previous"},
    )
    create_profile(database_path, original)

    assert update_profile(database_path, updated) is True
    assert get_profile(database_path, updated.profile_id) == updated


def test_update_profile_returns_false_for_missing_profile(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"

    assert update_profile(database_path, make_profile()) is False


def test_archive_and_restore_preserve_profile_data(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    profile = make_profile()
    create_profile(database_path, profile)

    assert set_profile_archived(
        database_path,
        profile.profile_id,
        archived=True,
    ) is True
    archived_profile = get_profile(database_path, profile.profile_id)
    assert archived_profile is not None
    assert archived_profile.archived is True
    assert archived_profile.preferences == profile.preferences
    assert archived_profile.resume == profile.resume

    assert set_profile_archived(
        database_path,
        profile.profile_id,
        archived=False,
    ) is True
    assert get_profile(database_path, profile.profile_id) == profile


def test_archive_returns_false_for_missing_profile(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"

    assert set_profile_archived(
        database_path,
        "profile_99999999",
        archived=True,
    ) is False


def test_active_profile_selection_round_trip_and_clear(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    first_profile = make_profile(profile_id="profile_11111111")
    second_profile = make_profile(profile_id="profile_22222222")
    create_profile(database_path, first_profile)
    create_profile(database_path, second_profile)

    assert get_active_profile(database_path) is None

    set_active_profile(database_path, first_profile.profile_id)
    assert get_active_profile(database_path) == first_profile

    set_active_profile(database_path, second_profile.profile_id)
    assert get_active_profile(database_path) == second_profile

    set_active_profile(database_path, None)
    assert get_active_profile(database_path) is None


def test_active_profile_selection_rejects_missing_or_archived_profile(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    archived_profile = make_profile(archived=True)
    create_profile(database_path, archived_profile)

    for profile_id in (archived_profile.profile_id, "profile_99999999"):
        with pytest.raises(ProfileSelectionError, match=profile_id):
            set_active_profile(database_path, profile_id)

    assert get_active_profile(database_path) is None


def test_profile_migration_does_not_change_existing_tables_or_rows(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "existing.sqlite3"

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE existing_user_data (value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO existing_user_data VALUES (?)",
            ("synthetic data must remain",),
        )

    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        value = connection.execute(
            "SELECT value FROM existing_user_data"
        ).fetchone()[0]
        profile_count = connection.execute(
            "SELECT COUNT(*) FROM profiles"
        ).fetchone()[0]
        migration_version = connection.execute(
            "SELECT name FROM schema_migrations WHERE version = 4"
        ).fetchone()[0]

    assert value == "synthetic data must remain"
    assert profile_count == 0
    assert migration_version == "add managed profile storage"
    assert len(list((tmp_path / "backups").glob("*.bak"))) == 1
