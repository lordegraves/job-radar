"""Provide GUI-safe managed-profile operations over temporary or user data.

Routes use this service instead of writing SQLite rows or resume paths directly.
There is deliberately no delete operation: archival is reversible and protects
profile-owned data until a future backup-aware deletion workflow exists.
"""

import json
import os
import secrets
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from job_radar.config import ConfigError
from job_radar.profile_models import (
    LocationPreference,
    ManagedProfile,
    OccupationPreference,
    ProfilePreferences,
    build_managed_resume,
    get_managed_resume_directory,
)
from job_radar.profile_storage import (
    create_profile,
    get_active_profile,
    get_profile,
    list_profiles,
    set_active_profile,
    set_profile_archived,
    update_profile,
)
from job_radar.resume_loader import SUPPORTED_RESUME_EXTENSIONS, load_resume_text
from job_radar.runtime_paths import RuntimePaths


@dataclass(frozen=True)
class ProfileManagementView:
    profiles: list[ManagedProfile]
    active_profile_id: str | None


JOB_LEVELS = {"Entry-level", "Mid-level", "Senior", "Executive"}
EMPLOYMENT_TYPES = {
    "Full-time",
    "Part-time",
    "Contract",
    "Temporary",
    "Seasonal",
    "Internship or apprenticeship",
}
WORKPLACE_ARRANGEMENTS = {"Remote", "Hybrid", "On-site"}
SCHEDULE_PREFERENCES = {
    "Any schedule",
    "Day shift",
    "Evening shift",
    "Night shift",
    "Weekdays",
    "Weekends accepted",
    "Flexible schedule",
}


def build_profile_management_view(
    settings_path: str | None,
    *,
    base_directory: str | Path | None = None,
) -> ProfileManagementView:
    runtime_paths = _runtime_paths(settings_path, base_directory)
    active_profile = get_active_profile(runtime_paths.database_path)
    return ProfileManagementView(
        profiles=list_profiles(runtime_paths.database_path, include_archived=True),
        active_profile_id=(active_profile.profile_id if active_profile else None),
    )


def create_managed_profile(
    settings_path: str | None,
    display_name: str,
    *,
    base_directory: str | Path | None = None,
) -> ManagedProfile:
    normalized_name = display_name.strip()
    if not normalized_name:
        raise ConfigError("Enter a profile name.")

    runtime_paths = _runtime_paths(settings_path, base_directory)
    profile = ManagedProfile(
        profile_id=f"profile_{secrets.token_hex(8)}",
        display_name=normalized_name,
    )
    create_profile(runtime_paths.database_path, profile)
    set_active_profile(runtime_paths.database_path, profile.profile_id)
    return profile


def update_managed_profile_from_form(
    settings_path: str | None,
    profile_id: str,
    values: dict[str, str],
    *,
    base_directory: str | Path | None = None,
) -> ManagedProfile:
    runtime_paths = _runtime_paths(settings_path, base_directory)
    current = get_profile(runtime_paths.database_path, profile_id)
    if current is None:
        raise ConfigError("The selected profile no longer exists.")

    display_name = values.get("display_name", "").strip()
    if not display_name:
        raise ConfigError("Enter a profile name.")

    preferences = ProfilePreferences(
        target_roles=_lines(values.get("target_roles", "")),
        seniority_levels=_lines(values.get("seniority_levels", "")),
        core_strengths=_lines(values.get("core_strengths", "")),
        credible_adjacent=_lines(values.get("credible_adjacent", "")),
        learning_or_gap=_lines(values.get("learning_or_gap", "")),
        exclusions=_lines(values.get("exclusions", "")),
        preferred_locations=_lines(values.get("preferred_locations", "")),
        work_arrangements=_lines(values.get("work_arrangements", "")),
        employment_types=_lines(values.get("employment_types", "")),
        compensation_floor_usd=_optional_non_negative_int(
            values.get("compensation_floor_usd", ""), "Compensation floor"
        ),
        compensation_target_usd=_optional_non_negative_int(
            values.get("compensation_target_usd", ""), "Compensation target"
        ),
        travel_tolerance=values.get("travel_tolerance", "").strip() or None,
        schedule_preference=current.preferences.schedule_preference,
        occupation_selections=current.preferences.occupation_selections,
        location_selections=current.preferences.location_selections,
    )
    updated = replace(current, display_name=display_name, preferences=preferences)
    update_profile(runtime_paths.database_path, updated)
    return updated


