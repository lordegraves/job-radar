from pathlib import Path

import pytest

from job_radar.config import ConfigError, load_companies, load_settings


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