"""Persist first-run progress so an interrupted setup resumes safely."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from job_radar.database import connect_database
from job_radar.storage import initialize_database


PROFILE = "profile"
RESUME = "resume"
FIT = "fit"
COMPANIES = "companies"
REVIEW = "review"
COMPLETE = "complete"
SETUP_STEPS = (PROFILE, RESUME, FIT, COMPANIES, REVIEW, COMPLETE)


@dataclass(frozen=True)
class SetupProgress:
    """Describe the single installation-local setup checkpoint."""

    current_step: str
    profile_id: str | None
    started_at: str
    updated_at: str
    completed_at: str | None
    validation_state: str
    validation_message: str | None
    validated_employer_id: str | None
    validated_at: str | None

    @property
    def complete(self) -> bool:
        return self.completed_at is not None


def get_setup_progress(
    database_path: str | Path,
) -> SetupProgress | None:
    """Load setup state without inferring progress from unrelated records."""

    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM setup_progress WHERE singleton_id = 1"
        ).fetchone()
    if row is None:
        return None
    return SetupProgress(
        current_step=row["current_step"],
        profile_id=row["profile_id"],
        started_at=row["started_at"],
        updated_at=row["updated_at"],
        completed_at=row["completed_at"],
        validation_state=row["validation_state"],
        validation_message=row["validation_message"],
        validated_employer_id=row["validated_employer_id"],
        validated_at=row["validated_at"],
    )


def start_setup(database_path: str | Path) -> SetupProgress:
    """Begin once, preserving an existing incomplete checkpoint."""

    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO setup_progress (
                singleton_id, current_step
            ) VALUES (1, ?)
            """,
            (PROFILE,),
        )
    progress = get_setup_progress(db_path)
    if progress is None:
        raise RuntimeError("Junior could not create setup progress.")
    return progress


def advance_setup(
    database_path: str | Path,
    step: str,
    *,
    profile_id: str | None = None,
) -> SetupProgress:
    """Advance to a named step without erasing the chosen profile."""

    if step not in SETUP_STEPS[:-1]:
        raise ValueError("Choose a valid setup step.")
    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.execute(
            """
            INSERT INTO setup_progress (
                singleton_id, current_step, profile_id
            ) VALUES (1, ?, ?)
            ON CONFLICT(singleton_id) DO UPDATE SET
                current_step = excluded.current_step,
                profile_id = COALESCE(
                    excluded.profile_id, setup_progress.profile_id
                ),
                validation_state = 'not_tested',
                validation_message = NULL,
                validated_employer_id = NULL,
                validated_at = NULL,
                updated_at = CURRENT_TIMESTAMP,
                completed_at = NULL
            """,
            (step, profile_id),
        )
    progress = get_setup_progress(db_path)
    if progress is None:
        raise RuntimeError("Junior could not update setup progress.")
    return progress


def complete_setup(
    database_path: str | Path,
    *,
    confirmation: str,
) -> None:
    """Complete onboarding only after an explicit review confirmation."""

    if confirmation != "FINISH":
        raise ValueError("Confirm the review before finishing setup.")
    db_path = initialize_database(database_path)
    progress = get_setup_progress(db_path)
    if progress is None or progress.validation_state != "passed":
        raise ValueError("Test the setup successfully before finishing.")
    if not progress.validated_employer_id:
        raise ValueError("Confirm at least one working company source.")
    from job_radar.employer_connection_service import (
        get_employer_connection_health,
    )

    health = get_employer_connection_health(
        db_path, progress.validated_employer_id
    )
    if health.state != "success":
        raise ValueError("Test the setup again after changing company settings.")
    with connect_database(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE setup_progress
            SET current_step = ?,
                completed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE singleton_id = 1
              AND current_step = ?
              AND completed_at IS NULL
            """,
            (COMPLETE, REVIEW),
        )
    if cursor.rowcount != 1:
        raise ValueError("Review the setup before finishing.")


def incomplete_setup_destination(
    database_path: str | Path,
) -> str | None:
    """Return the endpoint for an interrupted incomplete setup."""

    progress = get_setup_progress(database_path)
    if progress is None or progress.complete:
        return None
    return {
        PROFILE: "new_profile_page",
        RESUME: "setup_resume",
        FIT: "setup_job_fit",
        COMPANIES: "setup_companies",
        REVIEW: "setup_review",
    }.get(progress.current_step)
