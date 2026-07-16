from dataclasses import dataclass
from pathlib import Path

from job_radar.config import load_settings


DEFAULT_SETTINGS_PATH = "config/settings.yaml"
DEFAULT_COMPANY_CONFIG_PATH = "config/target-companies.yaml"
DEFAULT_SCORING_CONFIG_PATH = "config/scoring.yaml"


@dataclass(frozen=True)
class RuntimePaths:
    """Resolved paths used by one Job Radar application run.

    Relative paths continue to resolve from the working directory so current
    development and command-line behavior remains unchanged. A packaged
    application can later provide a different base directory without requiring
    each feature to implement its own path rules.
    """

    base_directory: Path
    settings_path: Path
    company_config_path: Path
    scoring_config_path: Path
    database_path: Path
    reports_path: Path
    logs_path: Path
    candidate_profile_path: Path | None
    job_history_workbook_path: Path | None

    @classmethod
    def from_settings(
        cls,
        settings_path: str | Path = DEFAULT_SETTINGS_PATH,
        *,
        company_config_path: str | Path = DEFAULT_COMPANY_CONFIG_PATH,
        scoring_config_path: str | Path = DEFAULT_SCORING_CONFIG_PATH,
        base_directory: str | Path | None = None,
    ) -> "RuntimePaths":
        base_path = _resolve_base_directory(base_directory)
        resolved_settings_path = _resolve_from_base(settings_path, base_path)
        settings = load_settings(resolved_settings_path)

        return cls(
            base_directory=base_path,
            settings_path=resolved_settings_path,
            company_config_path=_resolve_from_base(
                company_config_path,
                base_path,
            ),
            scoring_config_path=_resolve_from_base(
                scoring_config_path,
                base_path,
            ),
            database_path=_resolve_from_base(
                settings.database_path,
                base_path,
            ),
            reports_path=_resolve_from_base(
                settings.reports_path,
                base_path,
            ),
            logs_path=_resolve_from_base(
                settings.logs_path,
                base_path,
            ),
            candidate_profile_path=_resolve_optional_from_base(
                settings.candidate_profile_path,
                base_path,
            ),
            job_history_workbook_path=_resolve_optional_from_base(
                settings.job_history_workbook_path,
                base_path,
            ),
        )


def _resolve_base_directory(base_directory: str | Path | None) -> Path:
    if base_directory is None:
        return Path.cwd().resolve()

    return Path(base_directory).resolve()


def _resolve_from_base(path: str | Path, base_directory: Path) -> Path:
    candidate_path = Path(path)

    if candidate_path.is_absolute():
        return candidate_path.resolve()

    return (base_directory / candidate_path).resolve()


def _resolve_optional_from_base(
    path: str | Path | None,
    base_directory: Path,
) -> Path | None:
    if path is None:
        return None

    return _resolve_from_base(path, base_directory)
