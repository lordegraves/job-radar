"""List and read only bounded, sanitized logs that Junior explicitly owns."""

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from job_radar.application_info_service import ApplicationInfo
from job_radar.diagnostic_service import DiagnosticsView


MAX_VISIBLE_LOGS = 20
MAX_LOG_VIEW_BYTES = 200_000
_OWNED_LOG_PATTERN = re.compile(
    r"^(?:junior-actions\.log|junior-company-discovery\.log|"
    r"junior-diagnostics\.log|junior-last-scan\.log|"
    r"startup-errors\.log|(?:junior|startup-errors)-"
    r"\d{8}T\d{12}Z\.log)$"
)


class DiagnosticLogError(ValueError):
    """Explain a safe log or data-directory action failure."""


@dataclass(frozen=True)
class DiagnosticLogFile:
    name: str
    title: str
    description: str
    modified_at: str
    size_bytes: int


@dataclass(frozen=True)
class DiagnosticLogView:
    name: str
    title: str
    description: str
    content: str
    truncated: bool
    size_bytes: int
    entries: tuple["DiagnosticLogEntry", ...]


@dataclass(frozen=True)
class DiagnosticLogEntry:
    """Present one allowlisted JSON log event in readable operational terms."""

    timestamp: str
    title: str
    summary: str
    details: tuple[str, ...]


def list_diagnostic_logs(logs_path: str | Path) -> tuple[DiagnosticLogFile, ...]:
    directory = Path(logs_path)
    if not directory.is_dir():
        return ()
    paths = sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and _OWNED_LOG_PATTERN.fullmatch(path.name)
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:MAX_VISIBLE_LOGS]
    return tuple(
        DiagnosticLogFile(
            name=path.name,
            title=_log_title(path.name),
            description=_log_description(path.name),
            modified_at=datetime.fromtimestamp(path.stat().st_mtime).strftime(
                "%Y-%m-%d %I:%M %p"
            ),
            size_bytes=path.stat().st_size,
        )
        for path in paths
    )


def read_diagnostic_log(
    logs_path: str | Path,
    log_name: str,
) -> DiagnosticLogView:
    path = _resolve_owned_log(logs_path, log_name)
    size = path.stat().st_size
    truncated = size > MAX_LOG_VIEW_BYTES
    with path.open("rb") as stream:
        if truncated:
            stream.seek(-MAX_LOG_VIEW_BYTES, os.SEEK_END)
        content = stream.read(MAX_LOG_VIEW_BYTES).decode(
            "utf-8",
            errors="replace",
        )
    if truncated:
        content = (
            "[Earlier log entries are hidden because this file is large.]\n"
            + content
        )
    return DiagnosticLogView(
        name=path.name,
        title=_log_title(path.name),
        description=_log_description(path.name),
        content=content,
        truncated=truncated,
        size_bytes=size,
        entries=_parse_log_entries(content),
    )


def build_readable_log_download(log_view: DiagnosticLogView) -> bytes:
    """Return a human-readable support file while retaining structured facts."""

    lines = [
        f"Junior — {log_view.title}",
        log_view.description,
        "",
    ]
    for entry in log_view.entries:
        lines.append(f"[{entry.timestamp}] {entry.title}")
        lines.append(entry.summary)
        lines.extend(f"- {detail}" for detail in entry.details)
        lines.append("")
    if not log_view.entries:
        lines.append("No readable diagnostic events were found in this log.")
    return "\n".join(lines).encode("utf-8")


def diagnostic_download_name(log_view: DiagnosticLogView) -> str:
    """Create an email-friendly filename that identifies when it was saved."""

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{Path(log_view.name).stem}-{stamp}.txt"


def get_diagnostic_log_download(
    logs_path: str | Path,
    log_name: str,
) -> Path:
    """Resolve only a recognized Junior-owned log for direct download."""

    return _resolve_owned_log(logs_path, log_name)


def build_support_summary(
    application_info: ApplicationInfo,
    diagnostics: DiagnosticsView,
) -> str:
    lines = [
        "Junior troubleshooting summary",
        f"Version: {application_info.version}",
        f"Build: {application_info.build_label}",
        f"Release channel: {application_info.release_channel}",
        f"Database schema: {application_info.database_schema_version}",
        f"Profile schema: {application_info.profile_schema_version}",
        f"User data location: {application_info.user_data_location}",
        "",
        "Health:",
    ]
    lines.extend(
        f"- {card.title}: {card.state} ({card.category})"
        for card in diagnostics.cards
    )
    lines.extend(
        (
            "",
            "Do not include passwords, access tokens, credentials, the database,",
            "résumé contents, or profile contents in a support message.",
        )
    )
    return "\n".join(lines)


