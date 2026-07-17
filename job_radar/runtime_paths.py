import os
import sys
from dataclasses import dataclass
from pathlib import Path

from job_radar.config import ApplicationSettings, load_settings


DEFAULT_SETTINGS_PATH = "config/settings.yaml"
DEFAULT_COMPANY_CONFIG_PATH = "config/target-companies.yaml"
DEFAULT_SCORING_CONFIG_PATH = "config/scoring.yaml"
DEFAULT_REPORT_PATH = "reports/target-scan.html"
DEFAULT_EMAIL_PREVIEW_PATH = "reports/target-email-preview.txt"

APPLICATION_DATA_DIRECTORY_NAME = "JobRadar"
APPLICATION_DATA_ENVIRONMENT_VARIABLE = "JOB_RADAR_DATA_DIR"


@dataclass(frozen=True)
class UserDataPaths:
    """Standard writable locations owned by the current Job Radar user."""

    root: Path
    config: Path
    data: Path
    logs: Path
    profiles: Path
    reports: Path

    @classmethod
    def from_root(cls, root: str | Path) -> "UserDataPaths":
        resolved_root = Path(root).expanduser().resolve()

        return cls(
            root=resolved_root,
            config=resolved_root / "config",
            data=resolved_root / "data",
            logs=resolved_root / "logs",
            profiles=resolved_root / "profiles",
            reports=resolved_root / "reports",
        )

    @classmethod
    def default(cls) -> "UserDataPaths":
        return cls.from_root(get_default_user_data_directory())


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

    def resolve(self, path: str | Path) -> Path:
        """Resolve a required runtime path from this run's base directory."""

        return _resolve_from_base(path, self.base_directory)

    def resolve_optional(self, path: str | Path | None) -> Path | None:
        """Resolve an optional runtime path from this run's base directory."""

        return _resolve_optional_from_base(path, self.base_directory)

    @classmethod
    def from_settings_argument(
        cls,
        settings_path: str | Path | None,
        *,
        company_config_path: str | Path = DEFAULT_COMPANY_CONFIG_PATH,
        scoring_config_path: str | Path = DEFAULT_SCORING_CONFIG_PATH,
    ) -> "RuntimePaths":
        """Resolve an explicit settings file or use the active default."""

        if settings_path is None:
            return cls.from_default_settings(
                company_config_path=company_config_path,
                scoring_config_path=scoring_config_path,
            )

        return cls.from_settings(
            settings_path=settings_path,
            company_config_path=company_config_path,
            scoring_config_path=scoring_config_path,
        )

    @classmethod
    def from_default_settings(
        cls,
        *,
        company_config_path: str | Path = DEFAULT_COMPANY_CONFIG_PATH,
        scoring_config_path: str | Path = DEFAULT_SCORING_CONFIG_PATH,
    ) -> "RuntimePaths":
        """Use bootstrapped user settings when present, otherwise use the repo."""

        user_data_paths = UserDataPaths.default()
        user_settings_path = user_data_paths.config / "settings.yaml"

        if user_settings_path.is_file():
            return cls.from_settings(
                settings_path=user_settings_path,
                company_config_path=company_config_path,
                scoring_config_path=scoring_config_path,
                base_directory=user_data_paths.root,
            )

        return cls.from_settings(
            settings_path=DEFAULT_SETTINGS_PATH,
            company_config_path=company_config_path,
            scoring_config_path=scoring_config_path,
        )

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

        return cls.from_application_settings(
            settings,
            settings_path=resolved_settings_path,
            company_config_path=company_config_path,
            scoring_config_path=scoring_config_path,
            base_directory=base_path,
        )

    @classmethod
    def from_application_settings(
        cls,
        settings: ApplicationSettings,
        *,
        settings_path: str | Path,
        company_config_path: str | Path = DEFAULT_COMPANY_CONFIG_PATH,
        scoring_config_path: str | Path = DEFAULT_SCORING_CONFIG_PATH,
        base_directory: str | Path | None = None,
    ) -> "RuntimePaths":
        base_path = _resolve_base_directory(base_directory)

        return cls(
            base_directory=base_path,
            settings_path=_resolve_from_base(settings_path, base_path),
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
        )


def get_default_user_data_directory() -> Path:
    """Return the operating system's normal location for Job Radar user data.

    An explicit JOB_RADAR_DATA_DIR value takes priority. This provides a safe
    test and recovery override without requiring private data to live inside
    the source repository.
    """

    configured_directory = os.environ.get(APPLICATION_DATA_ENVIRONMENT_VARIABLE)

    if configured_directory:
        return Path(configured_directory).expanduser().resolve()

    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")

        if local_app_data:
            return (Path(local_app_data) / APPLICATION_DATA_DIRECTORY_NAME).resolve()

        return (
            Path.home() / "AppData" / "Local" / APPLICATION_DATA_DIRECTORY_NAME
        ).resolve()

    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / APPLICATION_DATA_DIRECTORY_NAME
        ).resolve()

    xdg_data_home = os.environ.get("XDG_DATA_HOME")

    if xdg_data_home:
        return (Path(xdg_data_home) / "job-radar").resolve()

    return (Path.home() / ".local" / "share" / "job-radar").resolve()


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
