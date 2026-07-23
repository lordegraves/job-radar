"""Verify Administration access and session signing stay local and bounded."""

from pathlib import Path

from job_radar.admin_access import safe_local_path
from job_radar.session_secret import (
    SESSION_SECRET_BYTES,
    SESSION_SECRET_FILE_NAME,
    load_or_create_session_secret,
)


def test_safe_local_path_accepts_only_local_absolute_paths() -> None:
    assert safe_local_path("/administration") == "/administration"
    assert safe_local_path("/settings?section=email") == (
        "/settings?section=email"
    )
    assert safe_local_path("https://example.invalid") is None
    assert safe_local_path("//example.invalid/path") is None
    assert safe_local_path("/\\example.invalid/path") is None
    assert safe_local_path("/%2F%2Fexample.invalid/path") is None
    assert safe_local_path("settings") is None
    assert safe_local_path(None) is None


def test_session_secret_is_installation_local_and_stable(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "junior.sqlite3"

    first_secret = load_or_create_session_secret(database_path)
    second_secret = load_or_create_session_secret(database_path)
    secret_path = (
        database_path.parent / "runtime" / SESSION_SECRET_FILE_NAME
    )

    assert first_secret == second_secret
    assert len(first_secret) == SESSION_SECRET_BYTES
    assert secret_path.read_bytes() == first_secret
    assert secret_path.parent == tmp_path / "data" / "runtime"
