from pathlib import Path

from job_radar.runtime_paths import RuntimePaths


def _write_settings(settings_path: Path, content: str) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(content, encoding="utf-8")


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
job_history_workbook_path: imports/job-history.xlsx

retention: {}
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
    assert runtime_paths.job_history_workbook_path == (
        tmp_path / "imports" / "job-history.xlsx"
    ).resolve()


def test_runtime_paths_preserve_absolute_paths(tmp_path: Path) -> None:
    database_path = tmp_path / "external" / "job_radar.sqlite3"
    reports_path = tmp_path / "external" / "reports"
    logs_path = tmp_path / "external" / "logs"
    profile_path = tmp_path / "external" / "profile.yaml"
    workbook_path = tmp_path / "external" / "job-history.xlsx"
    settings_path = tmp_path / "config" / "settings.yaml"

    _write_settings(
        settings_path,
        f"""
database_path: {database_path}
reports_path: {reports_path}
logs_path: {logs_path}
candidate_profile_path: {profile_path}
job_history_workbook_path: {workbook_path}

retention: {{}}
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
    assert runtime_paths.job_history_workbook_path == workbook_path.resolve()


def test_runtime_paths_allow_optional_profile_and_workbook_paths(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "config" / "settings.yaml"
    _write_settings(
        settings_path,
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs

retention: {}
""",
    )

    runtime_paths = RuntimePaths.from_settings(
        settings_path=settings_path,
        base_directory=tmp_path,
    )

    assert runtime_paths.candidate_profile_path is None
    assert runtime_paths.job_history_workbook_path is None


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

retention: {}
""",
    )

    runtime_paths = RuntimePaths.from_settings()

    assert runtime_paths.base_directory == tmp_path.resolve()
    assert runtime_paths.settings_path == settings_path.resolve()
    assert runtime_paths.database_path == (
        tmp_path / "data" / "job_radar.sqlite3"
    ).resolve()
