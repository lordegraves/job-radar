"""Create, inspect, restore, and export bounded Junior user-data bundles."""

from dataclasses import dataclass
from datetime import UTC, datetime
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import BinaryIO
import zipfile

from job_radar import __version__
from job_radar.database import connect_database
from job_radar.runtime_paths import RuntimePaths


BACKUP_EXTENSION = ".jrbackup"
MAX_RESTORE_BYTES = 2_000_000_000
_MANIFEST_NAME = "manifest.json"
_BACKUP_ROOT = "data/backups/manual"
_RESTORED_DIRECTORIES = ("profiles", "resumes", "reports", "logs")


class BackupError(ValueError):
    """Explain why a backup, export, or restore could not safely continue."""


@dataclass(frozen=True)
class BackupRecord:
    name: str
    created_at: str
    size_bytes: int


@dataclass(frozen=True)
class BackupResult:
    path: Path
    file_count: int


def list_backups(runtime_paths: RuntimePaths) -> tuple[BackupRecord, ...]:
    root = _backup_directory(runtime_paths)
    if not root.is_dir():
        return ()
    return tuple(
        BackupRecord(
            name=path.name,
            created_at=datetime.fromtimestamp(path.stat().st_mtime).strftime(
                "%Y-%m-%d %I:%M %p"
            ),
            size_bytes=path.stat().st_size,
        )
        for path in sorted(
            root.glob(f"*{BACKUP_EXTENSION}"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if path.is_file()
    )


def create_backup(runtime_paths: RuntimePaths, *, reason: str = "manual") -> BackupResult:
    """Write a verified private bundle without changing the active workspace."""
    _validate_runtime_ownership(runtime_paths)
    backup_root = _backup_directory(runtime_paths)
    backup_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    destination = backup_root / f"junior-{reason}-{timestamp}{BACKUP_EXTENSION}"

    with tempfile.TemporaryDirectory(dir=backup_root) as temporary:
        staging = Path(temporary)
        _copy_runtime_data(runtime_paths, staging)
        files = _manifest_files(staging)
        manifest = {
            "format": "junior-backup",
            "format_version": 1,
            "application_version": __version__,
            "created_at": datetime.now(UTC).isoformat(),
            "reason": reason,
            "files": files,
        }
        (staging / _MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary_archive = destination.with_suffix(".tmp")
        try:
            with zipfile.ZipFile(
                temporary_archive,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                allowZip64=True,
            ) as archive:
                for path in sorted(staging.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(staging).as_posix())
            _validate_archive(temporary_archive)
            os.replace(temporary_archive, destination)
        finally:
            temporary_archive.unlink(missing_ok=True)

    return BackupResult(path=destination, file_count=len(files))


def create_export(runtime_paths: RuntimePaths) -> Path:
    """Create a readable JSON export without credentials or binary documents."""
    _validate_runtime_ownership(runtime_paths)
    export_root = runtime_paths.user_data_directory / "exports"
    export_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    destination = export_root / f"junior-export-{timestamp}.json"
    payload = {
        "format": "junior-readable-export",
        "format_version": 1,
        "application_version": __version__,
        "created_at": datetime.now(UTC).isoformat(),
        "notice": (
            "This readable export is not a restore bundle. Credentials and "
            "resume document contents are excluded."
        ),
        "database": _export_database(runtime_paths.database_path),
    }
    temporary = destination.with_suffix(".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def restore_backup(
    runtime_paths: RuntimePaths,
    upload: BinaryIO,
    *,
    confirmation: str,
) -> BackupResult:
    """Validate an uploaded bundle, preserve current data, then restore it."""
    if confirmation.strip() != "RESTORE":
        raise BackupError("Type RESTORE to confirm this recovery operation.")
    _validate_runtime_ownership(runtime_paths)
    backup_root = _backup_directory(runtime_paths)
    backup_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=backup_root) as temporary:
        staging_root = Path(temporary)
        upload_path = staging_root / f"uploaded{BACKUP_EXTENSION}"
        _copy_upload(upload, upload_path)
        manifest = _validate_archive(upload_path)
        extracted = staging_root / "extracted"
        _extract_archive(upload_path, extracted)
        restored_database = extracted / "data" / "database.sqlite3"
        if not restored_database.is_file():
            raise BackupError("The backup does not contain Junior's database.")
        _validate_restored_database(restored_database)

        # This independent bundle survives the restore and is the supported
        # way back if the user selected the wrong otherwise-valid backup.
        safety_backup = create_backup(runtime_paths, reason="pre-restore")
        try:
            _apply_restored_data(runtime_paths, extracted)
            _validate_restored_database(runtime_paths.database_path)
        except (OSError, BackupError) as error:
            rollback = staging_root / "rollback"
            _validate_archive(safety_backup.path)
            _extract_archive(safety_backup.path, rollback)
            _apply_restored_data(runtime_paths, rollback)
            raise BackupError(
                "Restore did not complete. Junior put the prior data back and "
                "kept the safety backup."
            ) from error
        return BackupResult(
            path=safety_backup.path,
            file_count=len(manifest["files"]),
        )


def _copy_runtime_data(runtime_paths: RuntimePaths, staging: Path) -> None:
    mappings = (
        (runtime_paths.settings_path, staging / "config" / "settings.yaml"),
        (runtime_paths.company_config_path, staging / "config" / "companies.yaml"),
        (runtime_paths.scoring_config_path, staging / "config" / "scoring.yaml"),
    )
    for source, destination in mappings:
        if source.is_file() and _is_owned(runtime_paths, source):
            _copy_file(source, destination)

    database_destination = staging / "data" / "database.sqlite3"
    database_destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect_database(runtime_paths.database_path)) as source:
        with closing(sqlite3.connect(database_destination)) as destination:
            source.backup(destination)

    root = runtime_paths.user_data_directory
    for name in _RESTORED_DIRECTORIES:
        source = root / name
        if source.is_dir():
            _copy_directory(source, staging / name)


def _manifest_files(staging: Path) -> list[dict[str, object]]:
    files: list[dict[str, object]] = []
    for path in sorted(staging.rglob("*")):
        if path.is_file():
            files.append(
                {
                    "path": path.relative_to(staging).as_posix(),
                    "size": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
    return files


def _validate_archive(path: Path) -> dict[str, object]:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if _MANIFEST_NAME not in names:
                raise BackupError("This is not a recognized Junior backup.")
            _validate_archive_names(names)
            if sum(item.file_size for item in archive.infolist()) > MAX_RESTORE_BYTES:
                raise BackupError("That backup is too large for this recovery screen.")
            manifest = json.loads(archive.read(_MANIFEST_NAME).decode("utf-8"))
            if (
                manifest.get("format") != "junior-backup"
                or manifest.get("format_version") != 1
                or not isinstance(manifest.get("files"), list)
            ):
                raise BackupError("This Junior backup format is not supported.")
            expected = {
                item["path"]: item
                for item in manifest["files"]
                if isinstance(item, dict) and isinstance(item.get("path"), str)
            }
            archived_files = {name for name in names if name != _MANIFEST_NAME}
            if archived_files != set(expected):
                raise BackupError("The backup contents do not match its manifest.")
            for name, item in expected.items():
                content = archive.read(name)
                if len(content) != item.get("size"):
                    raise BackupError("A backup file has an unexpected size.")
                if hashlib.sha256(content).hexdigest() != item.get("sha256"):
                    raise BackupError("A backup file failed integrity validation.")
            return manifest
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BackupError("Junior could not read this backup file.") from error


def _validate_archive_names(names: list[str]) -> None:
    allowed_roots = {"config", "data", "profiles", "resumes", "reports", "logs"}
    for name in names:
        normalized = Path(name)
        if (
            name.startswith(("/", "\\"))
            or ".." in normalized.parts
            or (name != _MANIFEST_NAME and normalized.parts[0] not in allowed_roots)
        ):
            raise BackupError("The backup contains an unsafe file path.")


def _extract_archive(path: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    for name in _RESTORED_DIRECTORIES:
        (destination / name).mkdir()
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name == _MANIFEST_NAME:
                continue
            target = destination / Path(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def _apply_restored_data(runtime_paths: RuntimePaths, extracted: Path) -> None:
    file_mappings = (
        (extracted / "config" / "settings.yaml", runtime_paths.settings_path),
        (extracted / "config" / "companies.yaml", runtime_paths.company_config_path),
        (extracted / "config" / "scoring.yaml", runtime_paths.scoring_config_path),
    )
    for source, destination in file_mappings:
        if source.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(f".{destination.name}.restore")
            _copy_file(source, temporary)
            os.replace(temporary, destination)

    restored_database = extracted / "data" / "database.sqlite3"
    if restored_database.is_file():
        # SQLite's own online-backup API safely replaces the database contents
        # even when the running Windows process has other short-lived handles.
        with closing(sqlite3.connect(restored_database)) as source:
            with closing(connect_database(runtime_paths.database_path)) as destination:
                source.backup(destination)

    root = runtime_paths.user_data_directory
    for name in _RESTORED_DIRECTORIES:
        source = extracted / name
        destination = root / name
        replacement = root / f".{name}-restore"
        if replacement.exists():
            shutil.rmtree(replacement)
        _copy_directory(source, replacement)
        previous = root / f".{name}-before-restore"
        if previous.exists():
            shutil.rmtree(previous)
        if destination.exists():
            os.replace(destination, previous)
        os.replace(replacement, destination)
        shutil.rmtree(previous, ignore_errors=True)


def _validate_restored_database(path: Path) -> None:
    try:
        with closing(sqlite3.connect(path)) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.Error as error:
        raise BackupError("The restored database could not be validated.") from error
    if result != ("ok",):
        raise BackupError("The restored database failed its integrity check.")


def _copy_upload(upload: BinaryIO, destination: Path) -> None:
    total = 0
    with destination.open("wb") as output:
        while chunk := upload.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_RESTORE_BYTES:
                raise BackupError("That backup is too large for this recovery screen.")
            output.write(chunk)
    if total == 0:
        raise BackupError("Choose a Junior backup file to restore.")


def _export_database(database_path: Path) -> dict[str, list[dict[str, object]]]:
    exported: dict[str, list[dict[str, object]]] = {}
    with closing(connect_database(database_path)) as connection:
        tables = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
        for table_row in tables:
            table = str(table_row[0])
            quoted = table.replace('"', '""')
            cursor = connection.execute(f'SELECT * FROM "{quoted}"')
            columns = tuple(item[0] for item in cursor.description or ())
            rows = cursor.fetchall()
            exported[table] = [
                {
                    key: _json_value(value)
                    for key, value in zip(columns, row, strict=True)
                }
                for row in rows
            ]
    return exported


def _json_value(value: object) -> object:
    if isinstance(value, bytes):
        return {"binary_sha256": hashlib.sha256(value).hexdigest(), "bytes": len(value)}
    return value


def _validate_runtime_ownership(runtime_paths: RuntimePaths) -> None:
    root = runtime_paths.user_data_directory.resolve()
    required = (
        runtime_paths.settings_path,
        runtime_paths.database_path,
    )
    for path in required:
        resolved = path.resolve()
        if resolved != root and root not in resolved.parents:
            raise BackupError(
                "Junior cannot manage recovery because an active data path is "
                "outside the configured user-data directory."
            )


def _backup_directory(runtime_paths: RuntimePaths) -> Path:
    return runtime_paths.user_data_directory / Path(_BACKUP_ROOT)


def _is_owned(runtime_paths: RuntimePaths, path: Path) -> bool:
    root = runtime_paths.user_data_directory.resolve()
    resolved = path.resolve()
    return resolved == root or root in resolved.parents


def _copy_file(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise BackupError("Junior will not follow linked files during backup.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _copy_directory(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        if path.is_symlink():
            raise BackupError("Junior will not follow linked files during backup.")
        if path.is_file():
            _copy_file(path, destination / path.relative_to(source))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
