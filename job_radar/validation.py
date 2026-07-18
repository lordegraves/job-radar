"""Check configuration and runtime prerequisites without starting a scan.

Validation loads the same settings, company, scoring, profile, and path rules
used by normal execution, then reports whether required inputs and writable
output locations are ready. It does not collect jobs or send email.
"""

from dataclasses import dataclass
from pathlib import Path

from job_radar.candidate_profile import load_candidate_profile
from job_radar.config import ConfigError, load_companies
from job_radar.resume_loader import load_resume_text
from job_radar.runtime_paths import RuntimePaths
from job_radar.scoring import load_scoring_config


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

    base_directory = _get_settings_base_directory(settings_path)
    runtime_paths = RuntimePaths.from_settings(
        settings_path=settings_path,
        company_config_path=config_path,
        scoring_config_path=scoring_path,
        base_directory=base_directory,
    )

    companies = load_companies(runtime_paths.company_config_path)
    checks.append(f"company config loaded: {runtime_paths.company_config_path}")

    if not companies:
        raise ConfigError("company config has no enabled companies")

    checks.append(f"enabled companies: {len(companies)}")

    checks.append(f"settings loaded: {runtime_paths.settings_path}")

    load_scoring_config(runtime_paths.scoring_config_path)
    checks.append(f"scoring config loaded: {runtime_paths.scoring_config_path}")

    _validate_writable_parent(runtime_paths.database_path)
    checks.append(f"database path writable: {runtime_paths.database_path}")

    _validate_writable_directory(runtime_paths.reports_path)
    checks.append(f"reports path writable: {runtime_paths.reports_path}")

    _validate_writable_directory(runtime_paths.logs_path)
    checks.append(f"logs path writable: {runtime_paths.logs_path}")

    _validate_candidate_profile(runtime_paths, checks)

    if report_path is not None:
        _validate_output_parent(report_path, "report")

    if email_preview_path is not None:
        _validate_output_parent(email_preview_path, "email preview")

    return ValidationResult(passed=True, checks=checks)


def _get_settings_base_directory(settings_path: str | Path) -> Path:
    resolved_settings_path = Path(settings_path).expanduser().resolve()

    if resolved_settings_path.parent.name.casefold() == "config":
        return resolved_settings_path.parent.parent

    return resolved_settings_path.parent


def _validate_candidate_profile(
    runtime_paths: RuntimePaths,
    checks: list[str],
) -> None:
    candidate_profile_path = runtime_paths.candidate_profile_path

    if candidate_profile_path is None:
        checks.append("candidate profile not configured")
        return

    candidate_profile = load_candidate_profile(
        candidate_profile_path,
        base_directory=runtime_paths.base_directory,
    )
    checks.append(f"candidate profile loaded: {candidate_profile_path}")

    if candidate_profile.resume is None:
        checks.append("resume not configured")
        return

    resume_source_path = Path(candidate_profile.resume.source_path)
    load_resume_text(resume_source_path)
    checks.append(f"resume loaded: {resume_source_path}")

    if candidate_profile.resume.normalized_text_path is not None:
        normalized_text_path = Path(candidate_profile.resume.normalized_text_path)
        _validate_writable_parent(normalized_text_path)
        checks.append(
            f"normalized resume output path writable: {normalized_text_path}"
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
