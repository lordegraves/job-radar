"""Verify catalog recommendations and feedback remain profile-specific."""

from pathlib import Path

from job_radar.company_recommendation_models import (
    DISMISSED,
    MAYBE_LATER,
    NOT_RELEVANT,
)
from job_radar.company_recommendation_service import (
    build_company_recommendations,
    record_recommendation_feedback,
)
from job_radar.database import connect_database
from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import upsert_employer_source
from job_radar.profile_models import ManagedProfile, ProfilePreferences
from job_radar.profile_storage import create_profile, set_active_profile


def _profile(profile_id: str, name: str, role: str) -> ManagedProfile:
    return ManagedProfile(
        profile_id=profile_id,
        display_name=name,
        preferences=ProfilePreferences(target_roles=(role,)),
    )


def _employer(
    employer_id: str,
    name: str,
    *,
    tags: list[str] | None = None,
    enabled: bool = True,
) -> EmployerSource:
    return EmployerSource(
        employer_id=employer_id,
        name=name,
        source_type="html",
        enabled=enabled,
        source_config={
            "source_url": f"https://{employer_id}.invalid/jobs",
            "tags": tags or [],
        },
    )


def test_recommendations_are_profile_specific_ranked_and_scan_ready(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    cook = _profile("profile_aaaaaaaa", "Cook Profile", "cook")
    engineer = _profile("profile_bbbbbbbb", "Engineer Profile", "platform engineer")
    create_profile(database_path, cook)
    create_profile(database_path, engineer)
    upsert_employer_source(
        database_path,
        _employer("example_kitchen", "Example Kitchen", tags=["cook", "food"]),
    )
    upsert_employer_source(
        database_path,
        _employer("example_compute", "Example Compute", tags=["platform"]),
    )
    upsert_employer_source(
        database_path,
        _employer("offline_example", "Offline Example", enabled=False),
    )

    set_active_profile(database_path, cook.profile_id)
    cook_results = build_company_recommendations(database_path)
    set_active_profile(database_path, engineer.profile_id)
    engineer_results = build_company_recommendations(database_path)

    assert [item.employer_id for item in cook_results] == [
        "example_kitchen",
        "example_compute",
    ]
    assert [item.employer_id for item in engineer_results] == [
        "example_compute",
        "example_kitchen",
    ]
    assert "target work: cook" in cook_results[0].evidence[0]
    assert all(item.can_scan for item in cook_results)
    assert "offline_example" not in {
        item.employer_id for item in cook_results + engineer_results
    }


def test_feedback_persists_without_leaking_between_profiles(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    first = _profile("profile_aaaaaaaa", "First Profile", "cook")
    second = _profile("profile_bbbbbbbb", "Second Profile", "cook")
    create_profile(database_path, first)
    create_profile(database_path, second)
    upsert_employer_source(
        database_path,
        _employer("example_kitchen", "Example Kitchen", tags=["cook"]),
    )

    set_active_profile(database_path, first.profile_id)
    build_company_recommendations(database_path)
    record_recommendation_feedback(
        database_path,
        profile_id=first.profile_id,
        employer_id="example_kitchen",
        state=NOT_RELEVANT,
    )
    assert build_company_recommendations(database_path) == ()

    set_active_profile(database_path, second.profile_id)
    assert len(build_company_recommendations(database_path)) == 1


def test_maybe_later_and_dismiss_use_bounded_cooldowns(tmp_path: Path) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = _profile("profile_aaaaaaaa", "Cook Profile", "cook")
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    upsert_employer_source(
        database_path,
        _employer("example_kitchen", "Example Kitchen", tags=["cook"]),
    )

    for state in (MAYBE_LATER, DISMISSED):
        build_company_recommendations(database_path)
        record_recommendation_feedback(
            database_path,
            profile_id=profile.profile_id,
            employer_id="example_kitchen",
            state=state,
        )
        assert build_company_recommendations(database_path) == ()
        with connect_database(database_path) as connection:
            connection.execute(
                """
                UPDATE company_recommendations
                SET hidden_until = '2000-01-01 00:00:00'
                WHERE profile_id = ? AND employer_id = ?
                """,
                (profile.profile_id, "example_kitchen"),
            )
        assert len(build_company_recommendations(database_path)) == 1
