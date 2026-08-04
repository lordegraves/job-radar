"""Plan and perform backup-first migration of one legacy YAML profile.

The original profile and resume files are read-only migration sources. Every
write goes to Junior's managed user-data area, and a private recovery bundle
is completed before a managed profile record or resume directory is created.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import secrets
import shutil

from job_radar.candidate_profile import CandidateProfile, load_candidate_profile
from job_radar.config import ConfigError
from job_radar.database import connect_database
from job_radar.profile_models import (
    ManagedProfile,
    ProfilePreferences,
    build_managed_resume,
    get_managed_resume_directory,
)
from job_radar.profile_storage import (
    create_and_select_profile,
    list_profiles,
)
from job_radar.resume_loader import load_resume_text
from job_radar.storage import initialize_database


class ProfileMigrationError(RuntimeError):
    """Raised when migration safety checks prevent a legacy profile import."""


@dataclass(frozen=True)
class LegacyProfileMigrationPlan:
    """Describe an import without changing the database or source files."""

    profile_id: str
    display_name: str
    source_profile_path: Path
    source_resume_path: Path | None
    source_normalized_resume_path: Path | None
    managed_resume_directory: Path
    database_path: Path
    backup_root: Path


@dataclass(frozen=True)
class LegacyProfileMigrationResult:
    """Record the private backup and new managed profile after success."""

    profile: ManagedProfile
    backup_directory: Path
    managed_resume_directory: Path


def plan_legacy_profile_migration(
    *,
    database_path: str | Path,
    source_profile_path: str | Path,
    user_data_root: str | Path,
    profile_id: str | None = None,
) -> LegacyProfileMigrationPlan:
    """Validate source data and return the paths a migration would use."""

    root = Path(user_data_root).expanduser().resolve()
    source_path = Path(source_profile_path).expanduser().resolve()
    candidate = load_candidate_profile(source_path, base_directory=root)
    resolved_profile_id = profile_id or f"profile_{secrets.token_hex(8)}"
    managed_directory = (root / get_managed_resume_directory(resolved_profile_id)).resolve()
    resume_path, normalized_path = _candidate_resume_paths(candidate)

    if resume_path is not None:
        # Validate extraction during planning so a corrupt source never reaches
        # the backup or managed destination steps.
        load_resume_text(resume_path)

    return LegacyProfileMigrationPlan(
        profile_id=resolved_profile_id,
        display_name=candidate.name,
        source_profile_path=source_path,
        source_resume_path=resume_path,
        source_normalized_resume_path=normalized_path,
        managed_resume_directory=managed_directory,
        database_path=Path(database_path).expanduser().resolve(),
        backup_root=(root / "data" / "backups" / "profile-migrations").resolve(),
    )


def migrate_legacy_profile(
    plan: LegacyProfileMigrationPlan,
    *,
    user_data_root: str | Path,
) -> LegacyProfileMigrationResult:
    """Back up source state, then copy and select one managed profile."""

    root = Path(user_data_root).expanduser().resolve()
    expected_managed_directory = (
        root / get_managed_resume_directory(plan.profile_id)
    ).resolve()
    expected_backup_root = (
        root / "data" / "backups" / "profile-migrations"
    ).resolve()
    if plan.managed_resume_directory != expected_managed_directory:
        raise ProfileMigrationError("Migration destination is outside the user-data root.")
    if plan.backup_root != expected_backup_root:
        raise ProfileMigrationError("Migration backup is outside the user-data root.")

    database_path = initialize_database(plan.database_path)
    existing_profiles = list_profiles(database_path, include_archived=True)
    if any(profile.profile_id == plan.profile_id for profile in existing_profiles):
        raise ProfileMigrationError(f"Managed profile ID already exists: {plan.profile_id}")
    if any(
        profile.display_name.casefold() == plan.display_name.casefold()
        for profile in existing_profiles
    ):
        raise ProfileMigrationError(
            f"A managed profile already uses the name: {plan.display_name}"
        )
    if plan.managed_resume_directory.exists():
        raise ProfileMigrationError(
            f"Managed resume destination already exists: {plan.managed_resume_directory}"
        )

    candidate = load_candidate_profile(plan.source_profile_path, base_directory=root)
    _confirm_plan_still_matches_source(plan, candidate)
    backup_directory = _create_recovery_bundle(plan, database_path)
    profile = _build_managed_profile(plan, candidate)

    try:
        _copy_managed_resume(plan, profile)
        create_and_select_profile(database_path, profile)
    except BaseException:
        # Only newly created destination files are removed. The read-only source
        # and completed recovery bundle remain intact for investigation.
        if plan.managed_resume_directory.exists():
            shutil.rmtree(plan.managed_resume_directory)
        raise

    return LegacyProfileMigrationResult(
        profile=profile,
        backup_directory=backup_directory,
        managed_resume_directory=plan.managed_resume_directory,
    )


def _candidate_resume_paths(
    candidate: CandidateProfile,
) -> tuple[Path | None, Path | None]:
    if candidate.resume is None:
        return None, None
    source_path = Path(candidate.resume.source_path).resolve()
    normalized_path = (
        Path(candidate.resume.normalized_text_path).resolve()
        if candidate.resume.normalized_text_path is not None
        else None
    )
    return source_path, normalized_path


def _confirm_plan_still_matches_source(
    plan: LegacyProfileMigrationPlan,
    candidate: CandidateProfile,
) -> None:
    resume_path, normalized_path = _candidate_resume_paths(candidate)
    if candidate.name != plan.display_name:
        raise ProfileMigrationError("The source profile changed after planning.")
    if resume_path != plan.source_resume_path or normalized_path != plan.source_normalized_resume_path:
        raise ProfileMigrationError("The source resume paths changed after planning.")
    if resume_path is not None:
        load_resume_text(resume_path)


def _create_recovery_bundle(
    plan: LegacyProfileMigrationPlan,
    database_path: Path,
) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup_directory = plan.backup_root / f"{timestamp}-{plan.profile_id}"
    backup_directory.mkdir(parents=True, exist_ok=False)

    shutil.copy2(plan.source_profile_path, backup_directory / "legacy-profile.yaml")
    if plan.source_resume_path is not None:
        shutil.copy2(
            plan.source_resume_path,
            backup_directory / f"resume{plan.source_resume_path.suffix.lower()}",
        )
    if (
        plan.source_normalized_resume_path is not None
        and plan.source_normalized_resume_path.is_file()
    ):
        shutil.copy2(
            plan.source_normalized_resume_path,
            backup_directory / "resume.normalized.txt",
        )

    with connect_database(database_path) as source_connection:
        with connect_database(backup_directory / "job_radar.sqlite3") as backup_connection:
            source_connection.backup(backup_connection)

    manifest = {
        "profile_id": plan.profile_id,
        "display_name": plan.display_name,
        "source_profile_file": "legacy-profile.yaml",
        "source_resume_file": (
            f"resume{plan.source_resume_path.suffix.lower()}"
            if plan.source_resume_path is not None
            else None
        ),
        "database_file": "job_radar.sqlite3",
    }
    (backup_directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return backup_directory


def _build_managed_profile(
    plan: LegacyProfileMigrationPlan,
    candidate: CandidateProfile,
) -> ManagedProfile:
    managed_resume = None
    if plan.source_resume_path is not None:
        try:
            managed_resume = build_managed_resume(plan.source_resume_path.suffix)
        except ValueError as error:
            raise ConfigError(str(error)) from error

    return ManagedProfile(
        profile_id=plan.profile_id,
        display_name=candidate.name,
        preferences=ProfilePreferences(
            core_strengths=tuple(candidate.core_strengths),
            credible_adjacent=tuple(candidate.credible_adjacent),
            learning_or_gap=tuple(candidate.learning_or_gap),
            exclusions=tuple(candidate.avoid),
            compensation_floor_usd=candidate.compensation_floor_usd,
            compensation_target_usd=candidate.preferred_base_usd,
        ),
        resume=managed_resume,
    )


def _copy_managed_resume(
    plan: LegacyProfileMigrationPlan,
    profile: ManagedProfile,
) -> None:
    if plan.source_resume_path is None or profile.resume is None:
        return

    plan.managed_resume_directory.mkdir(parents=True, exist_ok=False)
    target_path = plan.managed_resume_directory / profile.resume.source_file_name
    normalized_path = (
        plan.managed_resume_directory / profile.resume.normalized_text_file_name
    )
    shutil.copy2(plan.source_resume_path, target_path)
    normalized_path.write_text(load_resume_text(target_path) + "\n", encoding="utf-8")
