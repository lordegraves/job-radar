"""Persist app-owned employer sources without rewriting YAML configuration."""

import json
import sqlite3
from pathlib import Path
from typing import Any

from job_radar.database import connect_database
from job_radar.domain_errors import EmployerInUseError
from job_radar.employer_models import EmployerSource, ProfileEmployerAssignment
from job_radar.storage import initialize_database


class EmployerStorageError(RuntimeError):
    """Raised when stored employer configuration cannot be reconstructed."""


def upsert_employer_source(
    database_path: str | Path,
    employer: EmployerSource,
) -> EmployerSource:
    """Create or replace one app-owned employer source."""

    db_path = initialize_database(database_path)

    with connect_database(db_path) as connection:
        connection.execute(
            """
            INSERT INTO employer_sources (
                employer_id,
                name,
                source_type,
                enabled,
                source_config_json,
                notes,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(employer_id) DO UPDATE SET
                name = excluded.name,
                source_type = excluded.source_type,
                enabled = excluded.enabled,
                source_config_json = excluded.source_config_json,
                notes = excluded.notes,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                employer.employer_id,
                employer.name.strip(),
                employer.source_type,
                int(employer.enabled),
                _dump_source_config(employer.source_config),
                employer.notes,
            ),
        )

    return employer


def get_employer_source(
    database_path: str | Path,
    employer_id: str,
) -> EmployerSource | None:
    """Load one app-owned employer source by stable ID."""

    db_path = initialize_database(database_path)

    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT *
            FROM employer_sources
            WHERE employer_id = ?
            """,
            (employer_id,),
        ).fetchone()

    if row is None:
        return None

    return _row_to_employer(row)


def list_employer_sources(
    database_path: str | Path,
    *,
    enabled_only: bool = False,
) -> list[EmployerSource]:
    """List app-owned employer sources in stable user-facing order."""

    db_path = initialize_database(database_path)
    query = "SELECT * FROM employer_sources"
    parameters: tuple[object, ...] = ()

    if enabled_only:
        query += " WHERE enabled = ?"
        parameters = (1,)

    query += " ORDER BY name COLLATE NOCASE, employer_id"

    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, parameters).fetchall()

    return [_row_to_employer(row) for row in rows]


def list_profile_employer_assignments(
    database_path: str | Path,
    profile_id: str,
) -> list[ProfileEmployerAssignment]:
    """List one profile's employer assignments in stable employer order."""

    db_path = initialize_database(database_path)

    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                association.profile_id,
                association.company_id,
                association.enabled
            FROM profile_company_associations AS association
            INNER JOIN employer_sources AS employer
                ON employer.employer_id = association.company_id
            WHERE association.profile_id = ?
            ORDER BY employer.name COLLATE NOCASE, association.company_id
            """,
            (profile_id,),
        ).fetchall()

    return [
        ProfileEmployerAssignment(
            profile_id=row["profile_id"],
            employer_id=row["company_id"],
            enabled=bool(row["enabled"]),
        )
        for row in rows
    ]


def is_profile_employer_enabled(
    database_path: str | Path,
    profile_id: str,
    employer_id: str,
) -> bool:
    """Return whether one employer is assigned and enabled for a profile."""

    db_path = initialize_database(database_path)

    with connect_database(db_path) as connection:
        row = connection.execute(
            """
            SELECT enabled
            FROM profile_company_associations
            WHERE profile_id = ?
              AND company_id = ?
            """,
            (
                profile_id,
                employer_id,
            ),
        ).fetchone()

    return row is not None and bool(row[0])


def set_profile_employer_enabled(
    database_path: str | Path,
    profile_id: str,
    employer_id: str,
    *,
    enabled: bool,
) -> bool:
    """Update one existing profile employer assignment's scanning state."""

    if not isinstance(enabled, bool):
        raise ValueError("profile employer enabled state must be a boolean")

    db_path = initialize_database(database_path)

    with connect_database(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE profile_company_associations
            SET enabled = ?
            WHERE profile_id = ?
              AND company_id = ?
            """,
            (
                int(enabled),
                profile_id,
                employer_id,
            ),
        )

    return cursor.rowcount > 0


def assign_employer_to_profile(
    database_path: str | Path,
    profile_id: str,
    employer_id: str,
) -> bool:
    """Assign a global employer source to one managed profile."""

    db_path = initialize_database(database_path)

    with connect_database(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO profile_company_associations (
                profile_id,
                company_id
            )
            VALUES (?, ?)
            """,
            (
                profile_id,
                employer_id,
            ),
        )

    return cursor.rowcount > 0


def unassign_employer_from_profile(
    database_path: str | Path,
    profile_id: str,
    employer_id: str,
) -> bool:
    """Remove one employer assignment without deleting the global source."""

    db_path = initialize_database(database_path)

    with connect_database(db_path) as connection:
        cursor = connection.execute(
            """
            DELETE FROM profile_company_associations
            WHERE profile_id = ?
              AND company_id = ?
            """,
            (
                profile_id,
                employer_id,
            ),
        )

    return cursor.rowcount > 0


def delete_employer_source(
    database_path: str | Path,
    employer_id: str,
) -> bool:
    """Delete only an unused employer with no profile or job references."""

    db_path = initialize_database(database_path)

    with connect_database(db_path) as connection:
        assignment = connection.execute(
            """
            SELECT 1
            FROM profile_company_associations
            WHERE company_id = ?
            LIMIT 1
            """,
            (employer_id,),
        ).fetchone()
        collected_job = connection.execute(
            """
            SELECT 1
            FROM job_postings
            WHERE company_key = ?
            LIMIT 1
            """,
            (employer_id,),
        ).fetchone()
        if assignment is not None or collected_job is not None:
            raise EmployerInUseError(
                "Employer records with profile or job history references "
                "cannot be permanently deleted."
            )
        cursor = connection.execute(
            "DELETE FROM employer_sources WHERE employer_id = ?",
            (employer_id,),
        )

    return cursor.rowcount > 0


def _dump_source_config(source_config: dict[str, Any]) -> str:
    try:
        return json.dumps(
            source_config,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise EmployerStorageError(
            "employer source configuration is not JSON serializable"
        ) from error


def _row_to_employer(row: sqlite3.Row) -> EmployerSource:
    try:
        source_config = json.loads(row["source_config_json"])

        if not isinstance(source_config, dict):
            raise ValueError("stored employer source config must be a mapping")

        return EmployerSource(
            employer_id=row["employer_id"],
            name=row["name"],
            source_type=row["source_type"],
            enabled=bool(row["enabled"]),
            source_config=source_config,
            notes=row["notes"],
        )
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise EmployerStorageError(
            f"stored employer source is invalid: {row['employer_id']}"
        ) from error
