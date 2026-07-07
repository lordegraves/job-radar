from dataclasses import dataclass
from pathlib import Path

from job_radar.candidate_profile import load_candidate_profile
from job_radar.config import ConfigError, load_settings
from job_radar.resume_loader import load_resume_text


RESUME_PREVIEW_CHARACTER_LIMIT = 1200


@dataclass(frozen=True)
class CandidateProfileView:
    settings_path: str
    candidate_profile_path: str | None
    candidate_profile_exists: bool
    load_error: str | None
    candidate_name: str | None
    compensation_floor_usd: int | None
    preferred_base_usd: int | None
    resume_source_path: str | None
    resume_source_exists: bool
    normalized_text_path: str | None
    normalized_text_exists: bool
    resume_character_count: int | None
    resume_preview: str | None
    core_strengths: list[str]
    credible_adjacent: list[str]
    learning_or_gap: list[str]
    avoid: list[str]


def build_candidate_profile_view(settings_path: str) -> CandidateProfileView:
    settings = load_settings(settings_path)
    candidate_profile_path = settings.get("candidate_profile_path")

    if not candidate_profile_path:
        return CandidateProfileView(
            settings_path=settings_path,
            candidate_profile_path=None,
            candidate_profile_exists=False,
            load_error="No candidate_profile_path is configured in settings.",
            candidate_name=None,
            compensation_floor_usd=None,
            preferred_base_usd=None,
            resume_source_path=None,
            resume_source_exists=False,
            normalized_text_path=None,
            normalized_text_exists=False,
            resume_character_count=None,
            resume_preview=None,
            core_strengths=[],
            credible_adjacent=[],
            learning_or_gap=[],
            avoid=[],
        )

    profile_path = Path(candidate_profile_path)

    try:
        candidate_profile = load_candidate_profile(profile_path)
    except ConfigError as error:
        return CandidateProfileView(
            settings_path=settings_path,
            candidate_profile_path=candidate_profile_path,
            candidate_profile_exists=profile_path.exists(),
            load_error=str(error),
            candidate_name=None,
            compensation_floor_usd=None,
            preferred_base_usd=None,
            resume_source_path=None,
            resume_source_exists=False,
            normalized_text_path=None,
            normalized_text_exists=False,
            resume_character_count=None,
            resume_preview=None,
            core_strengths=[],
            credible_adjacent=[],
            learning_or_gap=[],
            avoid=[],
        )

    resume_source_path = (
        candidate_profile.resume.source_path
        if candidate_profile.resume is not None
        else None
    )
    normalized_text_path = (
        candidate_profile.resume.normalized_text_path
        if candidate_profile.resume is not None
        else None
    )
    resume_text = None
    resume_error = None

    if resume_source_path:
        try:
            resume_text = load_resume_text(resume_source_path)
        except ConfigError as error:
            resume_error = str(error)

    return CandidateProfileView(
        settings_path=settings_path,
        candidate_profile_path=candidate_profile_path,
        candidate_profile_exists=profile_path.exists(),
        load_error=resume_error,
        candidate_name=candidate_profile.name,
        compensation_floor_usd=candidate_profile.compensation_floor_usd,
        preferred_base_usd=candidate_profile.preferred_base_usd,
        resume_source_path=resume_source_path,
        resume_source_exists=Path(resume_source_path).exists()
        if resume_source_path
        else False,
        normalized_text_path=normalized_text_path,
        normalized_text_exists=Path(normalized_text_path).exists()
        if normalized_text_path
        else False,
        resume_character_count=len(resume_text) if resume_text is not None else None,
        resume_preview=_build_resume_preview(resume_text),
        core_strengths=candidate_profile.core_strengths,
        credible_adjacent=candidate_profile.credible_adjacent,
        learning_or_gap=candidate_profile.learning_or_gap,
        avoid=candidate_profile.avoid,
    )


def _build_resume_preview(resume_text: str | None) -> str | None:
    if resume_text is None:
        return None

    if len(resume_text) <= RESUME_PREVIEW_CHARACTER_LIMIT:
        return resume_text

    return resume_text[:RESUME_PREVIEW_CHARACTER_LIMIT].rstrip() + "..."