"""Verify USAJOBS secrets remain in keyring and settings stay non-secret."""

from pathlib import Path

import pytest

from job_radar.config import load_settings
from job_radar.usajobs_settings_service import (
    UsaJobsSettingsError,
    load_usajobs_settings_form,
    remove_usajobs_settings,
    save_usajobs_settings,
)


def _write_settings(path: Path) -> None:
    path.write_text(
        "database_path: data/test.sqlite3\nreports_path: reports\nlogs_path: logs\n",
        encoding="utf-8",
    )


def test_save_keeps_authorization_key_only_in_credential_manager(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "settings.yaml"
    _write_settings(path)
    stored = {}
    monkeypatch.setattr(
        "job_radar.usajobs_settings_service.get_credential",
        lambda reference: stored.get(reference),
    )
    monkeypatch.setattr(
        "job_radar.usajobs_settings_service.store_credential",
        lambda reference, secret: stored.__setitem__(reference, secret),
    )

    form = save_usajobs_settings(
        path,
        contact_email="tester@example.com",
        authorization_key="private-key",
    )

    assert form.credential_saved is True
    assert stored == {"usajobs:authorization-key": "private-key"}
    assert "private-key" not in path.read_text(encoding="utf-8")
    settings = load_settings(path).usajobs
    assert settings.contact_email == "tester@example.com"
    assert settings.credential_key == "usajobs:authorization-key"


def test_remove_clears_reference_and_keyring_entry(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "settings.yaml"
    _write_settings(path)
    stored = {"usajobs:authorization-key": "private-key"}
    monkeypatch.setattr(
        "job_radar.usajobs_settings_service.get_credential",
        lambda reference: stored.get(reference),
    )
    monkeypatch.setattr(
        "job_radar.usajobs_settings_service.store_credential",
        lambda reference, secret: stored.__setitem__(reference, secret),
    )
    monkeypatch.setattr(
        "job_radar.usajobs_settings_service.delete_credential",
        lambda reference: stored.pop(reference, None) is not None,
    )
    save_usajobs_settings(
        path,
        contact_email="tester@example.com",
        authorization_key="private-key",
    )

    form = remove_usajobs_settings(path)

    assert form == load_usajobs_settings_form(path)
    assert form.contact_email == ""
    assert form.credential_saved is False
    assert stored == {}


def test_remove_restores_key_when_settings_replace_fails(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "settings.yaml"
    _write_settings(path)
    stored = {"usajobs:authorization-key": "private-key"}
    monkeypatch.setattr(
        "job_radar.usajobs_settings_service.get_credential",
        lambda reference: stored.get(reference),
    )
    monkeypatch.setattr(
        "job_radar.usajobs_settings_service.store_credential",
        lambda reference, secret: stored.__setitem__(reference, secret),
    )
    monkeypatch.setattr(
        "job_radar.usajobs_settings_service.delete_credential",
        lambda reference: stored.pop(reference, None) is not None,
    )
    save_usajobs_settings(
        path,
        contact_email="tester@example.com",
        authorization_key="private-key",
    )
    original = path.read_text(encoding="utf-8")
    monkeypatch.setattr(
        "job_radar.usajobs_settings_service.os.replace",
        lambda source, destination: (_ for _ in ()).throw(OSError("blocked")),
    )

    with pytest.raises(UsaJobsSettingsError, match="could not remove"):
        remove_usajobs_settings(path)

    assert stored == {"usajobs:authorization-key": "private-key"}
    assert path.read_text(encoding="utf-8") == original


def test_api_test_sends_saved_identity_without_exposing_key(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "settings.yaml"
    _write_settings(path)
    stored = {"usajobs:authorization-key": "private-key"}
    monkeypatch.setattr(
        "job_radar.usajobs_settings_service.get_credential",
        lambda reference: stored.get(reference),
    )
    monkeypatch.setattr(
        "job_radar.usajobs_settings_service.store_credential",
        lambda reference, secret: stored.__setitem__(reference, secret),
    )
    save_usajobs_settings(
        path,
        contact_email="tester@example.com",
        authorization_key="private-key",
    )
    captured = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"SearchResult": {}}

    def fake_get(url, *, headers, params, timeout):
        captured.update(url=url, headers=headers, params=params, timeout=timeout)
        return Response()

    monkeypatch.setattr("job_radar.usajobs_settings_service.requests.get", fake_get)

    from job_radar.usajobs_settings_service import test_usajobs_settings

    assert test_usajobs_settings(path) == "USAJOBS API access is working."
    assert captured["headers"] == {
        "Host": "data.usajobs.gov",
        "User-Agent": "tester@example.com",
        "Authorization-Key": "private-key",
    }
    assert "private-key" not in path.read_text(encoding="utf-8")
