"""Verify external company-lookup consent is validated and saved atomically."""

from pathlib import Path

import pytest
import yaml

from job_radar.company_discovery_settings_service import (
    CompanyDiscoverySettingsError,
    load_company_discovery_settings_form,
    save_company_discovery_settings,
)


def write_settings(path: Path) -> None:
    path.write_text(
        """
database_path: data/junior.sqlite3
reports_path: reports
logs_path: logs
unrelated_setting: preserved
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_external_lookup_defaults_off_and_preserves_unrelated_settings(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    write_settings(settings_path)

    assert (
        load_company_discovery_settings_form(
            settings_path
        ).external_lookup_enabled
        is False
    )

    saved = save_company_discovery_settings(
        settings_path,
        external_lookup_enabled=True,
    )
    stored = yaml.safe_load(settings_path.read_text(encoding="utf-8"))

    assert saved.external_lookup_enabled is True
    assert stored["company_discovery"]["external_lookup"] is True
    assert stored["unrelated_setting"] == "preserved"


def test_invalid_external_lookup_choice_does_not_change_settings(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    write_settings(settings_path)
    before = settings_path.read_bytes()

    with pytest.raises(CompanyDiscoverySettingsError):
        save_company_discovery_settings(
            settings_path,
            external_lookup_enabled="not-a-boolean",
        )

    assert settings_path.read_bytes() == before
