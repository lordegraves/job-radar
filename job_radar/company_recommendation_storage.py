"""Persist recommendation results and feedback independently per profile."""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from job_radar.company_recommendation_models import (
    DISMISSED,
    MAYBE_LATER,
    NEW,
    NOT_RELEVANT,
)
from job_radar.database import connect_database
from job_radar.storage import initialize_database


def save_recommendation(
    database_path: str | Path,
    *,
    profile_id: str,
    employer_id: str,
    score: int,
    evidence: tuple[str, ...],
    availability_state: str,
) -> None:
    """Refresh recommendation evidence without erasing user feedback."""

    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.execute(
            """
            INSERT INTO company_recommendations (
                profile_id, employer_id, recommendation_score, evidence_json,
                availability_state
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(profile_id, employer_id) DO UPDATE SET
                recommendation_score = excluded.recommendation_score,
                evidence_json = excluded.evidence_json,
                availability_state = excluded.availability_state,
                last_evaluated_at = CURRENT_TIMESTAMP
            """,
            (
                profile_id,
                employer_id,
                score,
                json.dumps(evidence),
                availability_state,
            ),
        )


def load_visible_rows(
    database_path: str | Path,
    profile_id: str,
) -> tuple[sqlite3.Row, ...]:
    """Load visible recommendations after applying durable feedback."""

    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT recommendation.*, employer.name AS employer_name
            FROM company_recommendations AS recommendation
            INNER JOIN employer_sources AS employer
              ON employer.employer_id = recommendation.employer_id
            LEFT JOIN profile_company_associations AS assignment
              ON assignment.profile_id = recommendation.profile_id
             AND assignment.company_id = recommendation.employer_id
            WHERE recommendation.profile_id = ?
              AND assignment.company_id IS NULL
              AND (
                    recommendation.recommendation_state = ?
                 OR (
                        recommendation.recommendation_state IN (?, ?)
                    AND recommendation.hidden_until <= CURRENT_TIMESTAMP
                 )
              )
            ORDER BY recommendation.recommendation_score DESC,
                     employer.name COLLATE NOCASE,
                     recommendation.employer_id
            """,
            (profile_id, NEW, MAYBE_LATER, DISMISSED),
        ).fetchall()
    return tuple(rows)


def set_feedback(
    database_path: str | Path,
    *,
    profile_id: str,
    employer_id: str,
    state: str,
) -> bool:
    """Save feedback only for the named profile and recommendation."""

    if state not in {MAYBE_LATER, DISMISSED, NOT_RELEVANT}:
        raise ValueError("Choose a supported recommendation response.")
    days = 30 if state == MAYBE_LATER else 90 if state == DISMISSED else None
    hidden_until = (
        (datetime.now(UTC) + timedelta(days=days)).isoformat()
        if days is not None
        else None
    )
    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE company_recommendations
            SET recommendation_state = ?, hidden_until = ?
            WHERE profile_id = ? AND employer_id = ?
            """,
            (state, hidden_until, profile_id, employer_id),
        )
    return cursor.rowcount == 1


def mark_added(
    database_path: str | Path,
    *,
    profile_id: str,
    employer_id: str,
) -> None:
    """Record that a profile deliberately accepted a recommendation."""

    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.execute(
            """
            UPDATE company_recommendations
            SET recommendation_state = ?, hidden_until = NULL
            WHERE profile_id = ? AND employer_id = ?
            """,
            ("ADDED", profile_id, employer_id),
        )
