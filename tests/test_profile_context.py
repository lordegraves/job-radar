"""Tests managed-profile selection and the safe legacy YAML fallback."""

from pathlib import Path

from job_radar.profile_context import load_active_candidate_context
from job_radar.profile_models import (
    ManagedProfile,
    ProfilePreferences,
    build_managed_resume,
)
from job_radar.profile_storage import create_profile, set_active_profile


def test_load_active_candidate_context_uses_selected_managed_profile(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    profile = ManagedProfile(
        profile_id="profile_1a2b3c4d",
        display_name="Managed Example",
        preferences=ProfilePreferences(
            core_strengths=("Platform operations",),
            credible_adjacent=("Reliability engineering",),
            learning_or_gap=("Product engineering",),
            exclusions=("Commission sales",),
            compensation_floor_usd=125000,
            compensation_target_usd=150000,
        ),
        resume=build_managed_resume(".md"),
    )
    resume_directory = tmp_path / "resumes" / profile.profile_id
    resume_directory.mkdir(parents=True)
    resume_path = resume_directory / "resume.md"
    normalized_path = resume_directory / "resume.normalized.txt"
    resume_path.write_text("# Managed Example\n\nPlatform operations", encoding="utf-8")
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)

    context = load_active_candidate_context(
        database_path,
        tmp_path / "unused-legacy-profile.yaml",
        base_directory=tmp_path,
    )

    assert context.managed_profile == profile
    assert context.candidate_profile is not None
    assert context.candidate_profile.name == "Managed Example"
    assert context.candidate_profile.compensation_floor_usd == 125000
    assert context.candidate_profile.preferred_base_usd == 150000
    assert context.candidate_profile.core_strengths == ["Platform operations"]
    assert context.candidate_profile.avoid == ["Commission sales"]
    assert context.resume_text == "# Managed Example Platform operations"
    assert normalized_path.read_text(encoding="utf-8") == (
        "# Managed Example Platform operations\n"
    )


def test_load_active_candidate_context_preserves_yaml_fallback(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    profile_path = tmp_path / "profiles" / "legacy" / "profile.yaml"
    resume_path = tmp_path / "profiles" / "legacy" / "resume.txt"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(
        """
candidate:
  name: Legacy Example
  resume:
    source_path: profiles/legacy/resume.txt
  core_strengths:
    - Linux
  credible_adjacent: []
  learning_or_gap: []
  avoid: []
""",
        encoding="utf-8",
    )
    resume_path.write_text("Legacy resume", encoding="utf-8")

    context = load_active_candidate_context(
        database_path,
        profile_path,
        base_directory=tmp_path,
    )

    assert context.managed_profile is None
    assert context.candidate_profile is not None
    assert context.candidate_profile.name == "Legacy Example"
    assert context.resume_text == "Legacy resume"
