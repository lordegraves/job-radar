from pathlib import Path

import pytest

from job_radar.config import (
    ActiveProfileSettings,
    ApplicationSettings,
    ConfigError,
    EmailSettings,
    load_companies,
    load_settings,
)


def test_load_companies_returns_only_enabled_companies(tmp_path: Path) -> None:
    config_file = tmp_path / "companies.yaml"
    config_file.write_text(
        """
companies:
  - company_key: enabled_company
    name: Enabled Company
    source_type: greenhouse
    source_slug: enabled
    enabled: true

  - company_key: disabled_company
    name: Disabled Company
    source_type: lever
    source_slug: disabled
    enabled: false
""",
        encoding="utf-8",
    )

    companies = load_companies(config_file)

    assert len(companies) == 1
    assert companies[0]["company_key"] == "enabled_company"
    assert companies[0]["source_type"] == "greenhouse"


def test_load_companies_rejects_unsupported_source_type(tmp_path: Path) -> None:
    config_file = tmp_path / "companies.yaml"
    config_file.write_text(
        """
companies:
  - company_key: bad_company
    name: Bad Company
    source_type: unknown_ats
    source_url: https://example.com/careers
    enabled: true
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Unsupported source_type"):
        load_companies(config_file)


def test_load_settings_requires_retention_section(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    settings_file.write_text(
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="retention"):
        load_settings(settings_file)


@pytest.mark.parametrize(
    ("key", "yaml_value"),
    [
        ("database_path", "[data/job_radar.sqlite3]"),
        ("reports_path", "{path: reports}"),
        ("logs_path", "123"),
        ("candidate_profile_path", "[profiles/example/profile.yaml]"),
    ],
)
def test_load_settings_rejects_non_string_paths(
    tmp_path: Path,
    key: str,
    yaml_value: str,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    candidate_profile_line = (
        f"candidate_profile_path: {yaml_value}\n"
        if key == "candidate_profile_path"
        else ""
    )

    database_path = (
        yaml_value if key == "database_path" else "data/job_radar.sqlite3"
    )
    reports_path = yaml_value if key == "reports_path" else "reports"
    logs_path = yaml_value if key == "logs_path" else "logs"

    settings_file.write_text(
        f"""
database_path: {database_path}
reports_path: {reports_path}
logs_path: {logs_path}
{candidate_profile_line}retention: {{}}
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=rf"{key} must be a string"):
        load_settings(settings_file)


