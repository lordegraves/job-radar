"""Test one employer collector without importing jobs or exposing raw failures."""

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.registry import collect_jobs_for_company
from job_radar.database import connect_database
from job_radar.diagnostic_service import classify_collector_failure
from job_radar.employer_admin_service import validate_source_configuration
from job_radar.employer_storage import get_employer_source
from job_radar.storage import initialize_database


SUCCESS = "success"
ERROR = "error"
NOT_TESTED = "not_tested"


@dataclass(frozen=True)
class EmployerConnectionHealth:
    """Present the latest safe operational result for one employer source."""

    state: str = NOT_TESTED
    category: str | None = None
    message: str | None = None
    job_count: int | None = None
    tested_at: str | None = None
    last_success_at: str | None = None
    last_error_at: str | None = None

    @property
    def state_label(self) -> str:
        return {
            SUCCESS: "Connected",
            ERROR: "Needs attention",
        }.get(self.state, "Not tested")


class EmployerConnectionError(ValueError):
    """Explain why a requested employer connection test cannot run."""


def test_employer_connection(
    database_path: str | Path,
    employer_id: str,
) -> EmployerConnectionHealth:
    """Run a bounded collector read and persist only a sanitized outcome."""

    employer = get_employer_source(database_path, employer_id)
    if employer is None:
        raise EmployerConnectionError("That employer no longer exists.")

    issues = validate_source_configuration(employer)
    if employer.source_type == "usajobs" and not all(
        os.environ.get(name)
        for name in ("USAJOBS_USER_AGENT", "USAJOBS_AUTHORIZATION_KEY")
    ):
        health = _error_health(
            "configuration",
            "USAJobs API access is not configured on this computer. Junior "
            "needs a USAJobs contact email and authorization key before it can "
            "test or scan federal sources.",
        )
    elif issues:
        message = (
            "This USAJobs source is missing its federal organization code. "
            "Complete the source setup, then test it again."
            if employer.source_type == "usajobs"
            else "Complete and validate the employer's source settings, then try again."
        )
        health = _error_health(
            "configuration",
            message,
        )
    else:
        try:
            source_config = employer.to_company_config()
            # A health check proves that the source is readable; it must not
            # perform the full, potentially thousands-of-jobs scan.
            # Eightfold's most common field failure occurs only when moving to
            # a later results page. Exercise that boundary without turning the
            # health check into a full scan.
            source_config["max_pages"] = (
                2 if employer.source_type == "eightfold" else 1
            )
            source_config["connection_test"] = True
            jobs = collect_jobs_for_company(source_config)
        except CollectorError as error:
            health = _collector_error_health(error)
        except requests.RequestException:
            health = _error_health(
                "network",
                "Junior could not reach the job source. Check the network "
                "connection and try again.",
            )
        except Exception:
            # Raw exception text may contain URLs, credentials, or response data.
            health = _error_health(
                "unexpected",
                "Junior could not test this source safely. Review the "
                "application log and contact support if the problem continues.",
            )
        else:
            count = len(jobs)
            health = _collection_health(count, context="Connection")

    _store_health(database_path, employer_id, health)
    return get_employer_connection_health(database_path, employer_id)


def get_employer_connection_health(
    database_path: str | Path,
    employer_id: str,
) -> EmployerConnectionHealth:
    """Load the last safe source-health result."""

    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT last_connection_state, last_connection_category,
                   last_connection_message, last_connection_job_count,
                   last_connection_test_at, last_connection_success_at,
                   last_connection_error_at
            FROM employer_sources
            WHERE employer_id = ?
            """,
            (employer_id,),
        ).fetchone()
    if row is None:
        raise EmployerConnectionError("That employer no longer exists.")
    return EmployerConnectionHealth(
        state=row["last_connection_state"],
        category=row["last_connection_category"],
        message=row["last_connection_message"],
        job_count=row["last_connection_job_count"],
        tested_at=row["last_connection_test_at"],
        last_success_at=row["last_connection_success_at"],
        last_error_at=row["last_connection_error_at"],
    )


def record_scan_connection_result(
    database_path: str | Path,
    employer_id: str,
    *,
    job_count: int | None = None,
    failure_category: str | None = None,
    failure_message: str | None = None,
) -> None:
    """Make a real scan the newest source-health evidence.

    A successful collection is stronger evidence than an older standalone
    connection test. Recording it here prevents a working source from staying
    red after Junior has demonstrably collected jobs from it.
    """

    if failure_message:
        health = EmployerConnectionHealth(
            state=ERROR,
            category=failure_category or "collector",
            message=failure_message,
        )
    else:
        count = int(job_count or 0)
        health = _collection_health(count, context="Scan")
    _store_health(database_path, employer_id, health)


def _collector_error_health(error: CollectorError) -> EmployerConnectionHealth:
    outcome = classify_collector_failure(error)
    return _error_health(outcome.category, outcome.message)


def _error_health(category: str, message: str) -> EmployerConnectionHealth:
    return EmployerConnectionHealth(
        state=ERROR,
        category=category,
        message=message,
    )


def _collection_health(count: int, *, context: str) -> EmployerConnectionHealth:
    """Treat an empty result as ambiguous source health, not proof of success."""

    if count == 0:
        return EmployerConnectionHealth(
            state=ERROR,
            category="empty_source",
            message=(
                f"{context} reached the source but returned no jobs. The employer "
                "may have no openings, or its recruiting source may have changed."
            ),
            job_count=0,
        )
    noun = "job" if count == 1 else "jobs"
    return EmployerConnectionHealth(
        state=SUCCESS,
        category="connected",
        message=f"{context} succeeded and returned {count} {noun}.",
        job_count=count,
    )


def _store_health(
    database_path: str | Path,
    employer_id: str,
    health: EmployerConnectionHealth,
) -> None:
    db_path = initialize_database(database_path)
    success_time = (
        "CURRENT_TIMESTAMP" if health.state == SUCCESS else "last_connection_success_at"
    )
    pending_test = "0" if health.state == SUCCESS else "source_change_pending_test"
    error_time = "CURRENT_TIMESTAMP" if health.state == ERROR else "NULL"
    with connect_database(db_path) as connection:
        connection.execute(
            f"""
            UPDATE employer_sources
            SET last_connection_test_at = CURRENT_TIMESTAMP,
                last_connection_success_at = {success_time},
                last_connection_error_at = {error_time},
                last_connection_state = ?,
                last_connection_category = ?,
                last_connection_message = ?,
                last_connection_job_count = ?,
                source_change_pending_test = {pending_test},
                updated_at = CURRENT_TIMESTAMP
            WHERE employer_id = ?
            """,
            (
                health.state,
                health.category,
                health.message,
                health.job_count,
                employer_id,
            ),
        )
