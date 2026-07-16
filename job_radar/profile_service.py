from dataclasses import dataclass
from pathlib import Path
from textwrap import fill

import yaml

from job_radar.candidate_profile import load_candidate_profile
from job_radar.config import ConfigError
from job_radar.resume_loader import (
    SUPPORTED_RESUME_EXTENSIONS,
    load_resume_display_text,
    load_resume_text,
    write_normalized_resume_text,
)
from job_radar.runtime_paths import RuntimePaths


RESUME_PREVIEW_CHARACTER_LIMIT = 5000
RESUME_PREVIEW_LINE_WIDTH = 110


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
    resume_source_file_name: str | None
    resume_source_exists: bool
    normalized_text_path: str | None
    normalized_text_exists: bool
    resume_character_count: int | None
    resume_preview: str | None
    core_strengths: list[str]
    credible_adjacent: list[str]
    learning_or_gap: list[str]
    avoid: list[str]


@dataclass(frozen=True)
class ResumeUploadResult:
    resume_source_path: str
    normalized_text_path: str


def build_candidate_profile_view(
    settings_path: str | None,
    *,
    base_directory: str | Path | None = None,
) -> CandidateProfileView:
    runtime_paths = (
        RuntimePaths.from_settings(
            settings_path=settings_path,
            base_directory=base_directory,
        )
        if settings_path is not None and base_directory is not None
        else RuntimePaths.from_settings_argument(settings_path)
    )
    resolved_settings_path = str(runtime_paths.settings_path)
    profile_path = runtime_paths.candidate_profile_path

    if profile_path is None:
        return CandidateProfileView(
            settings_path=resolved_settings_path,
            candidate_profile_path=None,
            candidate_profile_exists=False,
            load_error="No candidate_profile_path is configured in settings.",
            candidate_name=None,
            compensation_floor_usd=None,
            preferred_base_usd=None,
            resume_source_path=None,
            resume_source_file_name=None,
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

    resolved_profile_path = str(profile_path)

    try:
        candidate_profile = load_candidate_profile(
            profile_path,
            base_directory=runtime_paths.base_directory,
        )
    except ConfigError as error:
        return CandidateProfileView(
            settings_path=resolved_settings_path,
            candidate_profile_path=resolved_profile_path,
            candidate_profile_exists=profile_path.exists(),
            load_error=str(error),
            candidate_name=None,
            compensation_floor_usd=None,
            preferred_base_usd=None,
            resume_source_path=None,
            resume_source_file_name=None,
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

    configured_resume_source_path = (
        candidate_profile.resume.source_path
        if candidate_profile.resume is not None
        else None
    )
    configured_normalized_text_path = (
        candidate_profile.resume.normalized_text_path
        if candidate_profile.resume is not None
        else None
    )
    resume_source_path = runtime_paths.resolve_optional(
        configured_resume_source_path
    )
    normalized_text_path = runtime_paths.resolve_optional(
        configured_normalized_text_path
    )
    resume_text = None
    resume_error = None

    if resume_source_path is not None:
        try:
            resume_text = load_resume_display_text(resume_source_path)
        except ConfigError as error:
            resume_error = str(error)

    return CandidateProfileView(
        settings_path=resolved_settings_path,
        candidate_profile_path=resolved_profile_path,
        candidate_profile_exists=profile_path.exists(),
        load_error=resume_error,
        candidate_name=candidate_profile.name,
        compensation_floor_usd=candidate_profile.compensation_floor_usd,
        preferred_base_usd=candidate_profile.preferred_base_usd,
        resume_source_path=(
            str(resume_source_path)
            if resume_source_path is not None
            else None
        ),
        resume_source_file_name=(
            resume_source_path.name
            if resume_source_path is not None
            else None
        ),
        resume_source_exists=(
            resume_source_path.exists()
            if resume_source_path is not None
            else False
        ),
        normalized_text_path=(
            str(normalized_text_path)
            if normalized_text_path is not None
            else None
        ),
        normalized_text_exists=(
            normalized_text_path.exists()
            if normalized_text_path is not None
            else False
        ),
        resume_character_count=len(resume_text) if resume_text is not None else None,
        resume_preview=_build_resume_preview(resume_text),
        core_strengths=candidate_profile.core_strengths,
        credible_adjacent=candidate_profile.credible_adjacent,
        learning_or_gap=candidate_profile.learning_or_gap,
        avoid=candidate_profile.avoid,
    )


def save_uploaded_resume(
    settings_path: str | None,
    uploaded_filename: str,
    uploaded_content: bytes,
    *,
    base_directory: str | Path | None = None,
) -> ResumeUploadResult:
    extension = Path(uploaded_filename).suffix.lower()

    if extension not in SUPPORTED_RESUME_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_RESUME_EXTENSIONS))
        raise ConfigError(
            f"Unsupported resume format: {extension or 'none'}. "
            f"Supported formats: {supported}"
        )

    if not uploaded_content:
        raise ConfigError("Uploaded resume file is empty.")

    runtime_paths = (
        RuntimePaths.from_settings(
            settings_path=settings_path,
            base_directory=base_directory,
        )
        if settings_path is not None and base_directory is not None
        else RuntimePaths.from_settings_argument(settings_path)
    )
    profile_path = runtime_paths.candidate_profile_path

    if profile_path is None:
        raise ConfigError("No candidate_profile_path is configured in settings.")

    profile_data = _load_profile_yaml(profile_path)
    candidate_data = profile_data.setdefault("candidate", {})
    resume_data = candidate_data.setdefault("resume", {})

    current_source_path = runtime_paths.resolve_optional(
        resume_data.get("source_path")
    )
    current_normalized_path = runtime_paths.resolve_optional(
        resume_data.get("normalized_text_path")
    )

    target_path = _get_resume_upload_target_path(
        profile_path=profile_path,
        current_source_path=(
            str(current_source_path)
            if current_source_path is not None
            else None
        ),
        extension=extension,
    )
    normalized_text_path = (
        current_normalized_path
        if current_normalized_path is not None
        else target_path.with_suffix(".normalized.txt")
    )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_text_path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = target_path.with_name(f".{target_path.stem}.upload{extension}")

    try:
        # Validate extraction before replacing the active resume. This avoids
        # clobbering a working resume with a corrupt DOCX or image-only PDF.
        temp_path.write_bytes(uploaded_content)
        load_resume_text(temp_path)

        target_path.write_bytes(uploaded_content)
        write_normalized_resume_text(target_path, normalized_text_path)
    finally:
        temp_path.unlink(missing_ok=True)

    resume_data["source_path"] = str(target_path)
    resume_data["normalized_text_path"] = str(normalized_text_path)
    _write_profile_yaml(profile_path, profile_data)

    return ResumeUploadResult(
        resume_source_path=str(target_path),
        normalized_text_path=str(normalized_text_path),
    )