def update_managed_search_preferences(
    settings_path: str | None,
    *,
    occupation_selections_json: str,
    location_selections_json: str,
    seniority_levels: list[str],
    employment_types: list[str],
    work_arrangements: list[str],
    schedule_preference: str,
    compensation_floor_usd: str,
    travel_percentage: str,
    base_directory: str | Path | None = None,
) -> ManagedProfile:
    """Validate and save only the fields owned by Search Preferences."""

    runtime_paths = _runtime_paths(settings_path, base_directory)
    current = get_active_profile(runtime_paths.database_path)
    if current is None:
        raise ConfigError(
            "Create or select a managed profile before saving search preferences."
        )

    occupations = _occupation_preferences(occupation_selections_json)
    locations = _location_preferences(location_selections_json)
    levels = _allowed_selections(seniority_levels, JOB_LEVELS, "job level")
    employment = _allowed_selections(
        employment_types, EMPLOYMENT_TYPES, "employment type"
    )
    arrangements = _allowed_selections(
        work_arrangements, WORKPLACE_ARRANGEMENTS, "workplace arrangement"
    )
    schedule = schedule_preference.strip()
    if schedule not in SCHEDULE_PREFERENCES:
        raise ConfigError("Choose a valid schedule preference.")
    travel = _percentage(travel_percentage, "Maximum travel")

    preferences = replace(
        current.preferences,
        target_roles=tuple(item.label for item in occupations),
        seniority_levels=levels,
        preferred_locations=tuple(item.label for item in locations),
        work_arrangements=arrangements,
        employment_types=employment,
        compensation_floor_usd=_optional_non_negative_int(
            compensation_floor_usd, "Minimum annual compensation"
        ),
        travel_tolerance=str(travel),
        schedule_preference=schedule,
        occupation_selections=occupations,
        location_selections=locations,
    )
    updated = replace(current, preferences=preferences)
    if not update_profile(runtime_paths.database_path, updated):
        raise ConfigError("The selected profile no longer exists.")
    return updated


def select_managed_profile(
    settings_path: str | None,
    profile_id: str | None,
    *,
    base_directory: str | Path | None = None,
) -> None:
    runtime_paths = _runtime_paths(settings_path, base_directory)
    set_active_profile(runtime_paths.database_path, profile_id)


def archive_managed_profile(
    settings_path: str | None,
    profile_id: str,
    *,
    archived: bool,
    base_directory: str | Path | None = None,
) -> None:
    runtime_paths = _runtime_paths(settings_path, base_directory)
    if not set_profile_archived(
        runtime_paths.database_path, profile_id, archived=archived
    ):
        raise ConfigError("The selected profile no longer exists.")


def save_managed_profile_resume(
    settings_path: str | None,
    uploaded_filename: str,
    uploaded_content: bytes,
    *,
    base_directory: str | Path | None = None,
) -> None:
    extension = Path(uploaded_filename).suffix.lower()
    if extension not in SUPPORTED_RESUME_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_RESUME_EXTENSIONS))
        raise ConfigError(
            f"Unsupported resume format: {extension or 'none'}. "
            f"Supported formats: {supported}"
        )
    if not uploaded_content:
        raise ConfigError("Uploaded resume file is empty.")

    runtime_paths = _runtime_paths(settings_path, base_directory)
    profile = get_active_profile(runtime_paths.database_path)
    if profile is None:
        raise ConfigError("Create or select a managed profile before uploading a resume.")

    resume = build_managed_resume(extension)
    resume_directory = (
        runtime_paths.base_directory
        / get_managed_resume_directory(profile.profile_id)
    )
    resume_directory.mkdir(parents=True, exist_ok=True)
    target_path = resume_directory / resume.source_file_name
    normalized_path = resume_directory / resume.normalized_text_file_name
    temporary_source = resume_directory / f".resume-upload{extension}"
    temporary_normalized = resume_directory / ".resume-normalized-upload.txt"
    source_backup = resume_directory / f".resume-source-backup{extension}"
    normalized_backup = resume_directory / ".resume-normalized-backup.txt"
    source_existed = target_path.exists()
    normalized_existed = normalized_path.exists()

    try:
        temporary_source.write_bytes(uploaded_content)
        resume_text = load_resume_text(temporary_source)
        temporary_normalized.write_text(resume_text + "\n", encoding="utf-8")

        if source_existed:
            shutil.copy2(target_path, source_backup)
        if normalized_existed:
            shutil.copy2(normalized_path, normalized_backup)

        os.replace(temporary_source, target_path)
        os.replace(temporary_normalized, normalized_path)
        if not update_profile(
            runtime_paths.database_path,
            replace(profile, resume=resume),
        ):
            raise ConfigError("The selected profile no longer exists.")
    except BaseException:
        # Put the previous managed files back if the database update fails after
        # validated upload files were moved into place.
        if source_existed and source_backup.exists():
            os.replace(source_backup, target_path)
        elif not source_existed:
            target_path.unlink(missing_ok=True)

        if normalized_existed and normalized_backup.exists():
            os.replace(normalized_backup, normalized_path)
        elif not normalized_existed:
            normalized_path.unlink(missing_ok=True)
        raise
    finally:
        temporary_source.unlink(missing_ok=True)
        temporary_normalized.unlink(missing_ok=True)
        source_backup.unlink(missing_ok=True)
        normalized_backup.unlink(missing_ok=True)

    if profile.resume is not None:
        previous_path = resume_directory / profile.resume.source_file_name
        if previous_path != target_path:
            previous_path.unlink(missing_ok=True)


