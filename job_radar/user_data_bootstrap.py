from dataclasses import dataclass
from pathlib import Path
from shutil import copy2

from job_radar.database import connect_database
from job_radar.runtime_paths import UserDataPaths


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
    source_profiles_path: str | Path,
    user_data_paths: UserDataPaths,
    source_database_path: str | Path | None = None,
) -> UserDataBootstrapResult:
    """Copy initial configuration and optional database into user storage."""

    create_user_data_directories(user_data_paths)

    settings_result = copy_bootstrap_file(
        source_settings_path,
        user_data_paths.config / "settings.yaml",
    )
    profile_results = copy_bootstrap_tree(
        source_profiles_path,
        user_data_paths.profiles,
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
        profile_results=profile_results,
        database_result=database_result,
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
