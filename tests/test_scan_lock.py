import json
import os
import socket
from pathlib import Path

import pytest

from job_radar.scan_lock import (
    ScanAlreadyRunningError,
    acquire_scan_lock,
    build_scan_lock_path,
)


def test_acquire_scan_lock_prevents_concurrent_owner(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    lock_path = build_scan_lock_path(database_path)

    with acquire_scan_lock(database_path):
        assert lock_path.is_file()

        with pytest.raises(
            ScanAlreadyRunningError,
            match="already running",
        ):
            with acquire_scan_lock(database_path):
                raise AssertionError("Concurrent lock should not be acquired.")

    assert not lock_path.exists()


def test_acquire_scan_lock_removes_stale_lock(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    lock_path = build_scan_lock_path(database_path)

    lock_path.write_text(
        json.dumps(
            {
                "process_id": 999_999_999,
                "hostname": socket.gethostname(),
                "created_at": "2026-07-15T12:00:00+00:00",
                "ownership_token": "stale-token",
            }
        ),
        encoding="utf-8",
    )

    with acquire_scan_lock(database_path):
        metadata = json.loads(lock_path.read_text(encoding="utf-8"))

        assert metadata["process_id"] == os.getpid()
        assert metadata["ownership_token"] != "stale-token"

    assert not lock_path.exists()


def test_acquire_scan_lock_preserves_unreadable_existing_lock(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    lock_path = build_scan_lock_path(database_path)

    lock_path.write_text("not valid json", encoding="utf-8")

    with pytest.raises(
        ScanAlreadyRunningError,
        match="already running",
    ):
        with acquire_scan_lock(database_path):
            raise AssertionError("Invalid existing lock should remain busy.")

    assert lock_path.read_text(encoding="utf-8") == "not valid json"


def test_acquire_scan_lock_preserves_lock_from_another_host(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    lock_path = build_scan_lock_path(database_path)

    lock_path.write_text(
        json.dumps(
            {
                "process_id": 999_999_999,
                "hostname": "another-host",
                "created_at": "2026-07-15T12:00:00+00:00",
                "ownership_token": "remote-token",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ScanAlreadyRunningError,
        match="already running",
    ):
        with acquire_scan_lock(database_path):
            raise AssertionError("Foreign-host lock should remain busy.")

    metadata = json.loads(lock_path.read_text(encoding="utf-8"))

    assert metadata["ownership_token"] == "remote-token"


def test_acquire_scan_lock_releases_after_failure(tmp_path: Path) -> None:
    database_path = tmp_path / "job_radar.sqlite3"
    lock_path = build_scan_lock_path(database_path)

    with pytest.raises(RuntimeError, match="scan failed"):
        with acquire_scan_lock(database_path):
            raise RuntimeError("scan failed")

    assert not lock_path.exists()
