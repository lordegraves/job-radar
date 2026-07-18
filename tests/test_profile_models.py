"""Tests managed profile identity and app-owned resume-location boundaries."""

from pathlib import Path

import pytest

from job_radar.profile_models import (
    ManagedProfile,
    ManagedResume,
    ProfilePreferences,
    build_managed_resume,
    get_managed_resume_directory,
)


def test_managed_profile_preserves_generic_preferences() -> None:
    preferences = ProfilePreferences(
        target_roles=("Technical Writer",),
        seniority_levels=("Senior",),
        core_strengths=("Documentation systems",),
        preferred_locations=("Remote",),
        work_arrangements=("remote",),
        compensation_floor_usd=120000,
    )

    profile = ManagedProfile(
        profile_id="profile_1a2b3c4d",
        display_name="Example Candidate",
        preferences=preferences,
        company_ids=("example_company",),
    )

    assert profile.display_name == "Example Candidate"
    assert profile.preferences == preferences
    assert profile.company_ids == ("example_company",)
    assert profile.archived is False


def test_managed_resume_uses_app_owned_names() -> None:
    resume = build_managed_resume(".PDF")

    assert resume.source_file_name == "resume.pdf"
    assert resume.normalized_text_file_name == "resume.normalized.txt"


def test_managed_resume_directory_is_inside_common_resume_root() -> None:
    assert get_managed_resume_directory("profile_1a2b3c4d") == (
        Path("resumes") / "profile_1a2b3c4d"
    )


@pytest.mark.parametrize(
    "source_file_name",
    [
        "C:/Users/Example/Documents/resume.pdf",
        "../resume.pdf",
        "my-current-resume.pdf",
    ],
)
def test_managed_resume_rejects_external_paths_and_user_owned_names(
    source_file_name: str,
) -> None:
    with pytest.raises(ValueError):
        ManagedResume(source_file_name=source_file_name)


def test_managed_profile_rejects_invalid_profile_id() -> None:
    with pytest.raises(ValueError, match="profile_id"):
        ManagedProfile(
            profile_id="Clayton Graves",
            display_name="Example Candidate",
        )


def test_managed_profile_rejects_external_scoring_path() -> None:
    with pytest.raises(ValueError, match="scoring config"):
        ManagedProfile(
            profile_id="profile_1a2b3c4d",
            display_name="Example Candidate",
            scoring_config_file_name="C:/external/scoring.yaml",
        )
