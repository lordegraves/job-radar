from dataclasses import dataclass
from sqlite3 import Row


STAGE_LABELS = {
    "initialization": "Initializing scan",
    "configuration": "Loading configuration",
    "history_import": "Importing application history",
    "collection": "Collecting company jobs",
    "scoring": "Scoring collected jobs",
    "storage": "Saving actionable jobs",
    "report_generation": "Generating reports",
    "email_delivery": "Sending email",
    "completed": "Scan completed",
}

STAGE_PROGRESS_FLOORS = {
    "initialization": 2,
    "configuration": 5,
    "history_import": 10,
    "collection": 15,
    "scoring": 75,
    "storage": 85,
    "report_generation": 92,
    "email_delivery": 97,
    "completed": 100,
}


@dataclass(frozen=True)
class ScanProgressView:
    scan_run_id: int
    status: str
    status_label: str
    current_stage: str
    stage_label: str
    progress_percent: int
    companies_requested: int
    companies_scanned: int
    jobs_found: int
    collector_errors: int
    requested_at: str | None
    started_at: str | None
    finished_at: str | None
    failure_summary: str | None
    is_running: bool
    is_terminal: bool
    succeeded: bool


def _build_status_label(status: str) -> str:
    labels = {
        "running": "Running",
        "completed": "Completed",
        "completed_with_warnings": "Completed with warnings",
        "failed": "Failed",
    }

    return labels.get(
        status,
        status.replace("_", " ").strip().title() or "Unknown",
    )


def _build_stage_label(stage: str) -> str:
    return STAGE_LABELS.get(
        stage,
        stage.replace("_", " ").strip().title() or "Unknown stage",
    )


def _calculate_progress_percent(scan_row: Row) -> int:
    status = str(scan_row["status"])

    if status in {"completed", "completed_with_warnings"}:
        return 100

    current_stage = str(scan_row["current_stage"] or "initialization")
    stage_floor = STAGE_PROGRESS_FLOORS.get(current_stage, 0)

    if status == "failed":
        return min(stage_floor, 99)

    if current_stage != "collection":
        return min(stage_floor, 99)

    companies_requested = max(int(scan_row["companies_requested"] or 0), 0)
    companies_scanned = max(int(scan_row["companies_scanned"] or 0), 0)

    if companies_requested <= 0:
        return stage_floor

    collection_span = (
        STAGE_PROGRESS_FLOORS["scoring"]
        - STAGE_PROGRESS_FLOORS["collection"]
    )
    collection_ratio = min(companies_scanned / companies_requested, 1.0)

    return min(
        int(
            STAGE_PROGRESS_FLOORS["collection"]
            + collection_span * collection_ratio
        ),
        STAGE_PROGRESS_FLOORS["scoring"] - 1,
    )


def build_scan_progress_view(
    scan_row: Row | None,
) -> ScanProgressView | None:
    if scan_row is None:
        return None

    status = str(scan_row["status"])
    current_stage = str(scan_row["current_stage"] or "initialization")
    terminal_statuses = {
        "completed",
        "completed_with_warnings",
        "failed",
    }

    return ScanProgressView(
        scan_run_id=int(scan_row["id"]),
        status=status,
        status_label=_build_status_label(status),
        current_stage=current_stage,
        stage_label=_build_stage_label(current_stage),
        progress_percent=_calculate_progress_percent(scan_row),
        companies_requested=int(scan_row["companies_requested"] or 0),
        companies_scanned=int(scan_row["companies_scanned"] or 0),
        jobs_found=int(scan_row["jobs_found"] or 0),
        collector_errors=int(scan_row["collector_errors"] or 0),
        requested_at=scan_row["requested_at"],
        started_at=scan_row["started_at"],
        finished_at=scan_row["finished_at"],
        failure_summary=scan_row["failure_summary"],
        is_running=status == "running",
        is_terminal=status in terminal_statuses,
        succeeded=status in {"completed", "completed_with_warnings"},
    )
