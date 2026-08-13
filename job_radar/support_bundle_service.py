"""Build a bounded troubleshooting package without copying private user data."""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from job_radar.application_info_service import ApplicationInfo
from job_radar.company_transfer_service import export_company_catalog
from job_radar.diagnostic_log_service import (
    build_diagnostic_log_download,
    build_support_summary,
    list_diagnostic_logs,
)
from job_radar.diagnostic_service import DiagnosticsView
from job_radar.profile_storage import get_profile
from job_radar.profile_transfer_service import export_profile
from job_radar.runtime_paths import RuntimePaths
from job_radar.storage import fetch_latest_completed_scan_run_for_profile


MAX_BUNDLE_BYTES = 30_000_000
MAX_MEMBER_BYTES = 20_000_000
MAX_LOG_FILES = 20


class SupportBundleError(ValueError):
    """Explain why a safe troubleshooting package could not be created."""


@dataclass(frozen=True)
class SupportBundle:
    filename: str
    content: bytes


def build_support_bundle(
    runtime_paths: RuntimePaths,
    application_info: ApplicationInfo,
    diagnostics: DiagnosticsView,
    profile_id: str,
    *,
    now: datetime | None = None,
) -> SupportBundle:
    """Create one support ZIP from an explicit allowlist of safe artifacts."""

    profile = get_profile(runtime_paths.database_path, profile_id)
    if profile is None or profile.archived:
        raise SupportBundleError(
            "Choose an available profile before downloading troubleshooting information."
        )

    generated = now or datetime.now(UTC)
    stamp = generated.astimezone(UTC).strftime("%Y%m%d-%H%M%S")
    members: dict[str, bytes] = {}
    omitted: list[str] = []

    profile_name, profile_content = export_profile(
        runtime_paths.database_path,
        profile.profile_id,
    )
    company_name, company_content = export_company_catalog(
        runtime_paths.database_path
    )
    _add_member(members, f"configuration/{profile_name}", profile_content, omitted)
    _add_member(members, f"configuration/{company_name}", company_content, omitted)
    _add_member(
        members,
        "diagnostics/health-summary.txt",
        build_support_summary(application_info, diagnostics).encode("utf-8"),
        omitted,
    )

    latest_scan = fetch_latest_completed_scan_run_for_profile(
        runtime_paths.database_path, profile.profile_id
    )
    scan_artifacts = (
        _matching_scan_artifacts(runtime_paths.reports_path, latest_scan)
        if latest_scan is not None
        else ()
    )
    scan_matches_profile = bool(scan_artifacts)
    if scan_matches_profile:
        for path in scan_artifacts:
            _add_file(members, f"latest-scan/{path.name}", path, omitted)
    else:
        omitted.append(
            "Latest scan artifacts were not included because Junior could not "
            "verify a retained report set for the selected profile's newest scan."
        )

    log_names: list[str] = []
    if latest_scan is not None:
        for prefix in ("junior-scan", "junior-evaluation"):
            log_names.extend(
                path.name
                for path in sorted(
                    runtime_paths.logs_path.glob(
                        f"{prefix}-run-{latest_scan['id']}-*.log"
                    ),
                    reverse=True,
                )
            )
    log_names.extend(log.name for log in list_diagnostic_logs(runtime_paths.logs_path))
    log_names = list(dict.fromkeys(log_names))
    for log_name in log_names[:MAX_LOG_FILES]:
        content = build_diagnostic_log_download(
            runtime_paths.logs_path,
            log_name,
        ).encode("utf-8")
        _add_member(members, f"logs/{log_name}", content, omitted)

    instructions = (
        "Junior troubleshooting package\n\n"
        "Send this ZIP only when you choose to ask for support. Junior did not "
        "send it automatically.\n\n"
        "To reproduce the profile safely, import the company catalog first, then "
        "import the profile configuration. The imported profile remains inactive "
        "and contains no resume.\n\n"
        "Excluded on purpose: resume files and text; the SQLite database; "
        "credentials and tokens; applications and history; saved or passed jobs; "
        "personal notes; backups; raw scan archives; and files outside Junior's "
        "explicit diagnostic allowlist.\n"
    )
    _add_member(members, "README.txt", instructions.encode("utf-8"), omitted)

    manifest = {
        "format": "junior-troubleshooting-package",
        "schema_version": 1,
        "generated_at": generated.astimezone(UTC).isoformat(),
        "selected_profile": profile.display_name,
        "selected_profile_id": profile.profile_id,
        "latest_scan_run_id": latest_scan["id"] if latest_scan is not None else None,
        "latest_scan_trigger": latest_scan["trigger_source"] if latest_scan is not None else None,
        "matching_scan_included": scan_matches_profile,
        "files": sorted([*members, "manifest.json"]),
        "omitted": omitted,
        "excluded": [
            "resume files and resume text",
            "SQLite database and database exports",
            "credentials, tokens, and environment contents",
            "applications, history, saved jobs, passed jobs, and personal notes",
            "backups, raw scan archives, and arbitrary local files",
        ],
    }
    _add_member(
        members,
        "manifest.json",
        json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8"),
        omitted,
    )

    stream = io.BytesIO()
    with zipfile.ZipFile(
        stream,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=False,
    ) as archive:
        for name, content in sorted(members.items()):
            archive.writestr(name, content)
    content = stream.getvalue()
    if len(content) > MAX_BUNDLE_BYTES:
        raise SupportBundleError(
            "The troubleshooting package is too large to download safely. "
            "Reduce retained logs and try again."
        )
    return SupportBundle(
        filename=f"junior-troubleshooting-{stamp}.zip",
        content=content,
    )


def _matching_scan_artifacts(
    reports_path: Path,
    scan_run,
) -> tuple[Path, ...]:
    """Find one report set whose audit header proves the scan-run identity."""

    targeted = scan_run["trigger_source"] == "manual:selected"
    audit_name = (
        "targeted-job-evaluation-audit.txt"
        if targeted
        else "job-evaluation-audit.txt"
    )
    report_names = (
        ("targeted-scan.json", "targeted-scan.html", audit_name)
        if targeted
        else ("target-scan.json", "target-scan.html", audit_name)
    )
    candidates = [reports_path]
    archive_root = reports_path / "archive"
    if archive_root.is_dir():
        candidates.extend(
            path for path in sorted(archive_root.iterdir(), reverse=True) if path.is_dir()
        )
    marker = f"Scan run ID: {scan_run['id']}"
    for directory in candidates:
        audit = directory / audit_name
        if not audit.is_file():
            continue
        try:
            header = audit.read_text(encoding="utf-8", errors="replace")[:4096]
        except OSError:
            continue
        if marker not in header:
            continue
        return tuple(
            path for name in report_names if (path := directory / name).is_file()
        )
    return ()


def _add_file(
    members: dict[str, bytes],
    name: str,
    path: Path,
    omitted: list[str],
) -> None:
    if path.stat().st_size > MAX_MEMBER_BYTES:
        omitted.append(f"{name} exceeded the per-file size limit.")
        return
    _add_member(members, name, path.read_bytes(), omitted)


def _add_member(
    members: dict[str, bytes],
    name: str,
    content: bytes,
    omitted: list[str],
) -> None:
    if len(content) > MAX_MEMBER_BYTES:
        omitted.append(f"{name} exceeded the per-file size limit.")
        return
    members[name] = content
