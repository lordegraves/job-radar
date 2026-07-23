"""Verify retention choices save atomically without discarding unrelated settings."""

from pathlib import Path

import pytest
import yaml

from job_radar.retention_settings_service import (
    RetentionSettingsError,
    load_retention_settings_form,
    save_retention_settings,
)


def write_settings(path: Path) -> None:
    path.write_text(
        """
database_path: data/test.sqlite3
reports_path: reports
logs_path: logs
unrelated_setting: preserve-me
retention:
  report_policy: latest_only
  report_count: 1
  log_policy: latest_plus_previous
  log_count: 2
  future_key: preserve-me-too
""",
        encoding="utf-8",
    )


def test_load_and_save_retention_preserves_unknown_settings(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    write_settings(settings_path)

    saved = save_retention_settings(
        settings_path,
        report_policy="keep_last_n",
        report_count_text="7",
        log_policy="latest_only",
        log_count_text="1",
    )
    data = yaml.safe_load(settings_path.read_text(encoding="utf-8"))

    assert saved.reports.mode == "keep_last_n"
    assert saved.reports.total_to_keep == 7
    assert data["unrelated_setting"] == "preserve-me"
    assert data["retention"]["future_key"] == "preserve-me-too"


def test_invalid_retention_choice_leaves_settings_unchanged(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    write_settings(settings_path)
    original = settings_path.read_bytes()

    with pytest.raises(RetentionSettingsError, match="supported"):
        save_retention_settings(
            settings_path,
            report_policy="forever",
            report_count_text="1",
            log_policy="latest_only",
            log_count_text="1",
        )

    assert settings_path.read_bytes() == original
    assert load_retention_settings_form(settings_path).reports.mode == "latest_only"
