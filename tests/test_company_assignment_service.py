"""Verify Pause and Resume change only the active profile's assignment."""

from pathlib import Path

import pytest

from job_radar.company_assignment_service import set_company_scanning_state
from job_radar.domain_errors import (
    EmployerNotAssignedError,
    EmployerNotFoundError,
    NoActiveProfileError,
)
from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import (
    get_employer_source,
    is_profile_employer_enabled,
    upsert_employer_source,
)
from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import create_profile, set_active_profile


def add_employer(database_path: Path, employer_id: str, name: str) -> None:
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id=employer_id,
            name=name,
            source_type="html",
            source_config={"source_url": f"https://{employer_id}.invalid/jobs"},
        ),
    )


def test_pause_and_resume_change_only_active_profile_assignment(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    add_employer(database_path, "example_market", "Example Market")
    active_profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Active Profile",
        company_ids=("example_market",),
    )
    other_profile = ManagedProfile(
        profile_id="profile_bbbbbbbb",
        display_name="Other Profile",
        company_ids=("example_market",),
    )
    create_profile(database_path, active_profile)
    create_profile(database_path, other_profile)
    set_active_profile(database_path, active_profile.profile_id)

    paused = set_company_scanning_state(
        database_path,
        active_profile.profile_id,
        "example_market",
        scanning=False,
    )

    assert paused.scanning is False
    assert is_profile_employer_enabled(
        database_path, active_profile.profile_id, "example_market"
    ) is False
    assert is_profile_employer_enabled(
        database_path, other_profile.profile_id, "example_market"
    ) is True
    assert get_employer_source(database_path, "example_market").enabled is True

    resumed = set_company_scanning_state(
        database_path,
        active_profile.profile_id,
        "example_market",
        scanning=True,
    )

    assert resumed.scanning is True
    assert resumed.profile_name == "Active Profile"
    assert resumed.employer_name == "Example Market"
    assert is_profile_employer_enabled(
        database_path, active_profile.profile_id, "example_market"
    ) is True


def test_scanning_state_rejects_missing_active_profile(tmp_path: Path) -> None:
    database_path = tmp_path / "junior.sqlite3"
    add_employer(database_path, "example_market", "Example Market")

    with pytest.raises(NoActiveProfileError):
        set_company_scanning_state(
            database_path,
            "profile_aaaaaaaa",
            "example_market",
            scanning=False,
        )


def test_scanning_state_rejects_other_profile_and_unassigned_company(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    add_employer(database_path, "assigned_market", "Assigned Market")
    add_employer(database_path, "other_market", "Other Market")
    active_profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Active Profile",
        company_ids=("assigned_market",),
    )
    other_profile = ManagedProfile(
        profile_id="profile_bbbbbbbb",
        display_name="Other Profile",
        company_ids=("other_market",),
    )
    create_profile(database_path, active_profile)
    create_profile(database_path, other_profile)
    set_active_profile(database_path, active_profile.profile_id)

    with pytest.raises(EmployerNotAssignedError):
        set_company_scanning_state(
            database_path,
            other_profile.profile_id,
            "other_market",
            scanning=False,
        )

    with pytest.raises(EmployerNotAssignedError):
        set_company_scanning_state(
            database_path,
            active_profile.profile_id,
            "other_market",
            scanning=False,
        )

    assert is_profile_employer_enabled(
        database_path, other_profile.profile_id, "other_market"
    ) is True


def test_scanning_state_rejects_unknown_employer(tmp_path: Path) -> None:
    database_path = tmp_path / "junior.sqlite3"
    active_profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Active Profile",
    )
    create_profile(database_path, active_profile)
    set_active_profile(database_path, active_profile.profile_id)

    with pytest.raises(EmployerNotFoundError):
        set_company_scanning_state(
            database_path,
            active_profile.profile_id,
            "missing_market",
            scanning=False,
        )
