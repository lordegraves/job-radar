"""Verify Pause and Resume change only the active profile's assignment."""

from pathlib import Path

import pytest

from job_radar.company_assignment_service import (
    add_existing_company_to_profile,
    remove_company_from_profile,
    set_company_scanning_state,
)
from job_radar.database import connect_database
from job_radar.domain_errors import (
    EmployerAlreadyAssignedError,
    EmployerConfigurationError,
    EmployerNotAssignedError,
    EmployerNotFoundError,
    EmployerUnavailableError,
    NoActiveProfileError,
)
from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import (
    get_employer_source,
    is_profile_employer_enabled,
    upsert_employer_source,
)
from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import (
    create_profile,
    get_profile,
    set_active_profile,
)
from job_radar.models import JobPosting
from job_radar.storage import upsert_job_posting


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

    result = set_company_scanning_state(
        database_path,
        active_profile.profile_id,
        "other_market",
        scanning=False,
    )
    assert result.scanning is False

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


def test_remove_company_preserves_catalog_other_profile_and_history(
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
    posting = JobPosting(
        company_key="example_market",
        company_name="Example Market",
        source_type="html",
        source_url="https://example.invalid/jobs/1",
        source_job_id="job-1",
        title="Test Role",
        location="Test City",
        description="Fictional role used to verify historical preservation.",
        canonical_key="example-market-test-role",
        content_hash="fictional-content-hash",
    )
    upsert_job_posting(database_path, posting)

    with connect_database(database_path) as connection:
        connection.execute(
            """
            INSERT INTO application_tracker (
                profile_id, job_radar_id, company_name, role_title
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                active_profile.profile_id,
                posting.job_radar_id,
                "Example Market",
                "Test Role",
            ),
        )
        connection.execute(
            """
            INSERT INTO job_history (
                profile_id, history_type, company, role, import_key
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                active_profile.profile_id,
                "application",
                "Example Market",
                "Test Role",
                "test-history-1",
            ),
        )

    result = remove_company_from_profile(
        database_path,
        active_profile.profile_id,
        "example_market",
    )

    assert result.employer_name == "Example Market"
    assert get_profile(database_path, active_profile.profile_id).company_ids == ()
    assert get_profile(database_path, other_profile.profile_id).company_ids == (
        "example_market",
    )
    assert get_employer_source(database_path, "example_market") is not None

    with connect_database(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM job_postings"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM application_tracker"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM job_history"
        ).fetchone()[0] == 1


def test_remove_company_rejects_other_profile_and_unassigned_company(
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
        remove_company_from_profile(
            database_path,
            other_profile.profile_id,
            "other_market",
        )

    with pytest.raises(EmployerNotAssignedError):
        remove_company_from_profile(
            database_path,
            active_profile.profile_id,
            "other_market",
        )

    assert get_profile(database_path, other_profile.profile_id).company_ids == (
        "other_market",
    )


def test_add_existing_company_assigns_scanning_to_only_active_profile(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    add_employer(database_path, "example_market", "Example Market")
    active_profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Active Profile",
    )
    other_profile = ManagedProfile(
        profile_id="profile_bbbbbbbb",
        display_name="Other Profile",
    )
    create_profile(database_path, active_profile)
    create_profile(database_path, other_profile)
    set_active_profile(database_path, active_profile.profile_id)

    result = add_existing_company_to_profile(
        database_path,
        active_profile.profile_id,
        "example_market",
    )

    assert result.scanning is True
    assert result.profile_name == "Active Profile"
    assert get_profile(database_path, active_profile.profile_id).company_ids == (
        "example_market",
    )
    assert get_profile(database_path, other_profile.profile_id).company_ids == ()
    assert is_profile_employer_enabled(
        database_path,
        active_profile.profile_id,
        "example_market",
    ) is True


def test_add_existing_company_rejects_duplicate_unavailable_and_incomplete(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    add_employer(database_path, "example_market", "Example Market")
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="disabled_market",
            name="Disabled Market",
            source_type="html",
            enabled=False,
            source_config={"source_url": "https://disabled.invalid/jobs"},
        ),
    )
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="incomplete_market",
            name="Incomplete Market",
            source_type="html",
            source_config={},
        ),
    )
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Active Profile",
        company_ids=("example_market",),
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)

    with pytest.raises(EmployerAlreadyAssignedError):
        add_existing_company_to_profile(
            database_path,
            profile.profile_id,
            "example_market",
        )

    with pytest.raises(EmployerUnavailableError):
        add_existing_company_to_profile(
            database_path,
            profile.profile_id,
            "disabled_market",
        )

    with pytest.raises(EmployerConfigurationError):
        add_existing_company_to_profile(
            database_path,
            profile.profile_id,
            "incomplete_market",
        )

    with pytest.raises(EmployerNotFoundError):
        add_existing_company_to_profile(
            database_path,
            profile.profile_id,
            "missing_market",
        )
