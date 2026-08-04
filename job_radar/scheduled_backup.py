"""Create a verified Junior backup for schedulers and orchestrators."""

import argparse
from pathlib import Path

from job_radar.backup_service import create_backup
from job_radar.runtime_paths import RuntimePaths, UserDataPaths


DEFAULT_SCHEDULED_BACKUPS_TO_KEEP = 14


def run_scheduled_backup(
    *,
    user_data_root: str | Path | None = None,
    keep: int = DEFAULT_SCHEDULED_BACKUPS_TO_KEEP,
) -> Path:
    """Create one backup through the same verified service used by the GUI."""

    if keep < 1:
        raise ValueError("scheduled backup retention must keep at least one backup")
    paths = (
        UserDataPaths.from_root(user_data_root)
        if user_data_root is not None
        else UserDataPaths.default()
    )
    runtime_paths = RuntimePaths.from_settings(
        paths.config / "settings.yaml",
        base_directory=paths.root,
    )
    backup_path = create_backup(runtime_paths, reason="scheduled").path
    scheduled_backups = sorted(
        backup_path.parent.glob("junior-scheduled-*.jrbackup"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    # Retention removes only older scheduler-owned bundles after a new verified
    # backup exists. Manual and pre-change safety backups are never included.
    for expired_backup in scheduled_backups[keep:]:
        expired_backup.unlink()
    return backup_path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="junior-backup",
        description="Create a verified backup in Junior's user-data directory",
    )
    parser.add_argument(
        "--user-data-root",
        default=None,
        help="Optional explicit Junior user-data root",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=DEFAULT_SCHEDULED_BACKUPS_TO_KEEP,
        help="Number of verified scheduled backups to retain (default: 14)",
    )
    args = parser.parse_args()
    path = run_scheduled_backup(user_data_root=args.user_data_root, keep=args.keep)
    print(f"Verified Junior backup created: {path}")


if __name__ == "__main__":
    main()
