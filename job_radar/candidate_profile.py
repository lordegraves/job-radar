from dataclasses import dataclass
from pathlib import Path
from typing import Any

from job_radar.config import ConfigError, load_yaml_file
from job_radar.normalize import clean_text


@dataclass(frozen=True)
class CandidateResumeConfig:
    source_path: str
    normalized_text_path: str | None = None


@dataclass(frozen=True)
class CandidateProfile:
    name: str
    compensation_floor_usd: int | None
    preferred_base_usd: int | None
    resume: CandidateResumeConfig | None
    core_strengths: list[str]
    credible_adjacent: list[str]
    learning_or_gap: list[str]
    avoid: list[str]


def load_candidate_profile(path: str | Path) -> CandidateProfile:
    profile_path = Path(path)
    data = load_yaml_file(profile_path)

    candidate = data.get("candidate")
    if not isinstance(candidate, dict):
        raise ConfigError("candidate profile must contain a top-level candidate mapping")

    name = _optional_string(candidate.get("name"), "candidate.name") or "Unknown"
    compensation_floor_usd = _optional_int(
        candidate.get("compensation_floor_usd"),
        "candidate.compensation_floor_usd",
    )
    preferred_base_usd = _optional_int(
        candidate.get("preferred_base_usd"),
        "candidate.preferred_base_usd",
    )

    return CandidateProfile(
        name=name,
        compensation_floor_usd=compensation_floor_usd,
        preferred_base_usd=preferred_base_usd,
        resume=_load_resume_config(candidate.get("resume")),
        core_strengths=_string_list(candidate.get("core_strengths"), "core_strengths"),
        credible_adjacent=_string_list(
            candidate.get("credible_adjacent"),
            "credible_adjacent",
        ),
        learning_or_gap=_string_list(candidate.get("learning_or_gap"), "learning_or_gap"),
        avoid=_string_list(candidate.get("avoid"), "avoid"),
    )


def _load_resume_config(raw_resume: Any) -> CandidateResumeConfig | None:
    if raw_resume is None:
        return None

    if not isinstance(raw_resume, dict):
        raise ConfigError("candidate.resume must be a mapping")

    source_path = _required_string(
        raw_resume.get("source_path"),
        "candidate.resume.source_path",
    )
    normalized_text_path = _optional_string(
        raw_resume.get("normalized_text_path"),
        "candidate.resume.normalized_text_path",
    )

    return CandidateResumeConfig(
        source_path=source_path,
        normalized_text_path=normalized_text_path,
    )


def _string_list(raw_values: Any, config_key: str) -> list[str]:
    if raw_values is None:
        return []

    if not isinstance(raw_values, list):
        raise ConfigError(f"candidate.{config_key} must be a list")

    values: list[str] = []

    for index, raw_value in enumerate(raw_values, start=1):
        if not isinstance(raw_value, str):
            raise ConfigError(
                f"candidate.{config_key} entry #{index} must be a string"
            )

        cleaned_value = clean_text(raw_value)

        if not cleaned_value:
            raise ConfigError(
                f"candidate.{config_key} entry #{index} cannot be empty"
            )

        values.append(cleaned_value)

    return values


def _required_string(raw_value: Any, config_key: str) -> str:
    value = _optional_string(raw_value, config_key)

    if value is None:
        raise ConfigError(f"{config_key} is required")

    return value


def _optional_string(raw_value: Any, config_key: str) -> str | None:
    if raw_value is None:
        return None

    if not isinstance(raw_value, str):
        raise ConfigError(f"{config_key} must be a string")

    cleaned_value = clean_text(raw_value)

    if not cleaned_value:
        raise ConfigError(f"{config_key} cannot be empty")

    return cleaned_value


def _optional_int(raw_value: Any, config_key: str) -> int | None:
    if raw_value is None:
        return None

    if not isinstance(raw_value, int) or isinstance(raw_value, bool):
        raise ConfigError(f"{config_key} must be an integer")

    if raw_value < 0:
        raise ConfigError(f"{config_key} must be greater than or equal to 0")

    return raw_value