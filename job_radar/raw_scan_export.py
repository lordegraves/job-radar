"""Build a compressed, human-readable export of every collected scan posting."""

from datetime import datetime
from pathlib import Path
import tempfile
import zipfile

from job_radar import __display_version__
from job_radar.report_models import ScanReport


RAW_SCAN_ARCHIVE_NAME = "target-scan-raw.zip"
RAW_SCAN_TEXT_NAME = "target-scan-raw.txt"


def write_raw_scan_export(
    archive_path: str | Path,
    report: ScanReport,
) -> Path:
    """Write all collected postings to a compressed plain-text download."""
    path = Path(archive_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = _build_raw_scan_text(report)
    with tempfile.NamedTemporaryFile(
        prefix=f".{path.stem}.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with zipfile.ZipFile(
            temporary_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            archive.writestr(RAW_SCAN_TEXT_NAME, text)
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return path


def _build_raw_scan_text(report: ScanReport) -> str:
    lines = [
        "Junior raw scan export",
        f"Junior build: {__display_version__}",
        f"Generated: {report.generated_at or 'Unknown'}",
        f"Companies enabled: {report.companies_enabled}",
        f"Jobs collected: {len(report.postings)}",
        "",
        (
            "This file contains the public job-posting data collected during "
            "one scan. It is not a recommendation report."
        ),
        "",
    ]
    for index, posting in enumerate(report.postings, start=1):
        lines.extend(
            (
                "=" * 80,
                f"Posting {index}",
                f"Company: {posting.company_name}",
                f"Title: {posting.title}",
                f"Location: {posting.location or 'Not stated'}",
                f"Remote status: {posting.remote_status or 'Not stated'}",
                f"Compensation: {posting.salary_text or 'Not stated'}",
                f"Source type: {posting.source_type}",
                f"Source URL: {posting.source_url}",
                f"Source job ID: {posting.source_job_id or 'Not stated'}",
                f"Junior job ID: {posting.job_radar_id}",
                "",
                "Job description:",
                posting.description or "Not provided",
                "",
            )
        )
    return "\n".join(lines)


def raw_scan_download_name(modified_timestamp: float) -> str:
    """Return a stable user-facing filename that will not overwrite silently."""
    timestamp = datetime.fromtimestamp(modified_timestamp).strftime(
        "%Y-%m-%d-%H%M"
    )
    return f"junior-raw-scan-{timestamp}.zip"
