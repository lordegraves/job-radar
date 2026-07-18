"""Create or migrate a Job Radar user workspace without replacing user files.

Normal first-run setup copies only safe packaged defaults. Profiles, databases,
and existing configuration move only from explicitly supplied sources, and
imported settings are checked for literal credentials before any copy occurs.
"""

from contextlib import ExitStack
from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path
from shutil import copy2
from typing import Any

import yaml

from job_radar.database import connect_database
from job_radar.runtime_paths import UserDataPaths


PACKAGED_BOOTSTRAP_DIRECTORY = "bootstrap_defaults"
PACKAGED_SETTINGS_FILENAME = "settings.yaml"
PACKAGED_COMPANY_CONFIG_FILENAME = "target-companies.yaml"
PACKAGED_SCORING_CONFIG_FILENAME = "scoring.yaml"

FORBIDDEN_CREDENTIAL_KEYS = {
    "api_key",
    "apikey",
    "credential",
    "credentials",
    "password",
    "secret",
    "smtp_password",
    "token",
}


class UserDataBootstrapError(RuntimeError):
    """Raised when existing user data makes a safe bootstrap impossible."""


@dataclass(frozen=True)
class BootstrapCopyResult:
    """Outcome of one non-destructive bootstrap copy."""

    source: Path
    destination: Path
    copied: bool


@dataclass(frozen=True)
class UserDataBootstrapResult:
    """Summary of one user-configuration bootstrap operation."""

    user_data_paths: UserDataPaths
    settings_result: BootstrapCopyResult
    company_config_result: BootstrapCopyResult
    scoring_config_result: BootstrapCopyResult
    profile_results: tuple[BootstrapCopyResult, ...]
    database_result: BootstrapCopyResult | None

    @property
    def all_results(self) -> tuple[BootstrapCopyResult, ...]:
        optional_database_results = (
            (self.database_result,)
            if self.database_result is not None
            else ()
        )

        return (
            self.settings_result,
            self.company_config_result,
            self.scoring_config_result,
            *self.profile_results,
            *optional_database_results,
        )

    @property
    def copied_files(self) -> tuple[BootstrapCopyResult, ...]:
        return tuple(
            result
            for result in self.all_results
            if result.copied
        )

    @property
    def preserved_files(self) -> tuple[BootstrapCopyResult, ...]:
        return tuple(
            result
            for result in self.all_results
            if not result.copied
        )


