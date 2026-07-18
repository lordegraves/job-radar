from pathlib import Path

from job_radar.validation import validate_configuration


def _write_valid_workspace(root: Path) -> dict[str, Path]:
    config_directory = root / "config"
    profile_directory = root / "profiles" / "example"

    config_directory.mkdir(parents=True)
    profile_directory.mkdir(parents=True)

    settings_path = config_directory / "settings.yaml"
    companies_path = config_directory / "target-companies.yaml"
    scoring_path = config_directory / "scoring.yaml"
    profile_path = profile_directory / "profile.yaml"
    resume_path = profile_directory / "resume.md"

    settings_path.write_text(
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs
candidate_profile_path: profiles/example/profile.yaml

email:
  enabled: false
  sender: ""
  sender_name: "Job Radar"
  recipients: []
  smtp_host: ""
  smtp_port: 587
  smtp_username: ""
  smtp_password_env: ""
  smtp_tls_mode: "starttls"
""".lstrip(),
        encoding="utf-8",
    )

    companies_path.write_text(
        """
companies:
  - company_key: example_ai
    name: Example AI
    source_type: greenhouse
    source_slug: exampleai
    enabled: true
""".lstrip(),
        encoding="utf-8",
    )

    scoring_path.write_text(
        """
positive_keywords:
  infrastructure: 10

negative_keywords:
  sales: -15

location_preferences:
  allowed:
    remote: 100
  conditional: {}
  skipped: {}

top_matches:
  min_score: 120
  excluded_title_keywords:
    - sales
  strong_signals:
    - title:infrastructure

review_needed:
  min_score: 100
  excluded_location_statuses:
    - skipped
    - unknown
  strong_signals:
    - title:infrastructure
""".lstrip(),
        encoding="utf-8",
    )

    profile_path.write_text(
        """
candidate:
  name: Example Candidate
  resume:
    source_path: profiles/example/resume.md
    normalized_text_path: profiles/example/resume.normalized.txt
""".lstrip(),
        encoding="utf-8",
    )

    resume_path.write_text(
        "# Example Candidate\n\nInfrastructure engineer.\n",
        encoding="utf-8",
    )

    return {
        "settings": settings_path,
        "companies": companies_path,
        "scoring": scoring_path,
        "profile": profile_path,
        "resume": resume_path,
    }


def test_validate_configuration_resolves_workspace_paths_outside_current_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "user-data"
    unrelated_directory = tmp_path / "unrelated"
    paths = _write_valid_workspace(workspace)
    unrelated_directory.mkdir()

    monkeypatch.chdir(unrelated_directory)

    result = validate_configuration(
        config_path=str(paths["companies"]),
        settings_path=str(paths["settings"]),
        scoring_path=str(paths["scoring"]),
    )

    assert result.passed is True
    assert f"company config loaded: {paths['companies'].resolve()}" in result.checks
    assert f"settings loaded: {paths['settings'].resolve()}" in result.checks
    assert f"scoring config loaded: {paths['scoring'].resolve()}" in result.checks
    assert (
        f"database path writable: {(workspace / 'data/job_radar.sqlite3').resolve()}"
        in result.checks
    )
    assert f"reports path writable: {(workspace / 'reports').resolve()}" in result.checks
    assert f"logs path writable: {(workspace / 'logs').resolve()}" in result.checks
    assert f"candidate profile loaded: {paths['profile'].resolve()}" in result.checks
    assert f"resume loaded: {paths['resume'].resolve()}" in result.checks
    assert (
        "normalized resume output path writable: "
        f"{(workspace / 'profiles/example/resume.normalized.txt').resolve()}"
        in result.checks
    )


def test_validate_configuration_resolves_non_config_settings_from_parent_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "standalone-workspace"
    unrelated_directory = tmp_path / "unrelated"
    paths = _write_valid_workspace(workspace)
    standalone_settings = workspace / "settings.yaml"
    paths["settings"].replace(standalone_settings)
    unrelated_directory.mkdir()

    monkeypatch.chdir(unrelated_directory)

    result = validate_configuration(
        config_path=str(paths["companies"]),
        settings_path=str(standalone_settings),
        scoring_path=str(paths["scoring"]),
    )

    assert result.passed is True
    assert f"settings loaded: {standalone_settings.resolve()}" in result.checks
    assert f"candidate profile loaded: {paths['profile'].resolve()}" in result.checks