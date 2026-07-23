"""Run one saved scheduled scan through Junior's shared scan service."""

import argparse
from pathlib import Path

from job_radar.runtime_paths import (
    DEFAULT_EMAIL_PREVIEW_PATH,
    DEFAULT_REPORT_PATH,
    RuntimePaths,
    UserDataPaths,
)
from job_radar.scan_service import handle_scan
from job_radar.schedule_service import load_scan_schedule


def run_saved_schedule(
    *,
    user_data_root: str | Path | None = None,
) -> bool:
    """Run the saved schedule, or exit safely when scheduling is off."""
    user_data_paths = (
        UserDataPaths.from_root(user_data_root)
        if user_data_root is not None
        else UserDataPaths.default()
    )
    settings_path = user_data_paths.config / "settings.yaml"
    runtime_paths = RuntimePaths.from_settings(
        settings_path,
        base_directory=user_data_paths.root,
    )
    schedule = load_scan_schedule(runtime_paths.database_path)
    if not schedule.enabled:
        return False

    handle_scan(
        config_path=str(runtime_paths.company_config_path),
        settings_path=str(runtime_paths.settings_path),
        report_path=str(runtime_paths.resolve(DEFAULT_REPORT_PATH)),
        scoring_path=str(runtime_paths.scoring_config_path),
        email_preview_path=str(
            runtime_paths.resolve(DEFAULT_EMAIL_PREVIEW_PATH)
        ),
        send_email=schedule.email_delivery,
        base_directory=str(runtime_paths.base_directory),
        trigger_source="scheduled",
    )
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="job-radar-scheduled",
        description="Run Junior's saved scan schedule",
    )
    parser.add_argument(
        "--user-data-root",
        default=None,
        help="Optional explicit user-data root for testing or server operation",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    ran = run_saved_schedule(user_data_root=args.user_data_root)
    if not ran:
        print("Scheduled scans are turned off. No scan was run.")


if __name__ == "__main__":
    main()
