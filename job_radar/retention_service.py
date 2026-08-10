"""Archive and prune only clearly owned Junior report and log outputs."""

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import os
from pathlib import Path
import re
import shutil
import tempfile

from job_radar.config import RetentionSettings


ARCHIVE_DIRECTORY_NAME = "archive"
ARCHIVE_MARKER_NAME = ".junior-report-archive"
_ARCHIVE_NAME_PATTERN = re.compile(
    r"^scan-(?P<timestamp>\d{8}T\d{12})Z(?:-(?P<counter>\d{2}))?$"
)
_OWNED_LOG_PATTERN = re.compile(
    r"^(?:(?:junior|startup-errors)-\d{8}T\d{12}Z|"
    r"junior-(?:database|errors|user-actions)-\d{8}T\d{6}Z|"
    r"junior-(?:scan|evaluation)-run-\d+-\d{8}T\d{6}Z)\.log$"
)


@dataclass(frozen=True)
class RetainedReportRun:
    archive_name: str
    generated_at: str
    html_report_name: str | None
    email_preview_name: str | None
    evaluation_audit_name: str | None
    raw_scan_name: str | None


def archive_before_report_write(
    *,
    html_report_path: str | Path,
    snapshot_path: str | Path,
    email_preview_path: str | Path | None,
    evaluation_audit_path: str | Path | None = None,
    raw_scan_path: str | Path | None = None,
) -> None:
    """Preserve the prior known report set before any current file is replaced."""
    html_path = Path(html_report_path)
    snapshot = Path(snapshot_path)
    email_path = Path(email_preview_path) if email_preview_path else None
    audit_path = (
        Path(evaluation_audit_path) if evaluation_audit_path else None
    )
    raw_path = Path(raw_scan_path) if raw_scan_path else None
    report_files = tuple(
        path
        for path in (html_path, snapshot, email_path, audit_path, raw_path)
        if path is not None and path.is_file()
    )
    if report_files:
        _archive_report_files(
            reports_directory=html_path.parent,
            report_files=report_files,
        )


def apply_retention_after_report_write(
    *,
    reports_path: str | Path,
    logs_path: str | Path,
    retention: RetentionSettings,
) -> None:
    """Prune owned history only after the replacement report set is complete."""
    archives_to_keep = max(0, retention.reports.total_to_keep - 1)
    _prune_report_archives(Path(reports_path), keep=archives_to_keep)
    _prune_owned_logs(
        Path(logs_path),
        keep=retention.logs.total_to_keep,
    )


def list_retained_report_runs(
    reports_path: str | Path,
) -> tuple[RetainedReportRun, ...]:
    archives = _owned_archive_directories(Path(reports_path))
    return tuple(
        RetainedReportRun(
            archive_name=archive.name,
            generated_at=_format_archive_name(archive.name),
            html_report_name=_optional_relative_name(
                archive,
                "target-scan.html",
            ),
            email_preview_name=_optional_relative_name(
                archive,
                "target-email-preview.txt",
            ),
            evaluation_audit_name=_optional_relative_name(
                archive,
                "job-evaluation-audit.txt",
            ),
            raw_scan_name=_optional_relative_name(
                archive,
                "target-scan-raw.zip",
            ),
        )
        for archive in reversed(archives)
    )


def _archive_report_files(
    *,
    reports_directory: Path,
    report_files: tuple[Path, ...],
) -> Path:
    archive_root = reports_directory / ARCHIVE_DIRECTORY_NAME
    archive_root.mkdir(parents=True, exist_ok=True)
    archive_name = _next_archive_name(archive_root)
    temporary_directory = Path(
        tempfile.mkdtemp(prefix=f".{archive_name}.", dir=archive_root)
    )
    final_directory = archive_root / archive_name
    try:
        (temporary_directory / ARCHIVE_MARKER_NAME).write_text(
            "Junior retained report archive.\n",
            encoding="utf-8",
        )
        for source in report_files:
            destination = temporary_directory / source.name
            shutil.copy2(source, destination)
            if _sha256(source) != _sha256(destination):
                raise OSError("Retained report verification failed.")
        os.replace(temporary_directory, final_directory)
    except BaseException:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        raise
    return final_directory


