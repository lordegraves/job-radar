"""Verify that every runtime path resolves to the intended ownership boundary.

The tests cover OS defaults, explicit overrides, user-workspace preference,
development fallbacks, absolute paths, and relative path resolution using only
temporary directories.
"""

from pathlib import Path

import job_radar.runtime_paths as runtime_paths_module
from job_radar.config import load_settings
from job_radar.runtime_paths import (
    APPLICATION_DATA_ENVIRONMENT_VARIABLE,
    RuntimePaths,
    UserDataPaths,
    get_default_user_data_directory,
)


def _write_settings(settings_path: Path, content: str) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(content, encoding="utf-8")


def test_default_user_data_directory_honors_environment_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configured_directory = tmp_path / "custom-job-radar-data"
    monkeypatch.setenv(
        APPLICATION_DATA_ENVIRONMENT_VARIABLE,
        str(configured_directory),
    )

    assert get_default_user_data_directory() == configured_directory.resolve()


def test_default_user_data_directory_uses_windows_local_app_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.delenv(APPLICATION_DATA_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setattr(runtime_paths_module.os, "name", "nt")

    assert get_default_user_data_directory() == (
        local_app_data / "JobRadar"
    ).resolve()


def test_user_data_paths_define_standard_writable_layout(
    tmp_path: Path,
) -> None:
    root = tmp_path / "JobRadar"

    user_data_paths = UserDataPaths.from_root(root)

    assert user_data_paths.root == root.resolve()
    assert user_data_paths.config == root.resolve() / "config"
    assert user_data_paths.data == root.resolve() / "data"
    assert user_data_paths.logs == root.resolve() / "logs"
    assert user_data_paths.profiles == root.resolve() / "profiles"
    assert user_data_paths.resumes == root.resolve() / "resumes"
    assert user_data_paths.reports == root.resolve() / "reports"


def test_default_user_data_paths_use_default_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "JobRadar"
    monkeypatch.setenv(
        APPLICATION_DATA_ENVIRONMENT_VARIABLE,
        str(root),
    )

    user_data_paths = UserDataPaths.default()

    assert user_data_paths.root == root.resolve()
    assert user_data_paths.data == root.resolve() / "data"
    assert user_data_paths.profiles == root.resolve() / "profiles"
    assert user_data_paths.resumes == root.resolve() / "resumes"


def test_runtime_paths_settings_argument_uses_active_default_for_none(
    tmp_path: Path,
    monkeypatch,
) -> None:
    user_data_root = tmp_path / "user-data"
    user_settings_path = user_data_root / "config" / "settings.yaml"
    _write_settings(
        user_settings_path,
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs

""",
    )
    monkeypatch.setenv(
        APPLICATION_DATA_ENVIRONMENT_VARIABLE,
        str(user_data_root),
    )

    runtime_paths = RuntimePaths.from_settings_argument(None)

    assert runtime_paths.base_directory == user_data_root.resolve()
    assert runtime_paths.settings_path == user_settings_path.resolve()
    assert runtime_paths.database_path == (
        user_data_root / "data" / "job_radar.sqlite3"
    ).resolve()


def test_runtime_paths_settings_argument_preserves_explicit_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository_root = tmp_path / "repository"
    explicit_settings_path = repository_root / "config" / "settings.yaml"
    user_data_root = tmp_path / "user-data"
    _write_settings(
        explicit_settings_path,
        """
database_path: data/explicit.sqlite3
reports_path: reports
logs_path: logs

""",
    )
    monkeypatch.chdir(repository_root)
    monkeypatch.setenv(
        APPLICATION_DATA_ENVIRONMENT_VARIABLE,
        str(user_data_root),
    )

    runtime_paths = RuntimePaths.from_settings_argument(
        "config/settings.yaml"
    )

    assert runtime_paths.base_directory == repository_root.resolve()
    assert runtime_paths.settings_path == explicit_settings_path.resolve()
    assert runtime_paths.user_data_directory == repository_root.resolve()
    assert runtime_paths.database_path == (
        repository_root / "data" / "explicit.sqlite3"
    ).resolve()


def test_runtime_paths_use_bootstrapped_user_settings_by_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    user_data_root = tmp_path / "user-data"
    user_settings_path = user_data_root / "config" / "settings.yaml"
    _write_settings(
        user_settings_path,
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs
candidate_profile_path: profiles/example/profile.yaml

""",
    )
    monkeypatch.setenv(
        APPLICATION_DATA_ENVIRONMENT_VARIABLE,
        str(user_data_root),
    )

    runtime_paths = RuntimePaths.from_default_settings()

    assert runtime_paths.base_directory == user_data_root.resolve()
    assert runtime_paths.settings_path == user_settings_path.resolve()
    assert runtime_paths.database_path == (
        user_data_root / "data" / "job_radar.sqlite3"
    ).resolve()
    assert runtime_paths.reports_path == (
        user_data_root / "reports"
    ).resolve()
    assert runtime_paths.logs_path == (
        user_data_root / "logs"
    ).resolve()
    assert runtime_paths.candidate_profile_path == (
        user_data_root / "profiles" / "example" / "profile.yaml"
    ).resolve()
    assert runtime_paths.user_data_directory == user_data_root.resolve()


def test_runtime_paths_uses_settings_parent_for_flat_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    _write_settings(
        settings_path,
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs
""",
    )
    monkeypatch.chdir(tmp_path.parent)

    runtime_paths = RuntimePaths.from_settings_argument(settings_path)

    assert runtime_paths.user_data_directory == tmp_path.resolve()


def test_runtime_paths_fall_back_to_repository_settings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository_root = tmp_path / "repository"
    repository_settings_path = (
        repository_root / "config" / "settings.yaml"
    )
    user_data_root = tmp_path / "user-data"
    _write_settings(
        repository_settings_path,
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs

""",
    )
    monkeypatch.chdir(repository_root)
    monkeypatch.setenv(
        APPLICATION_DATA_ENVIRONMENT_VARIABLE,
        str(user_data_root),
    )

    runtime_paths = RuntimePaths.from_default_settings()

    assert runtime_paths.base_directory == repository_root.resolve()
    assert runtime_paths.settings_path == repository_settings_path.resolve()
    assert runtime_paths.database_path == (
        repository_root / "data" / "job_radar.sqlite3"
    ).resolve()
    assert runtime_paths.reports_path == (
        repository_root / "reports"
    ).resolve()
    assert runtime_paths.logs_path == (
        repository_root / "logs"
    ).resolve()


def test_runtime_paths_resolve_relative_paths_from_explicit_base(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    _write_settings(
        settings_path,
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs
candidate_profile_path: profiles/example/profile.yaml

""",
    )

    runtime_paths = RuntimePaths.from_settings(
        settings_path="config/settings.yaml",
        base_directory=tmp_path,
    )

    assert runtime_paths.base_directory == tmp_path.resolve()
    assert runtime_paths.settings_path == settings_path.resolve()
    assert runtime_paths.company_config_path == (
        tmp_path / "config" / "target-companies.yaml"
    ).resolve()
    assert runtime_paths.scoring_config_path == (
        tmp_path / "config" / "scoring.yaml"
    ).resolve()
    assert runtime_paths.database_path == (
        tmp_path / "data" / "job_radar.sqlite3"
    ).resolve()
    assert runtime_paths.reports_path == (tmp_path / "reports").resolve()
    assert runtime_paths.logs_path == (tmp_path / "logs").resolve()
    assert runtime_paths.candidate_profile_path == (
        tmp_path / "profiles" / "example" / "profile.yaml"
    ).resolve()

def test_runtime_paths_preserve_absolute_paths(tmp_path: Path) -> None:
    database_path = tmp_path / "external" / "job_radar.sqlite3"
    reports_path = tmp_path / "external" / "reports"
    logs_path = tmp_path / "external" / "logs"
    profile_path = tmp_path / "external" / "profile.yaml"
    settings_path = tmp_path / "config" / "settings.yaml"

    _write_settings(
        settings_path,
        f"""
database_path: {database_path}
reports_path: {reports_path}
logs_path: {logs_path}
candidate_profile_path: {profile_path}

""",
    )

    runtime_paths = RuntimePaths.from_settings(
        settings_path=settings_path,
        base_directory=tmp_path / "unused-base",
    )

    assert runtime_paths.database_path == database_path.resolve()
    assert runtime_paths.reports_path == reports_path.resolve()
    assert runtime_paths.logs_path == logs_path.resolve()
    assert runtime_paths.candidate_profile_path == profile_path.resolve()


def test_runtime_paths_allow_optional_profile_path(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    _write_settings(
        settings_path,
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs

""",
    )

    runtime_paths = RuntimePaths.from_settings(
        settings_path=settings_path,
        base_directory=tmp_path,
    )

    assert runtime_paths.candidate_profile_path is None


def test_runtime_paths_resolve_required_and_optional_output_paths(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    _write_settings(
        settings_path,
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs

""",
    )

    runtime_paths = RuntimePaths.from_settings(
        settings_path=settings_path,
        base_directory=tmp_path,
    )

    assert runtime_paths.resolve("reports/target-scan.html") == (
        tmp_path / "reports" / "target-scan.html"
    ).resolve()
    assert runtime_paths.resolve(tmp_path / "external" / "report.html") == (
        tmp_path / "external" / "report.html"
    ).resolve()
    assert runtime_paths.resolve_optional("reports/email-preview.txt") == (
        tmp_path / "reports" / "email-preview.txt"
    ).resolve()
    assert runtime_paths.resolve_optional(None) is None


def test_runtime_paths_build_from_loaded_application_settings(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    _write_settings(
        settings_path,
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs
candidate_profile_path: profiles/example/profile.yaml

""",
    )
    settings = load_settings(settings_path)

    runtime_paths = RuntimePaths.from_application_settings(
        settings,
        settings_path=settings_path,
        company_config_path="config/custom-companies.yaml",
        scoring_config_path="config/custom-scoring.yaml",
        base_directory=tmp_path,
    )

    assert runtime_paths.settings_path == settings_path.resolve()
    assert runtime_paths.company_config_path == (
        tmp_path / "config" / "custom-companies.yaml"
    ).resolve()
    assert runtime_paths.scoring_config_path == (
        tmp_path / "config" / "custom-scoring.yaml"
    ).resolve()
    assert runtime_paths.database_path == (
        tmp_path / "data" / "job_radar.sqlite3"
    ).resolve()
    assert runtime_paths.candidate_profile_path == (
        tmp_path / "profiles" / "example" / "profile.yaml"
    ).resolve()


def test_runtime_paths_use_current_working_directory_by_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    settings_path = tmp_path / "config" / "settings.yaml"
    _write_settings(
        settings_path,
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs

""",
    )

    runtime_paths = RuntimePaths.from_settings()

    assert runtime_paths.base_directory == tmp_path.resolve()
    assert runtime_paths.settings_path == settings_path.resolve()
    assert runtime_paths.database_path == (
        tmp_path / "data" / "job_radar.sqlite3"
    ).resolve()
