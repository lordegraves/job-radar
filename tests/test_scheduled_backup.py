"""Verify orchestrated backups use Junior's validated backup service."""

from pathlib import Path

from job_radar.scheduled_backup import run_scheduled_backup
from job_radar.storage import initialize_database


def test_scheduled_backup_creates_verified_bundle(tmp_path: Path) -> None:
    settings = tmp_path / "config/settings.yaml"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        "database_path: data/junior.sqlite3\n"
        "reports_path: reports\n"
        "logs_path: logs\n",
        encoding="utf-8",
    )
    initialize_database(tmp_path / "data/junior.sqlite3")

    backup = run_scheduled_backup(user_data_root=tmp_path)

    assert backup.is_file()
    assert backup.suffix == ".jrbackup"
    assert "scheduled" in backup.name


def test_scheduled_backup_retention_preserves_manual_bundles(tmp_path: Path) -> None:
    settings = tmp_path / "config/settings.yaml"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        "database_path: data/junior.sqlite3\n"
        "reports_path: reports\n"
        "logs_path: logs\n",
        encoding="utf-8",
    )
    initialize_database(tmp_path / "data/junior.sqlite3")
    backup_root = tmp_path / "data/backups/manual"
    backup_root.mkdir(parents=True)
    manual_backup = backup_root / "junior-manual-preserve.jrbackup"
    manual_backup.write_text("manual", encoding="utf-8")

    for _ in range(3):
        run_scheduled_backup(user_data_root=tmp_path, keep=2)

    assert manual_backup.read_text(encoding="utf-8") == "manual"
    assert len(list(backup_root.glob("junior-scheduled-*.jrbackup"))) == 2
