"""Persist app-owned employer sources without rewriting YAML configuration."""

import json
import sqlite3
from pathlib import Path
from typing import Any

from job_radar.database import connect_database
from job_radar.employer_models import EmployerSource
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


def delete_employer_source(
    database_path: str | Path,
    employer_id: str,
) -> bool:
    """Delete one employer source that is not referenced by collected jobs."""

    db_path = initialize_database(database_path)

    with connect_database(db_path) as connection:
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