def create_user_data_directories(user_data_paths: UserDataPaths) -> None:
    """Create the standard writable directory layout when it is missing."""

    for directory in (
        user_data_paths.root,
        user_data_paths.config,
        user_data_paths.data,
        user_data_paths.logs,
        user_data_paths.profiles,
        user_data_paths.reports,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def bootstrap_user_configuration(
    *,
    source_settings_path: str | Path,
    source_company_config_path: str | Path,
    source_scoring_config_path: str | Path,
    user_data_paths: UserDataPaths,
    source_profiles_path: str | Path | None = None,
    source_database_path: str | Path | None = None,
) -> UserDataBootstrapResult:
    """Copy initial configuration and optional migration data into user storage."""

    create_user_data_directories(user_data_paths)

    settings_result = copy_bootstrap_settings_file(
        source_settings_path,
        user_data_paths.config / "settings.yaml",
    )
    company_config_result = copy_bootstrap_file(
        source_company_config_path,
        user_data_paths.config / "target-companies.yaml",
    )
    scoring_config_result = copy_bootstrap_file(
        source_scoring_config_path,
        user_data_paths.config / "scoring.yaml",
    )

    profile_results = (
        copy_bootstrap_tree(
            source_profiles_path,
            user_data_paths.profiles,
        )
        if source_profiles_path is not None
        else ()
    )

    database_result = (
        copy_bootstrap_database(
            source_database_path,
            user_data_paths.data / "job_radar.sqlite3",
        )
        if source_database_path is not None
        else None
    )

    return UserDataBootstrapResult(
        user_data_paths=user_data_paths,
        settings_result=settings_result,
        company_config_result=company_config_result,
        scoring_config_result=scoring_config_result,
        profile_results=profile_results,
        database_result=database_result,
    )


def bootstrap_packaged_user_configuration(
    *,
    user_data_paths: UserDataPaths,
    source_settings_path: str | Path | None = None,
    source_company_config_path: str | Path | None = None,
    source_scoring_config_path: str | Path | None = None,
    source_profiles_path: str | Path | None = None,
    source_database_path: str | Path | None = None,
) -> UserDataBootstrapResult:
    """Bootstrap from packaged safe defaults plus optional migration sources."""

    packaged_directory = files("job_radar").joinpath(
        PACKAGED_BOOTSTRAP_DIRECTORY
    )

    with ExitStack() as stack:
        settings_path = _resolve_bootstrap_source(
            explicit_path=source_settings_path,
            packaged_resource=packaged_directory.joinpath(
                PACKAGED_SETTINGS_FILENAME
            ),
            stack=stack,
        )
        company_config_path = _resolve_bootstrap_source(
            explicit_path=source_company_config_path,
            packaged_resource=packaged_directory.joinpath(
                PACKAGED_COMPANY_CONFIG_FILENAME
            ),
            stack=stack,
        )
        scoring_config_path = _resolve_bootstrap_source(
            explicit_path=source_scoring_config_path,
            packaged_resource=packaged_directory.joinpath(
                PACKAGED_SCORING_CONFIG_FILENAME
            ),
            stack=stack,
        )

        return bootstrap_user_configuration(
            source_settings_path=settings_path,
            source_company_config_path=company_config_path,
            source_scoring_config_path=scoring_config_path,
            source_profiles_path=source_profiles_path,
            source_database_path=source_database_path,
            user_data_paths=user_data_paths,
        )


def copy_bootstrap_tree(
    source_root: str | Path,
    destination_root: str | Path,
) -> tuple[BootstrapCopyResult, ...]:
    """Copy every file in a bootstrap tree without replacing user data."""

    source_root_path = Path(source_root).resolve()
    destination_root_path = Path(destination_root).resolve()

    if not source_root_path.is_dir():
        raise UserDataBootstrapError(
            f"Bootstrap source directory does not exist: {source_root_path}"
        )

    if destination_root_path.exists() and not destination_root_path.is_dir():
        raise UserDataBootstrapError(
            f"Bootstrap destination is not a directory: {destination_root_path}"
        )

    results: list[BootstrapCopyResult] = []

    for source_path in sorted(source_root_path.rglob("*")):
        if not source_path.is_file():
            continue

        relative_path = source_path.relative_to(source_root_path)
        destination_path = destination_root_path / relative_path
        results.append(copy_bootstrap_file(source_path, destination_path))

    return tuple(results)


def copy_bootstrap_database(
    source: str | Path,
    destination: str | Path,
) -> BootstrapCopyResult:
    """Copy a SQLite database safely without replacing existing user data."""

    source_path = Path(source).resolve()
    destination_path = Path(destination).resolve()

    if not source_path.is_file():
        raise UserDataBootstrapError(
            f"Bootstrap source database does not exist: {source_path}"
        )

    if destination_path.exists():
        if not destination_path.is_file():
            raise UserDataBootstrapError(
                f"Bootstrap database destination is not a file: {destination_path}"
            )

        return BootstrapCopyResult(
            source=source_path,
            destination=destination_path,
            copied=False,
        )

    destination_path.parent.mkdir(parents=True, exist_ok=True)

    with connect_database(source_path) as source_connection:
        with connect_database(destination_path) as destination_connection:
            source_connection.backup(destination_connection)

    return BootstrapCopyResult(
        source=source_path,
        destination=destination_path,
        copied=True,
    )


def copy_bootstrap_settings_file(
    source: str | Path,
    destination: str | Path,
) -> BootstrapCopyResult:
    """Copy settings only when they contain no literal credential values."""

    source_path = Path(source).resolve()
    destination_path = Path(destination).resolve()

    if destination_path.exists():
        if not destination_path.is_file():
            raise UserDataBootstrapError(
                f"Bootstrap destination is not a file: {destination_path}"
            )

        return BootstrapCopyResult(
            source=source_path,
            destination=destination_path,
            copied=False,
        )

    if not source_path.is_file():
        raise UserDataBootstrapError(
            f"Bootstrap source file does not exist: {source_path}"
        )

    try:
        settings_data = yaml.safe_load(
            source_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise UserDataBootstrapError(
            f"Bootstrap settings file could not be read safely: {source_path}"
        ) from error

    if settings_data is not None and not isinstance(settings_data, dict):
        raise UserDataBootstrapError(
            "Bootstrap settings file must contain a YAML mapping"
        )

    forbidden_path = _find_literal_credential_path(settings_data or {})

    if forbidden_path is not None:
        raise UserDataBootstrapError(
            "Bootstrap settings contain a literal credential value at "
            f"{forbidden_path}. Store only a credential reference such as "
            "smtp_password_env."
        )

    return copy_bootstrap_file(source_path, destination)


def copy_bootstrap_file(
    source: str | Path,
    destination: str | Path,
) -> BootstrapCopyResult:
    """Copy one bootstrap file without replacing existing user data."""

    source_path = Path(source).resolve()
    destination_path = Path(destination).resolve()

    if not source_path.is_file():
        raise UserDataBootstrapError(
            f"Bootstrap source file does not exist: {source_path}"
        )

    if destination_path.exists():
        if not destination_path.is_file():
            raise UserDataBootstrapError(
                f"Bootstrap destination is not a file: {destination_path}"
            )

        return BootstrapCopyResult(
            source=source_path,
            destination=destination_path,
            copied=False,
        )

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    copy2(source_path, destination_path)

    return BootstrapCopyResult(
        source=source_path,
        destination=destination_path,
        copied=True,
    )


def _resolve_bootstrap_source(
    *,
    explicit_path: str | Path | None,
    packaged_resource: Any,
    stack: ExitStack,
) -> Path:
    if explicit_path is not None:
        return Path(explicit_path).expanduser().resolve()

    return stack.enter_context(as_file(packaged_resource)).resolve()


def _find_literal_credential_path(
    value: Any,
    *,
    path: tuple[str, ...] = (),
) -> str | None:
    if isinstance(value, dict):
        for raw_key, child_value in value.items():
            key = str(raw_key)
            normalized_key = key.strip().lower().replace("-", "_")

            if (
                _is_literal_credential_key(normalized_key)
                and _has_literal_credential_value(child_value)
            ):
                return ".".join((*path, key))

            nested_path = _find_literal_credential_path(
                child_value,
                path=(*path, key),
            )

            if nested_path is not None:
                return nested_path

    if isinstance(value, list):
        for index, child_value in enumerate(value):
            nested_path = _find_literal_credential_path(
                child_value,
                path=(*path, str(index)),
            )

            if nested_path is not None:
                return nested_path

    return None


def _is_literal_credential_key(key: str) -> bool:
    if key.endswith("_env"):
        return False

    if key in FORBIDDEN_CREDENTIAL_KEYS:
        return True

    return key.endswith(
        (
            "_api_key",
            "_credential",
            "_credentials",
            "_password",
            "_secret",
            "_token",
        )
    )


def _has_literal_credential_value(value: Any) -> bool:
    if value is None:
        return False

    if isinstance(value, str):
        return bool(value.strip())

    return True
