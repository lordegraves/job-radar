"""Resolve the profile and resume used by scans without breaking YAML users.

A selected managed profile takes priority. When no managed profile is selected,
Job Radar preserves the existing YAML profile workflow exactly as before.
"""

from dataclasses import dataclass
from pathlib import Path

from job_radar.candidate_profile import (
    CandidateProfile,
    CandidateResumeConfig,
    load_candidate_profile,
)
from job_radar.profile_models import (
    ManagedProfile,
    ProfilePreferences,
    get_managed_resume_directory,
)
from job_radar.profile_storage import get_active_profile
from job_radar.resume_loader import load_resume_text, write_normalized_resume_text


@dataclass(frozen=True)
class ActiveCandidateContext:
    """Provide both legacy scoring inputs and structured managed preferences."""

    candidate_profile: CandidateProfile | None
    resume_text: str | None
    managed_profile: ManagedProfile | None = None
    job_preferences: ProfilePreferences | None = None


def load_active_candidate_context(
    database_path: str | Path,
    candidate_profile_path: Path | None,
    *,
    base_directory: Path,
) -> ActiveCandidateContext:
    """Use managed data when selected and otherwise retain the YAML path."""

    managed_profile = get_active_profile(database_path)

    if managed_profile is not None:
        candidate_profile = managed_profile_to_candidate_profile(
            managed_profile,
            base_directory=base_directory,
        )
        return ActiveCandidateContext(
            candidate_profile=candidate_profile,
            resume_text=_load_and_normalize_resume(candidate_profile),
            managed_profile=managed_profile,
            job_preferences=managed_profile.preferences,
        )

    if candidate_profile_path is None:
        return ActiveCandidateContext(None, None)

    candidate_profile = load_candidate_profile(
        candidate_profile_path,
        base_directory=base_directory,
    )
    return ActiveCandidateContext(
        candidate_profile=candidate_profile,
        resume_text=_load_and_normalize_resume(candidate_profile),
    )


def managed_profile_to_candidate_profile(
    profile: ManagedProfile,
    *,
    base_directory: Path,
) -> CandidateProfile:
    resume = None

    if profile.resume is not None:
        resume_directory = (
            base_directory / get_managed_resume_directory(profile.profile_id)
        ).resolve()
        resume = CandidateResumeConfig(
            source_path=str(resume_directory / profile.resume.source_file_name),
            normalized_text_path=str(
                resume_directory / profile.resume.normalized_text_file_name
            ),
        )

    return CandidateProfile(
        name=profile.display_name,
        compensation_floor_usd=profile.preferences.compensation_floor_usd,
        preferred_base_usd=profile.preferences.compensation_target_usd,
        resume=resume,
        core_strengths=list(profile.preferences.core_strengths),
        credible_adjacent=list(profile.preferences.credible_adjacent),
        learning_or_gap=list(profile.preferences.learning_or_gap),
        avoid=list(profile.preferences.exclusions),
    )


def _load_and_normalize_resume(
    candidate_profile: CandidateProfile,
) -> str | None:
    if candidate_profile.resume is None:
        return None

    resume_text = load_resume_text(candidate_profile.resume.source_path)

    if candidate_profile.resume.normalized_text_path:
        write_normalized_resume_text(
            source_path=candidate_profile.resume.source_path,
            normalized_text_path=candidate_profile.resume.normalized_text_path,
        )

    return resume_text
