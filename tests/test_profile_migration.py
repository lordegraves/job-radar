"""Tests backup-first legacy profile migration with disposable invented data."""

from dataclasses import replace
from pathlib import Path

import pytest

from job_radar.candidate_profile import load_candidate_profile
from job_radar.profile_context import load_active_candidate_context
from job_radar.profile_migration import (
    ProfileMigrationError,
    migrate_legacy_profile,
    plan_legacy_profile_migration,
)
from job_radar.profile_storage import get_active_profile


def write_legacy_profile(root: Path) -> tuple[Path, Path, Path]:
    profile_path = root / "profiles" / "legacy" / "profile.yaml"
    resume_path = root / "profiles" / "legacy" / "example-resume.md"
    normalized_path = root / "profiles" / "legacy" / "example.normalized.txt"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(
        """
candidate:
  name: Invented Candidate
  compensation_floor_usd: 150000
  preferred_base_usd: 180000
  resume:
    source_path: profiles/legacy/example-resume.md
    normalized_text_path: profiles/legacy/example.normalized.txt
  core_strengths:
    - Linux infrastructure
    - HPC operations
  credible_adjacent:
    - Site reliability engineering
  learning_or_gap:
    - Product engineering
  avoid:
    - Commission sales
""",
        encoding="utf-8",
    )
    resume_path.write_text(
        "# Invented Candidate\n\nLinux infrastructure and HPC operations",
        encoding="utf-8",
    )
    normalized_path.write_text("previous normalized text\n", encoding="utf-8")
    return profile_path, resume_path, normalized_path


def test_plan_is_read_only_and_resolves_managed_destination(tmp_path: Path) -> None:
    profile_path, resume_path, normalized_path = write_legacy_profile(tmp_path)
    database_path = tmp_path / "data" / "job_radar.sqlite3"

    plan = plan_legacy_profile_migration(
        database_path=database_path,
        source_profile_path=profile_path,
        user_data_root=tmp_path,
        profile_id="profile_12345678",
    )

    assert plan.display_name == "Invented Candidate"
    assert plan.source_resume_path == resume_path.resolve()
    assert plan.source_normalized_resume_path == normalized_path.resolve()
    assert plan.managed_resume_directory == (
        tmp_path / "resumes" / "profile_12345678"
    ).resolve()
    assert not database_path.exists()
    assert not plan.managed_resume_directory.exists()
    assert not plan.backup_root.exists()


def test_migration_backs_up_sources_and_preserves_scan_behavior(
    tmp_path: Path,
) -> None:
    profile_path, resume_path, normalized_path = write_legacy_profile(tmp_path)
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    original_profile = profile_path.read_bytes()
    original_resume = resume_path.read_bytes()
    original_normalized = normalized_path.read_bytes()
    legacy_candidate = load_candidate_profile(profile_path, base_directory=tmp_path)
    plan = plan_legacy_profile_migration(
        database_path=database_path,
        source_profile_path=profile_path,
        user_data_root=tmp_path,
        profile_id="profile_12345678",
    )

    result = migrate_legacy_profile(plan, user_data_root=tmp_path)

    assert profile_path.read_bytes() == original_profile
    assert resume_path.read_bytes() == original_resume
    assert normalized_path.read_bytes() == original_normalized
    assert (result.backup_directory / "legacy-profile.yaml").read_bytes() == (
        original_profile
    )
    assert (result.backup_directory / "resume.md").read_bytes() == original_resume
    assert (result.backup_directory / "resume.normalized.txt").read_bytes() == (
        original_normalized
    )
    assert (result.backup_directory / "job_radar.sqlite3").is_file()
    assert (result.backup_directory / "manifest.json").is_file()
    assert (result.managed_resume_directory / "resume.md").is_file()
    assert (result.managed_resume_directory / "resume.normalized.txt").is_file()

    active_profile = get_active_profile(database_path)
    assert active_profile == result.profile
    context = load_active_candidate_context(
        database_path,
        profile_path,
        base_directory=tmp_path,
    )
    assert context.candidate_profile is not None
    assert context.candidate_profile.name == legacy_candidate.name
    assert (
        context.candidate_profile.compensation_floor_usd
        == legacy_candidate.compensation_floor_usd
    )
    assert context.candidate_profile.preferred_base_usd == (
        legacy_candidate.preferred_base_usd
    )
    assert context.candidate_profile.core_strengths == legacy_candidate.core_strengths
    assert context.candidate_profile.credible_adjacent == (
        legacy_candidate.credible_adjacent
    )
    assert context.candidate_profile.learning_or_gap == legacy_candidate.learning_or_gap
    assert context.candidate_profile.avoid == legacy_candidate.avoid
    assert context.resume_text == (
        "# Invented Candidate\nLinux infrastructure and HPC operations"
    )


def test_migration_refuses_duplicate_profile_name_without_new_backup(
    tmp_path: Path,
) -> None:
    profile_path, _resume_path, _normalized_path = write_legacy_profile(tmp_path)
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    first_plan = plan_legacy_profile_migration(
        database_path=database_path,
        source_profile_path=profile_path,
        user_data_root=tmp_path,
        profile_id="profile_11111111",
    )
    first_result = migrate_legacy_profile(first_plan, user_data_root=tmp_path)
    second_plan = plan_legacy_profile_migration(
        database_path=database_path,
        source_profile_path=profile_path,
        user_data_root=tmp_path,
        profile_id="profile_22222222",
    )

    with pytest.raises(ProfileMigrationError, match="already uses the name"):
        migrate_legacy_profile(second_plan, user_data_root=tmp_path)

    assert list(second_plan.backup_root.iterdir()) == [first_result.backup_directory]
    assert not second_plan.managed_resume_directory.exists()


def test_migration_rolls_back_new_destination_when_database_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_path, _resume_path, _normalized_path = write_legacy_profile(tmp_path)
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    plan = plan_legacy_profile_migration(
        database_path=database_path,
        source_profile_path=profile_path,
        user_data_root=tmp_path,
        profile_id="profile_12345678",
    )
    monkeypatch.setattr(
        "job_radar.profile_migration.create_and_select_profile",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("synthetic database failure")
        ),
    )

    with pytest.raises(RuntimeError, match="synthetic database failure"):
        migrate_legacy_profile(plan, user_data_root=tmp_path)

    assert not plan.managed_resume_directory.exists()
    backup_directories = list(plan.backup_root.iterdir())
    assert len(backup_directories) == 1
    assert (backup_directories[0] / "legacy-profile.yaml").is_file()
    assert (backup_directories[0] / "job_radar.sqlite3").is_file()


def test_migration_refuses_backup_location_outside_user_data(
    tmp_path: Path,
) -> None:
    profile_path, _resume_path, _normalized_path = write_legacy_profile(tmp_path)
    plan = plan_legacy_profile_migration(
        database_path=tmp_path / "data" / "job_radar.sqlite3",
        source_profile_path=profile_path,
        user_data_root=tmp_path,
        profile_id="profile_12345678",
    )
    unsafe_plan = replace(plan, backup_root=tmp_path.parent / "unexpected-backup")

    with pytest.raises(ProfileMigrationError, match="backup is outside"):
        migrate_legacy_profile(unsafe_plan, user_data_root=tmp_path)

    assert not unsafe_plan.backup_root.exists()
    assert not plan.database_path.exists()