def test_load_settings_defaults_email_settings(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    settings_file.write_text(
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs

retention:
  report_retention_days: 90
  routine_event_retention_days: 90
  log_max_mb: 5
  log_backup_count: 5
  raw_capture_enabled: false
  raw_capture_retention_days: 7
""",
        encoding="utf-8",
    )

    settings = load_settings(settings_file)

    assert isinstance(settings, ApplicationSettings)
    assert settings.database_path == "data/job_radar.sqlite3"
    assert settings.reports_path == "reports"
    assert settings.logs_path == "logs"
    assert isinstance(settings.active_profile, ActiveProfileSettings)
    assert settings.active_profile.candidate_profile_path is None
    assert settings.candidate_profile_path is None
    assert isinstance(settings.email, EmailSettings)
    assert settings.email.enabled is False
    assert settings.email.sender == ""
    assert settings.email.sender_name == ""
    assert settings.email.recipients == ()
    assert settings.email.smtp_host == ""
    assert settings.email.smtp_port == 587
    assert settings.email.smtp_username == ""
    assert settings.email.smtp_password_env == ""
    assert settings.email.smtp_tls_mode == "starttls"

    # Mapping compatibility protects released callers during migration.
    assert settings["database_path"] == settings.database_path
    assert settings.get("candidate_profile_path") is None
    assert "candidate_profile_path" not in settings
    assert "job_history_workbook_path" not in settings
    assert settings["email"]["smtp_port"] == 587


def test_load_settings_exposes_active_profile_selection(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    profile_path = tmp_path / "profiles" / "example" / "profile.yaml"
    settings_file.write_text(
        f"""
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs
candidate_profile_path: {profile_path}

retention: {{}}
""",
        encoding="utf-8",
    )

    settings = load_settings(settings_file)

    assert settings.active_profile.candidate_profile_path == str(profile_path)
    assert settings.candidate_profile_path == str(profile_path)

    # Preserve the released flat YAML/mapping interface during migration.
    assert settings["candidate_profile_path"] == str(profile_path)


def test_load_settings_accepts_job_history_workbook_path(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    workbook_path = tmp_path / "job-history.xlsx"
    settings_file.write_text(
        f"""
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs
job_history_workbook_path: {workbook_path}

retention:
  report_retention_days: 90
  routine_event_retention_days: 90
  log_max_mb: 5
  log_backup_count: 5
  raw_capture_enabled: false
  raw_capture_retention_days: 7
""",
        encoding="utf-8",
    )

    settings = load_settings(settings_file)

    assert settings["job_history_workbook_path"] == str(workbook_path)
    assert settings.active_profile.candidate_profile_path is None


def test_load_settings_rejects_invalid_job_history_workbook_path(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    settings_file.write_text(
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs
job_history_workbook_path:
  - job-history.xlsx

retention:
  report_retention_days: 90
  routine_event_retention_days: 90
  log_max_mb: 5
  log_backup_count: 5
  raw_capture_enabled: false
  raw_capture_retention_days: 7
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="job_history_workbook_path must be a string"):
        load_settings(settings_file)


def test_load_settings_reads_email_settings(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    settings_file.write_text(
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs

retention:
  report_retention_days: 90
  routine_event_retention_days: 90
  log_max_mb: 5
  log_backup_count: 5
  raw_capture_enabled: false
  raw_capture_retention_days: 7

email:
  enabled: false
  sender: clayton@example.com
  sender_name: Job Radar
  recipients:
    - clayton@example.com
  smtp_host: smtp.example.com
  smtp_port: 587
""",
        encoding="utf-8",
    )

    settings = load_settings(settings_file)

    assert settings.email.enabled is False
    assert settings.email.sender == "clayton@example.com"
    assert settings.email.sender_name == "Job Radar"
    assert settings.email.recipients == ("clayton@example.com",)
    assert settings.email.smtp_host == "smtp.example.com"
    assert settings.email.smtp_port == 587
    assert settings.email.smtp_username == ""
    assert settings.email.smtp_password_env == ""
    assert settings.email.smtp_tls_mode == "starttls"


def test_load_settings_rejects_invalid_email_sender_name(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    settings_file.write_text(
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs

retention:
  report_retention_days: 90
  routine_event_retention_days: 90
  log_max_mb: 5
  log_backup_count: 5
  raw_capture_enabled: false
  raw_capture_retention_days: 7

email:
  enabled: false
  sender_name:
    - Job Radar
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="email.sender_name must be a string"):
        load_settings(settings_file)


def test_load_settings_rejects_invalid_email_recipients(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    settings_file.write_text(
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs

retention:
  report_retention_days: 90
  routine_event_retention_days: 90
  log_max_mb: 5
  log_backup_count: 5
  raw_capture_enabled: false
  raw_capture_retention_days: 7

email:
  enabled: false
  recipients: clayton@example.com
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="email.recipients must be a list"):
        load_settings(settings_file)


def test_load_settings_accepts_enabled_email_when_password_env_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("JOB_RADAR_SMTP_PASSWORD", "not-a-real-password")

    settings_file = tmp_path / "settings.yaml"
    settings_file.write_text(
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs

retention:
  report_retention_days: 90
  routine_event_retention_days: 90
  log_max_mb: 5
  log_backup_count: 5
  raw_capture_enabled: false
  raw_capture_retention_days: 7

email:
  enabled: true
  sender: clayton@example.com
  recipients:
    - clayton@example.com
  smtp_host: smtp.example.com
  smtp_port: 587
  smtp_username: clayton@example.com
  smtp_password_env: JOB_RADAR_SMTP_PASSWORD
  smtp_tls_mode: starttls
""",
        encoding="utf-8",
    )

    settings = load_settings(settings_file)

    assert settings["email"]["enabled"] is True
    assert settings["email"]["smtp_password_env"] == "JOB_RADAR_SMTP_PASSWORD"


def test_load_settings_accepts_enabled_email_without_password_env_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_file = tmp_path / "settings.yaml"
    monkeypatch.delenv("JOB_RADAR_SMTP_PASSWORD", raising=False)
    settings_file.write_text(
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs

retention:
  report_retention_days: 90
  routine_event_retention_days: 90
  log_max_mb: 5
  log_backup_count: 5
  raw_capture_enabled: false
  raw_capture_retention_days: 7

email:
  enabled: true
  sender: clayton@example.com
  recipients:
    - clayton@example.com
  smtp_host: smtp.example.com
  smtp_port: 587
  smtp_username: clayton@example.com
  smtp_password_env: JOB_RADAR_SMTP_PASSWORD
  smtp_tls_mode: starttls
""",
        encoding="utf-8",
    )

    settings = load_settings(settings_file)

    assert settings.email.enabled is True
    assert settings.email.smtp_password_env == "JOB_RADAR_SMTP_PASSWORD"


def test_load_settings_rejects_enabled_email_without_sender(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("JOB_RADAR_SMTP_PASSWORD", "not-a-real-password")

    settings_file = tmp_path / "settings.yaml"
    monkeypatch.delenv("JOB_RADAR_SMTP_PASSWORD", raising=False)
    settings_file.write_text(
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs

retention:
  report_retention_days: 90
  routine_event_retention_days: 90
  log_max_mb: 5
  log_backup_count: 5
  raw_capture_enabled: false
  raw_capture_retention_days: 7

email:
  enabled: true
  sender: ""
  recipients:
    - clayton@example.com
  smtp_host: smtp.example.com
  smtp_port: 587
  smtp_password_env: JOB_RADAR_SMTP_PASSWORD
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError,
        match="email.sender is required when email is enabled",
    ):
        load_settings(settings_file)

def test_load_settings_rejects_invalid_email_tls_mode(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yaml"
    settings_file.write_text(
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs

retention:
  report_retention_days: 90
  routine_event_retention_days: 90
  log_max_mb: 5
  log_backup_count: 5
  raw_capture_enabled: false
  raw_capture_retention_days: 7

email:
  enabled: false
  smtp_tls_mode: bad_tls_mode
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="smtp_tls_mode must be one of"):
        load_settings(settings_file)

def test_load_settings_rejects_enabled_email_without_smtp_username(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("JOB_RADAR_SMTP_PASSWORD", "not-a-real-password")

    settings_file = tmp_path / "settings.yaml"
    settings_file.write_text(
        """
database_path: data/job_radar.sqlite3
reports_path: reports
logs_path: logs

retention:
  report_retention_days: 90
  routine_event_retention_days: 90
  log_max_mb: 5
  log_backup_count: 5
  raw_capture_enabled: false
  raw_capture_retention_days: 7

email:
  enabled: true
  sender: clayton@example.com
  recipients:
    - clayton@example.com
  smtp_host: smtp.example.com
  smtp_port: 587
  smtp_username: ""
  smtp_password_env: JOB_RADAR_SMTP_PASSWORD
  smtp_tls_mode: starttls
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError,
        match="email.smtp_username is required when email is enabled",
    ):
        load_settings(settings_file)


def test_load_companies_allows_disabled_future_source_types(
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "companies.yaml"
    config_file.write_text(
        """
companies:
  - company_key: enabled_company
    name: Enabled Company
    source_type: greenhouse
    source_slug: enabled
    enabled: true

  - company_key: disabled_usajobs_company
    name: Disabled USAJobs Company
    source_type: usajobs
    source_slug: disabled-usajobs
    enabled: false
""",
        encoding="utf-8",
    )

    companies = load_companies(config_file)

    assert len(companies) == 1
    assert companies[0]["company_key"] == "enabled_company"