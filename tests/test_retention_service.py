"""Verify retention preserves complete reports and deletes only Junior-owned history."""

from pathlib import Path

from job_radar.config import RetentionPolicySettings, RetentionSettings
from job_radar.retention_service import (
    ARCHIVE_MARKER_NAME,
    apply_retention_after_report_write,
    archive_before_report_write,
    list_retained_report_runs,
)


def policy(mode: str, count: int = 1) -> RetentionPolicySettings:
    return RetentionPolicySettings(mode=mode, count=count)


def run_retention(
    reports: Path,
    logs: Path,
    *,
    report_policy: RetentionPolicySettings,
    log_policy: RetentionPolicySettings | None = None,
) -> None:
    archive_before_report_write(
        html_report_path=reports / "target-scan.html",
        snapshot_path=reports / "target-scan.json",
        email_preview_path=reports / "target-email-preview.txt",
    )
    apply_retention_after_report_write(
        reports_path=reports,
        logs_path=logs,
        retention=RetentionSettings(
            reports=report_policy,
            logs=log_policy or policy("latest_only"),
        ),
    )


def write_current_reports(reports: Path, value: str) -> None:
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "target-scan.html").write_text(value, encoding="utf-8")
    (reports / "target-scan.json").write_text(
        f'{{"run": "{value}"}}', encoding="utf-8"
    )
    (reports / "target-email-preview.txt").write_text(value, encoding="utf-8")


def test_retention_archives_previous_complete_report_set(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    logs = tmp_path / "logs"
    write_current_reports(reports, "first run")

    run_retention(
        reports,
        logs,
        report_policy=policy("latest_plus_previous"),
    )

    runs = list_retained_report_runs(reports)
    assert len(runs) == 1
    archive = reports / "archive" / runs[0].archive_name
    assert (archive / ARCHIVE_MARKER_NAME).is_file()
    assert (archive / "target-scan.html").read_text(
        encoding="utf-8"
    ) == "first run"
    assert (archive / "target-scan.json").is_file()
    assert (archive / "target-email-preview.txt").is_file()


def test_retention_prunes_old_archives_but_leaves_unknown_files(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    logs = tmp_path / "logs"
    unknown_directory = reports / "archive" / "personal-notes"
    unknown_directory.mkdir(parents=True)
    (unknown_directory / "notes.txt").write_text("keep", encoding="utf-8")

    for value in ("one", "two", "three"):
        write_current_reports(reports, value)
        run_retention(
            reports,
            logs,
            report_policy=policy("latest_plus_previous"),
        )

    assert len(list_retained_report_runs(reports)) == 1
    assert (unknown_directory / "notes.txt").read_text(
        encoding="utf-8"
    ) == "keep"


def test_latest_only_removes_owned_archives_without_archiving_current(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    logs = tmp_path / "logs"
    write_current_reports(reports, "current")
    owned_archive = reports / "archive" / "scan-20260723T120000000000Z"
    owned_archive.mkdir(parents=True)
    (owned_archive / ARCHIVE_MARKER_NAME).write_text(
        "owned", encoding="utf-8"
    )
    unmarked_archive = reports / "archive" / "scan-20260723T130000000000Z"
    unmarked_archive.mkdir()

    run_retention(reports, logs, report_policy=policy("latest_only"))

    assert not owned_archive.exists()
    assert unmarked_archive.is_dir()
    assert (reports / "target-scan.html").read_text(
        encoding="utf-8"
    ) == "current"


def test_failed_replacement_keeps_safety_archive_until_a_successful_run(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    write_current_reports(reports, "last valid run")
    archive_before_report_write(
        html_report_path=reports / "target-scan.html",
        snapshot_path=reports / "target-scan.json",
        email_preview_path=reports / "target-email-preview.txt",
    )

    runs = list_retained_report_runs(reports)
    assert len(runs) == 1
    archived_report = (
        reports / "archive" / runs[0].archive_name / "target-scan.html"
    )
    assert archived_report.read_text(encoding="utf-8") == "last valid run"


def test_log_retention_prunes_only_recognized_dated_logs(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    logs = tmp_path / "logs"
    logs.mkdir()
    for timestamp in ("20260720T120000000000Z", "20260721T120000000000Z"):
        (logs / f"junior-{timestamp}.log").write_text(
            timestamp, encoding="utf-8"
        )
    (logs / "startup-errors.log").write_text("active", encoding="utf-8")
    (logs / "personal.log").write_text("unrelated", encoding="utf-8")

    run_retention(
        reports,
        logs,
        report_policy=policy("latest_only"),
        log_policy=policy("latest_only"),
    )

    assert not (logs / "junior-20260720T120000000000Z.log").exists()
    assert (logs / "junior-20260721T120000000000Z.log").is_file()
    assert (logs / "startup-errors.log").is_file()
    assert (logs / "personal.log").is_file()