def _prune_report_archives(reports_directory: Path, *, keep: int) -> None:
    archives = _owned_archive_directories(reports_directory)
    for archive in archives[: max(0, len(archives) - keep)]:
        try:
            shutil.rmtree(archive)
        except OSError:
            # Retention is housekeeping after the new report is durable. A
            # locked historical archive must not change a completed scan into
            # a failed scan; Junior can try to prune it again next time.
            continue


def _prune_owned_logs(logs_directory: Path, *, keep: int) -> None:
    if not logs_directory.is_dir():
        return
    owned_logs: dict[str, list[Path]] = {}
    for path in logs_directory.iterdir():
        if not path.is_file() or not _OWNED_LOG_PATTERN.fullmatch(path.name):
            continue
        owned_logs.setdefault(_owned_log_family(path.name), []).append(path)
    for family_logs in owned_logs.values():
        family_logs.sort(key=lambda path: path.name)
        for path in family_logs[: max(0, len(family_logs) - keep)]:
            try:
                path.unlink()
            except OSError:
                # Antivirus and report viewers can briefly lock old Windows logs.
                # Preserve the completed scan and retry cleanup on a later run.
                continue
    _prune_owned_logs_to_byte_ceiling(logs_directory)


MAX_RETAINED_DATED_LOG_BYTES = 100_000_000


def _prune_owned_logs_to_byte_ceiling(logs_directory: Path) -> None:
    """Bound dated scan history even when the configured file count is high."""

    dated_logs = sorted(
        (
            path
            for path in logs_directory.iterdir()
            if path.is_file() and _OWNED_LOG_PATTERN.fullmatch(path.name)
        ),
        key=lambda path: (path.stat().st_mtime, path.name),
    )
    retained_bytes = sum(path.stat().st_size for path in dated_logs)
    while retained_bytes > MAX_RETAINED_DATED_LOG_BYTES and len(dated_logs) > 1:
        path = dated_logs.pop(0)
        try:
            size = path.stat().st_size
            path.unlink()
        except OSError:
            continue
        retained_bytes -= size


def _owned_log_family(name: str) -> str:
    """Retain history independently for each troubleshooting purpose."""

    for family in (
        "database",
        "errors",
        "user-actions",
        "scan-run",
        "evaluation-run",
        "startup-errors",
    ):
        if name.startswith(f"junior-{family}-") or name.startswith(f"{family}-"):
            return family
    return "legacy-junior"


def _owned_archive_directories(reports_directory: Path) -> list[Path]:
    archive_root = reports_directory / ARCHIVE_DIRECTORY_NAME
    if not archive_root.is_dir():
        return []
    return sorted(
        (
            path
            for path in archive_root.iterdir()
            if _is_owned_archive(path)
        ),
        key=lambda path: path.name,
    )


def _is_owned_archive(path: Path) -> bool:
    """Ignore inaccessible history rather than failing the completed scan."""

    try:
        return bool(
            path.is_dir()
            and _ARCHIVE_NAME_PATTERN.fullmatch(path.name)
            and (path / ARCHIVE_MARKER_NAME).is_file()
        )
    except OSError:
        return False


def _next_archive_name(archive_root: Path) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    candidate = f"scan-{timestamp}"
    counter = 1
    while (archive_root / candidate).exists():
        candidate = f"scan-{timestamp}-{counter:02d}"
        counter += 1
    return candidate


def _format_archive_name(name: str) -> str:
    match = _ARCHIVE_NAME_PATTERN.fullmatch(name)
    if match is None:
        return name
    raw_timestamp = match.group("timestamp")
    try:
        parsed = datetime.strptime(raw_timestamp, "%Y%m%dT%H%M%S%f")
    except ValueError:
        return name
    return parsed.strftime("%Y-%m-%d %I:%M %p UTC")


def _optional_relative_name(archive: Path, filename: str) -> str | None:
    path = archive / filename
    if not path.is_file():
        return None
    return f"{ARCHIVE_DIRECTORY_NAME}/{archive.name}/{filename}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
