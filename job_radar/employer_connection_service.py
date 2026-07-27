"""Test one employer collector without importing jobs or exposing raw failures."""

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
    if issues:
        health = _error_health(
            "configuration",
            "Complete and validate the employer's source settings, then try again.",
        )
    else:
        try:
            source_config = employer.to_company_config()
            # A health check proves that the source is readable; it must not
            # perform the full, potentially thousands-of-jobs scan.
            source_config["max_pages"] = 1
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
            noun = "job" if count == 1 else "jobs"
            health = EmployerConnectionHealth(
                state=SUCCESS,
                category="connected",
                message=f"Connection succeeded and returned {count} {noun}.",
                job_count=count,
            )

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


def _collector_error_health(error: CollectorError) -> EmployerConnectionHealth:
    outcome = classify_collector_failure(error)
    return _error_health(outcome.category, outcome.message)


def _error_health(category: str, message: str) -> EmployerConnectionHealth:
    return EmployerConnectionHealth(
        state=ERROR,
        category=category,
        message=message,
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
    error_time = (
        "CURRENT_TIMESTAMP" if health.state == ERROR else "last_connection_error_at"
    )
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