def _load_profile_yaml(profile_path: Path) -> dict:
    if not profile_path.exists():
        raise ConfigError(f"Candidate profile does not exist: {profile_path}")

    try:
        profile_data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ConfigError(f"Could not read candidate profile: {profile_path}") from error

    if not isinstance(profile_data, dict):
        raise ConfigError(f"Candidate profile must be a YAML mapping: {profile_path}")

    return profile_data


def _write_profile_yaml(profile_path: Path, profile_data: dict) -> None:
    profile_path.write_text(
        yaml.safe_dump(profile_data, sort_keys=False),
        encoding="utf-8",
    )


def _get_resume_upload_target_path(
    profile_path: Path,
    current_source_path: str | None,
    extension: str,
) -> Path:
    if current_source_path:
        current_path = Path(current_source_path)

        if current_path.suffix.lower() == extension:
            return current_path

        return current_path.with_suffix(extension)

    return profile_path.with_name(f"resume{extension}")


def _build_resume_preview(resume_text: str | None) -> str | None:
    if resume_text is None:
        return None

    preview_text = resume_text

    if len(preview_text) > RESUME_PREVIEW_CHARACTER_LIMIT:
        preview_text = preview_text[:RESUME_PREVIEW_CHARACTER_LIMIT].rstrip() + "..."

    return _format_resume_preview(preview_text)


def _format_resume_preview(resume_text: str) -> str:
    # clean_text intentionally collapses whitespace for matching/scoring.
    # The GUI preview adds lightweight formatting back so the resume is readable.
    sectioned_text = resume_text.replace(" ## ", "\n\n## ")

    lines: list[str] = []

    for raw_line in sectioned_text.splitlines():
        line = raw_line.strip()

        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue

        if _should_start_resume_preview_section(line, lines):
            if lines and lines[-1] != "":
                lines.append("")

        lines.append(fill(line, width=RESUME_PREVIEW_LINE_WIDTH))

    return "\n".join(lines).strip()


def _should_start_resume_preview_section(line: str, existing_lines: list[str]) -> bool:
    if not existing_lines:
        return False

    lowered_line = line.lower()

    section_markers = (
        "## ",
        "professional summary",
        "core competencies",
        "technical skills",
        "professional experience",
        "work experience",
        "experience",
        "education",
        "certifications",
        "projects",
    )

    if lowered_line.startswith(section_markers):
        return True

    # DOCX extraction often preserves each job heading as a single text line.
    # Add breathing room before likely job entries without changing scoring text.
    if " | " in line and any(year in line for year in (" 20", " 19")):
        return True

    return False