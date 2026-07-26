"""Build safe, read-only company-source and latest-scan diagnostic details."""

from dataclasses import dataclass
from pathlib import Path

from job_radar.database import connect_database
from job_radar.employer_connection_service import get_employer_connection_health
from job_radar.employer_storage import list_employer_sources
from job_radar.storage import fetch_latest_scan_run, initialize_database


@dataclass(frozen=True)
class SourceHealthItem:
    """Describe one global source without exposing its collector configuration."""

    employer_id: str
    employer_name: str
    source_type: str
    source_label: str
    enabled: bool
    state: str
    state_label: str
    category: str | None
    message: str
    job_count: int | None
    tested_at: str | None
    latest_scan_state: str
    latest_scan_message: str


@dataclass(frozen=True)
class ScanWarningItem:
    """Expose one already-sanitized latest-scan warning."""

    employer_id: str
    employer_name: str
    source_type: str
    source_label: str
    category: str
    message: str
    created_at: str


def build_source_health_items(
    database_path: str | Path,
) -> tuple[SourceHealthItem, ...]:
    """Combine manual connection tests with safe latest-scan observations."""

    db_path = initialize_database(database_path)
    latest = fetch_latest_scan_run(db_path)
    warning_by_company: dict[str, tuple[str, str]] = {}
    latest_profile_companies: set[str] = set()

    if latest is not None:
        with connect_database(db_path) as connection:
            warning_by_company = {
                str(row[0]): (str(row[1]), str(row[2]))
                for row in connection.execute(
                    """
                    SELECT company_key, error_type, error_message
                    FROM scan_errors
                    WHERE scan_run_id = ?
                      AND company_key IS NOT NULL
                    """,
                    (int(latest["id"]),),
                ).fetchall()
            }
            if latest["profile_id"]:
                latest_profile_companies = {
                    str(row[0])
                    for row in connection.execute(
                        """
                        SELECT company_id
                        FROM profile_company_associations
                        WHERE profile_id = ?
                          AND enabled = 1
                        """,
                        (str(latest["profile_id"]),),
                    ).fetchall()
                }

    items: list[SourceHealthItem] = []
    for employer in list_employer_sources(db_path):
        health = get_employer_connection_health(db_path, employer.employer_id)
        warning = warning_by_company.get(employer.employer_id)
        if warning:
            scan_state = "Warning"
            scan_message = warning[1]
        elif employer.employer_id in latest_profile_companies:
            scan_state = "No warning"
            scan_message = "No source warning was recorded in the latest scan."
        else:
            scan_state = "Not in latest scan"
            scan_message = "This source was not part of the latest profile scan."

        items.append(
            SourceHealthItem(
                employer_id=employer.employer_id,
                employer_name=employer.name,
                source_type=employer.source_type,
                source_label=_source_label(employer.source_type),
                enabled=employer.enabled,
                state=health.state,
                state_label=health.state_label,
                category=health.category,
                message=health.message or "No separate connection test has run.",
                job_count=health.job_count,
                tested_at=health.tested_at,
                latest_scan_state=scan_state,
                latest_scan_message=scan_message,
            )
        )
    return tuple(items)


def build_latest_scan_warnings(
    database_path: str | Path,
) -> tuple[ScanWarningItem, ...]:
    """Return only sanitized warnings from the latest scan."""

    db_path = initialize_database(database_path)
    latest = fetch_latest_scan_run(db_path)
    if latest is None:
        return ()

    employers = {
        employer.employer_id: employer
        for employer in list_employer_sources(db_path)
    }
    with connect_database(db_path) as connection:
        rows = connection.execute(
            """
            SELECT company_key, source_type, error_type, error_message, created_at
            FROM scan_errors
            WHERE scan_run_id = ?
            ORDER BY company_key COLLATE NOCASE
            """,
            (int(latest["id"]),),
        ).fetchall()

    warnings: list[ScanWarningItem] = []
    for company_key, source_type, category, message, created_at in rows:
        employer = employers.get(str(company_key))
        warnings.append(
            ScanWarningItem(
                employer_id=str(company_key or ""),
                employer_name=(
                    employer.name if employer is not None else str(company_key or "Unknown")
                ),
                source_type=str(source_type or "unknown"),
                source_label=_source_label(str(source_type or "unknown")),
                category=str(category).replace("_", " ").title(),
                message=str(message),
                created_at=str(created_at),
            )
        )
    return tuple(warnings)


def _source_label(source_type: str) -> str:
    return {
        "adp": "ADP Workforce Now",
        "eightfold": "Eightfold",
        "html": "Standard public careers page",
        "icims": "iCIMS",
        "oracle_hcm": "Oracle Cloud HCM",
        "ukg": "UKG Pro Recruiting",
    }.get(source_type, source_type.replace("_", " ").title())
