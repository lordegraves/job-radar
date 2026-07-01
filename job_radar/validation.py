from dataclasses import dataclass
from pathlib import Path
from typing import Any

from job_radar.candidate_profile import load_candidate_profile
from job_radar.config import ConfigError, load_companies, load_settings
from job_radar.resume_loader import load_resume_text
from job_radar.scoring import ScoringConfigError, load_scoring_config


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    checks: list[str]


def validate_configuration(
    config_path: str,
    settings_path: str,
    scoring_path: str,
    report_path: str | None = None,
    email_preview_path: str | None = None,
) -> ValidationResult:
    checks: list[str] = []

    companies = load_companies(config_path)
    checks.append(f"company config loaded: {config_path}")

    if not companies:
        raise ConfigError("company config has no enabled companies")

    checks.append(f"enabled companies: {len(companies)}")

    settings = load_settings(settings_path)
    checks.append(f"settings loaded: {settings_path}")

    load_scoring_config(scoring_path)
    checks.append(f"scoring config loaded: {scoring_path}")

    _validate_database_path(settings)
    checks.append(f"database path writable: {settings['database_path']}")

    _validate_configured_directory(settings, "reports_path")
    checks.append(f"reports path writable: {settings['reports_path']}")

    _validate_configured_directory(settings, "logs_path")
    checks.append(f"logs path writable: {settings['logs_path']}")

    _validate_candidate_profile(settings, checks)

    if report_path is not None:
        _validate_output_parent(report_path, "report")

    if email_preview_path is not None:
        _validate_output_parent(email_preview_path, "email preview")

    return ValidationResult(passed=True, checks=checks)


def _validate_database_path(settings: dict[str, Any]) -> None:
    database_path = settings.get("database_path")

    if not isinstance(database_path, str):
        raise ConfigError("settings.yaml database_path must be a string")

    _validate_writable_parent(Path(database_path))


def _validate_configured_directory(
    settings: dict[str, Any],
    key: str,
) -> None:
    directory_path = settings.get(key)

    if not isinstance(directory_path, str):
        raise ConfigError(f"settings.yaml {key} must be a string")

    _validate_writable_directory(Path(directory_path))


def _validate_candidate_profile(
    settings: dict[str, Any],
    checks: list[str],
) -> None:
    candidate_profile_path = settings.get("candidate_profile_path")

    if candidate_profile_path is None:
        checks.append("candidate profile not configured")
        return

    if not isinstance(candidate_profile_path, str):
        raise ConfigError("settings.yaml candidate_profile_path must be a string")

    candidate_profile = load_candidate_profile(candidate_profile_path)
    checks.append(f"candidate profile loaded: {candidate_profile_path}")

    if candidate_profile.resume is None:
        checks.append("resume not configured")
        return

    load_resume_text(candidate_profile.resume.source_path)
    checks.append(f"resume loaded: {candidate_profile.resume.source_path}")

    if candidate_profile.resume.normalized_text_path is not None:
        _validate_writable_parent(Path(candidate_profile.resume.normalized_text_path))
        checks.append(
            "normalized resume output path writable: "
            f"{candidate_profile.resume.normalized_text_path}"
        )


def _validate_output_parent(output_path: str, label: str) -> None:
    _validate_writable_parent(Path(output_path))


def _validate_writable_parent(path: Path) -> None:
    parent = path.parent

    if str(parent) == "":
        parent = Path(".")

    _validate_writable_directory(parent)


def _validate_writable_directory(directory_path: Path) -> None:
    directory_path.mkdir(parents=True, exist_ok=True)

    if not directory_path.is_dir():
        raise ConfigError(f"Path is not a directory: {directory_path}")

    probe_path = directory_path / ".job_radar_write_test"

    try:
        probe_path.write_text("ok\n", encoding="utf-8")
    except OSError as error:
        raise ConfigError(f"Directory is not writable: {directory_path}") from error
    finally:
        if probe_path.exists():
            probe_path.unlink()