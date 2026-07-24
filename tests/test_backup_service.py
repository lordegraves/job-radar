"""Test private backups, readable exports, and guarded restore with fake data."""

from io import BytesIO
import json
from pathlib import Path
import zipfile
from contextlib import closing

import pytest

from job_radar.backup_service import (
    BackupError,
    create_backup,
    create_export,
    list_backups,
    restore_backup,
)
from job_radar.database import connect_database
from job_radar.runtime_paths import RuntimePaths
from job_radar.storage import initialize_database


def _runtime(tmp_path: Path) -> RuntimePaths:
    settings = tmp_path / "config" / "settings.yaml"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        """
database_path: data/junior.sqlite3
reports_path: reports
logs_path: logs
""",
        encoding="utf-8",
    )
    (tmp_path / "config" / "target-companies.yaml").write_text(
        "companies: []\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "scoring.yaml").write_text(
        "scoring: {}\n",
        encoding="utf-8",
    )
    runtime = RuntimePaths.from_settings(
        settings,
        base_directory=tmp_path,
    )
    initialize_database(runtime.database_path)
    return runtime


def _marker(runtime: RuntimePaths) -> str:
    with closing(connect_database(runtime.database_path)) as connection:
        return str(
            connection.execute(
                "SELECT value FROM backup_test WHERE key = 'backup-test'"
            ).fetchone()[0]
        )


def test_backup_and_restore_preserve_complete_fake_workspace(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    (tmp_path / "resumes" / "fake-profile").mkdir(parents=True)
    (tmp_path / "resumes" / "fake-profile" / "resume.txt").write_text(
        "Invented resume",
        encoding="utf-8",
    )
    with closing(connect_database(runtime.database_path)) as connection:
        connection.execute(
            "CREATE TABLE backup_test (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO backup_test (key, value) VALUES ('backup-test', 'before')"
        )
        connection.commit()

    backup = create_backup(runtime)
    with closing(connect_database(runtime.database_path)) as connection:
        connection.execute(
            "UPDATE backup_test SET value = 'after' WHERE key = 'backup-test'"
        )
        connection.commit()
    (tmp_path / "resumes" / "fake-profile" / "resume.txt").write_text(
        "Changed invented resume",
        encoding="utf-8",
    )
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "created-after-backup.html").write_text(
        "Not part of the restored state",
        encoding="utf-8",
    )

    result = restore_backup(
        runtime,
        BytesIO(backup.path.read_bytes()),
        confirmation="RESTORE",
    )

    assert _marker(runtime) == "before"
    assert (tmp_path / "resumes" / "fake-profile" / "resume.txt").read_text(
        encoding="utf-8"
    ) == "Invented resume"
    assert not (tmp_path / "reports" / "created-after-backup.html").exists()
    assert "pre-restore" in result.path.name
    assert len(list_backups(runtime)) == 2


def test_backup_migrates_data_into_a_separate_clean_workspace(
    tmp_path: Path,
) -> None:
    development = _runtime(tmp_path / "development")
    installed = _runtime(tmp_path / "installed")
    (development.user_data_directory / "resumes" / "test-profile").mkdir(
        parents=True
    )
    development_resume = (
        development.user_data_directory
        / "resumes"
        / "test-profile"
        / "resume.txt"
    )
    development_resume.write_text("Fictional resume", encoding="utf-8")
    with closing(connect_database(development.database_path)) as connection:
        connection.execute(
            "CREATE TABLE backup_test (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO backup_test (key, value) VALUES ('backup-test', 'source')"
        )
        connection.commit()

    backup = create_backup(development)
    restore_backup(
        installed,
        BytesIO(backup.path.read_bytes()),
        confirmation="RESTORE",
    )

    assert _marker(installed) == "source"
    installed_resume = (
        installed.user_data_directory
        / "resumes"
        / "test-profile"
        / "resume.txt"
    )
    assert installed_resume.read_text(encoding="utf-8") == "Fictional resume"
    assert development_resume.read_text(encoding="utf-8") == "Fictional resume"
    assert backup.path.is_file()


def test_restore_rejects_wrong_confirmation_and_tampered_bundle(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    backup = create_backup(runtime)

    with pytest.raises(BackupError, match="Type RESTORE"):
        restore_backup(runtime, BytesIO(backup.path.read_bytes()), confirmation="")

    tampered = BytesIO()
    with zipfile.ZipFile(tampered, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": "junior-backup",
                    "format_version": 1,
                    "files": [
                        {"path": "../outside.txt", "size": 1, "sha256": "bad"}
                    ],
                }
            ),
        )
        archive.writestr("../outside.txt", "x")
    tampered.seek(0)
    with pytest.raises(BackupError, match="unsafe file path"):
        restore_backup(runtime, tampered, confirmation="RESTORE")


def test_readable_export_excludes_resume_and_contains_database_rows(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    (tmp_path / "resumes").mkdir()
    (tmp_path / "resumes" / "private.txt").write_text(
        "Do not export this text",
        encoding="utf-8",
    )

    export_path = create_export(runtime)
    exported = json.loads(export_path.read_text(encoding="utf-8"))

    assert exported["format"] == "junior-readable-export"
    assert "schema_migrations" in exported["database"]
    assert "Do not export this text" not in export_path.read_text(encoding="utf-8")
