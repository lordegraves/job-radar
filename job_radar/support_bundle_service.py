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
from job_radar.storage import fetch_latest_scan_run


MAX_BUNDLE_BYTES = 30_000_000
MAX_MEMBER_BYTES = 5_000_000
MAX_LOG_FILES = 20
_REPORT_FILES = (
    "target-scan.json",
    "target-scan.html",
    "job-evaluation-audit.txt",
    "targeted-job-evaluation-audit.txt",
)


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

    latest_scan = fetch_latest_scan_run(runtime_paths.database_path)
    scan_matches_profile = bool(
        latest_scan is not None
        and latest_scan["profile_id"] == profile.profile_id
        and latest_scan["status"] in {"completed", "completed_with_warnings"}
        and latest_scan["report_status"] == "completed"
    )
    if scan_matches_profile:
        for name in _REPORT_FILES:
            path = runtime_paths.reports_path / name
            if path.is_file():
                _add_file(members, f"latest-scan/{name}", path, omitted)
    else:
        omitted.append(
            "Latest scan artifacts were not included because the most recent "
            "completed report does not belong to the selected profile."
        )

    for log in list_diagnostic_logs(runtime_paths.logs_path)[:MAX_LOG_FILES]:
        content = build_diagnostic_log_download(
            runtime_paths.logs_path,
            log.name,
        ).encode("utf-8")
        _add_member(members, f"logs/{log.name}", content, omitted)

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
