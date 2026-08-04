from pathlib import Path

import pytest

from job_radar.config import load_settings
from job_radar.llm_settings_service import LlmSettingsError, save_llm_settings


def write_settings(path: Path) -> None:
    path.write_text(
        "database_path: data/db.sqlite3\n"
        "reports_path: reports\n"
        "logs_path: logs\n",
        encoding="utf-8",
    )


def test_llm_defaults_off(tmp_path) -> None:
    settings_path = tmp_path / "settings.yaml"
    write_settings(settings_path)
    settings = load_settings(settings_path)

    assert settings.llm.enabled is False
    assert settings.llm.provider == "openai"


def test_enabling_requires_privacy_acknowledgement(tmp_path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.yaml"
    write_settings(settings_path)
    monkeypatch.setattr(
        "job_radar.llm_settings_service.get_credential",
        lambda _reference: None,
    )

    with pytest.raises(LlmSettingsError, match="privacy warning"):
        save_llm_settings(
            settings_path,
            enabled=True,
            provider="openai",
            model="gpt-test",
            privacy_acknowledged=False,
            max_reviews_per_scan=10,
            credential="test-key",
        )


def test_api_key_is_stored_only_in_credential_manager(tmp_path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.yaml"
    write_settings(settings_path)
    stored = {}
    monkeypatch.setattr(
        "job_radar.llm_settings_service.get_credential",
        lambda reference: stored.get(reference),
    )
    monkeypatch.setattr(
        "job_radar.llm_settings_service.store_credential",
        lambda reference, value: stored.__setitem__(reference, value),
    )

    form = save_llm_settings(
        settings_path,
        enabled=True,
        provider="openai",
        model="gpt-test",
        privacy_acknowledged=True,
        max_reviews_per_scan=10,
        credential="test-key",
    )

    assert form.enabled is True
    assert form.credential_saved is True
    assert "test-key" not in settings_path.read_text(encoding="utf-8")
    assert load_settings(settings_path).llm.credential_key == "llm:openai:api-key"
