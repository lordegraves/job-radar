import json
import os
import socket
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator
from uuid import uuid4


class ScanAlreadyRunningError(RuntimeError):
    """Raised when another Job Radar process already owns the scan lock."""


def build_scan_lock_path(database_path: str | Path) -> Path:
    path = Path(database_path)
    return path.with_name(f"{path.name}.scan.lock")


def _process_is_running(process_id: int) -> bool:
    if process_id <= 0:
        return False

    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information,
            False,
            process_id,
        )

        if not handle:
            error_code = ctypes.get_last_error()

            if error_code == 5:
                return True

            return False

        ctypes.windll.kernel32.CloseHandle(handle)
        return True

    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False

    return True


def _read_lock_metadata(lock_path: Path) -> dict | None:
    try:
        raw_text = lock_path.read_text(encoding="utf-8")
        metadata = json.loads(raw_text)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(metadata, dict):
        return None

    return metadata


def _remove_stale_lock(lock_path: Path) -> bool:
    metadata = _read_lock_metadata(lock_path)

    if metadata is None:
        return False

    process_id = metadata.get("process_id")
    hostname = metadata.get("hostname")

    if not isinstance(process_id, int):
        return False

    if hostname != socket.gethostname():
        return False

    if _process_is_running(process_id):
        return False

    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        return False

    return True


def _create_lock_file(lock_path: Path, ownership_token: str) -> None:
    metadata = {
        "process_id": os.getpid(),
        "hostname": socket.gethostname(),
        "created_at": datetime.now(UTC).isoformat(),
        "ownership_token": ownership_token,
    }
    encoded_metadata = json.dumps(metadata, indent=2).encode("utf-8")

    descriptor = os.open(
        lock_path,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
    )

    try:
        os.write(descriptor, encoded_metadata)
    finally:
        os.close(descriptor)


def _release_lock_file(lock_path: Path, ownership_token: str) -> None:
    metadata = _read_lock_metadata(lock_path)

    if metadata is None:
        return

    if metadata.get("ownership_token") != ownership_token:
        return

    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


@contextmanager
def acquire_scan_lock(database_path: str | Path) -> Iterator[Path]:
    lock_path = build_scan_lock_path(database_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    ownership_token = uuid4().hex

    try:
        _create_lock_file(lock_path, ownership_token)
    except FileExistsError:
        if not _remove_stale_lock(lock_path):
            raise ScanAlreadyRunningError(
                "Another Job Radar scan is already running."
            ) from None

        try:
            _create_lock_file(lock_path, ownership_token)
        except FileExistsError:
            raise ScanAlreadyRunningError(
                "Another Job Radar scan is already running."
            ) from None

    try:
        yield lock_path
    finally:
        _release_lock_file(lock_path, ownership_token)