def _runtime_paths(
    settings_path: str | None,
    base_directory: str | Path | None,
) -> RuntimePaths:
    if settings_path is not None and base_directory is not None:
        return RuntimePaths.from_settings(
            settings_path=settings_path,
            base_directory=base_directory,
        )
    return RuntimePaths.from_settings_argument(settings_path)


def _lines(value: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in value.splitlines() if line.strip())


def _optional_non_negative_int(value: str, label: str) -> int | None:
    normalized = value.strip().replace(",", "").replace("$", "")
    if not normalized:
        return None
    try:
        result = int(normalized)
    except ValueError as error:
        raise ConfigError(f"{label} must be a whole-dollar amount.") from error
    if result < 0:
        raise ConfigError(f"{label} cannot be negative.")
    return result


def _allowed_selections(
    values: list[str], allowed: set[str], label: str
) -> tuple[str, ...]:
    selections = tuple(
        dict.fromkeys(value.strip() for value in values if value.strip())
    )
    if any(value not in allowed for value in selections):
        raise ConfigError(f"Choose a valid {label}.")
    return selections


def _percentage(value: str, label: str) -> int:
    try:
        percentage = int(value)
    except ValueError as error:
        raise ConfigError(f"{label} must be between 0% and 100%.") from error
    if not 0 <= percentage <= 100:
        raise ConfigError(f"{label} must be between 0% and 100%.")
    return percentage


def _occupation_preferences(raw_value: str) -> tuple[OccupationPreference, ...]:
    values = _json_list(raw_value, "occupations")
    if len(values) > 50:
        raise ConfigError("Choose no more than 50 occupations.")
    try:
        selections = tuple(
            OccupationPreference(
                value=str(item["value"]).strip(),
                label=str(item["label"]).strip(),
            )
            for item in values
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ConfigError("The selected occupations are invalid.") from error
    return _unique_by_value(selections)


def _location_preferences(raw_value: str) -> tuple[LocationPreference, ...]:
    values = _json_list(raw_value, "locations")
    if len(values) > 20:
        raise ConfigError("Choose no more than 20 locations.")
    try:
        selections = tuple(
            LocationPreference(
                value=str(item["value"]).strip(),
                label=str(item["label"]).strip(),
                latitude=(
                    float(item["latitude"])
                    if item.get("latitude") is not None
                    else None
                ),
                longitude=(
                    float(item["longitude"])
                    if item.get("longitude") is not None
                    else None
                ),
                radius_miles=int(item["radius"]),
            )
            for item in values
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ConfigError("The selected locations are invalid.") from error
    return _unique_by_value(selections)


def _json_list(raw_value: str, label: str) -> list[object]:
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError as error:
        raise ConfigError(f"The selected {label} are invalid.") from error
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ConfigError(f"The selected {label} are invalid.")
    return value


def _unique_by_value(values: tuple) -> tuple:
    unique = {}
    for value in values:
        unique[value.value.casefold()] = value
    return tuple(unique.values())