def open_data_directory(data_path: str | Path) -> None:
    directory = Path(data_path).resolve()
    if not directory.is_dir():
        raise DiagnosticLogError(
            "Junior's data directory is not available on this computer."
        )
    try:
        if sys.platform == "win32":
            os.startfile(directory)  # type: ignore[attr-defined]
            return
        if sys.platform == "darwin":
            command = ["open", str(directory)]
        else:
            command = ["xdg-open", str(directory)]
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        raise DiagnosticLogError(
            "Junior could not open the data directory. "
            "The location remains visible in the troubleshooting summary."
        ) from error


def _resolve_owned_log(logs_path: str | Path, log_name: str) -> Path:
    if Path(log_name).name != log_name:
        raise DiagnosticLogError("That diagnostic log is not available.")
    if _OWNED_LOG_PATTERN.fullmatch(log_name) is None:
        raise DiagnosticLogError("That diagnostic log is not available.")
    directory = Path(logs_path).resolve()
    path = (directory / log_name).resolve()
    if directory not in path.parents or not path.is_file():
        raise DiagnosticLogError("That diagnostic log is not available.")
    return path


def _log_title(log_name: str) -> str:
    return {
        "junior-actions.log": "User action history",
        "junior-last-scan.log": "Latest scan activity",
        "junior-company-discovery.log": "Company discovery activity",
        "junior-diagnostics.log": "Operational diagnostics",
    }.get(
        log_name,
        (
            "Startup problem details"
            if log_name.startswith("startup-errors")
            else "Junior diagnostic history"
        ),
    )


def _log_description(log_name: str) -> str:
    descriptions = {
        "junior-actions.log": (
            "Safe records of Save, Pass, Apply, and other deliberate job "
            "decisions. Job descriptions and profile contents are excluded."
        ),
        "junior-last-scan.log": (
            "A step-by-step operational record of the newest scan, including "
            "safe company-source outcomes and totals but no job listings."
        ),
        "junior-company-discovery.log": (
            "Safe outcomes from attempts to identify a company's public "
            "recruiting platform. Probe responses are not retained."
        ),
        "junior-diagnostics.log": (
            "Bounded operational history across recent scans. It contains "
            "safe status fields rather than raw exceptions."
        ),
    }
    if log_name.startswith("startup-errors"):
        return "Sanitized information recorded when Junior could not start."
    return descriptions.get(
        log_name,
        "A bounded, sanitized Junior-owned troubleshooting record.",
    )


def _parse_log_entries(content: str) -> tuple[DiagnosticLogEntry, ...]:
    entries: list[DiagnosticLogEntry] = []
    for line in content.splitlines():
        if not line.strip() or line.startswith("[Earlier log entries"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            entries.append(
                DiagnosticLogEntry(
                    timestamp="Time not recorded",
                    title="Diagnostic note",
                    summary=line,
                    details=(),
                )
            )
            continue
        if not isinstance(value, dict):
            continue
        event = str(value.get("event") or "diagnostic_event")
        timestamp = _display_timestamp(value.get("timestamp"))
        summary, used = _event_summary(event, value)
        details = tuple(
            f"{key.replace('_', ' ').title()}: {item}"
            for key, item in value.items()
            if key not in used | {"event", "timestamp"} and item is not None
        )
        entries.append(
            DiagnosticLogEntry(
                timestamp=timestamp,
                title=event.replace("_", " ").title(),
                summary=summary,
                details=details,
            )
        )
    return tuple(entries)


def _display_timestamp(value: object) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value or "Time not recorded")
    return parsed.astimezone().strftime("%Y-%m-%d %I:%M:%S %p")


def _event_summary(
    event: str,
    value: dict[str, object],
) -> tuple[str, set[str]]:
    if event == "scan_started":
        return (
            f"Junior started a scan of {value.get('companies_requested', 0)} "
            "company source(s).",
            {"companies_requested"},
        )
    if event == "company_collection_completed":
        return (
            f"{value.get('company_id', 'Company source')} worked and returned "
            f"{value.get('jobs_found', 0)} job(s).",
            {"company_id", "jobs_found"},
        )
    if event == "company_collection_failed":
        return (
            f"{value.get('company_id', 'Company source')} failed during "
            f"collection: {value.get('failure_reason', 'No reason recorded.')}",
            {"company_id", "failure_reason"},
        )
    if event == "scan_completed":
        return (
            f"Scan completed: {value.get('jobs_found', 0)} found, "
            f"{value.get('jobs_stored', 0)} kept for review, "
            f"{value.get('jobs_omitted', 0)} omitted, and "
            f"{value.get('collector_errors', 0)} source error(s).",
            {"jobs_found", "jobs_stored", "jobs_omitted", "collector_errors"},
        )
    return (event.replace("_", " ").capitalize() + ".", set())
