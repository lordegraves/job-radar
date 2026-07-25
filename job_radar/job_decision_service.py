"""Store profile-owned job bookmarks and passes outside application history."""

from dataclasses import dataclass
from pathlib import Path

from job_radar.database import connect_database
from job_radar.storage import initialize_database


DECISION_SAVED = "saved"
DECISION_PASSED = "passed"
JOB_DECISIONS = {DECISION_SAVED, DECISION_PASSED}


class JobDecisionError(ValueError):
    """Explain an invalid job decision without exposing storage details."""


@dataclass(frozen=True)
class JobDecision:
    profile_id: str
    job_radar_id: str
    decision: str
    company: str
    title: str
    source_url: str | None
    location: str | None
    notes: str | None
    updated_at: str


def save_job_decision(
    database_path: str | Path,
    *,
    profile_id: str,
    job_radar_id: str,
    decision: str,
    company: str,
    title: str,
    source_url: str | None,
    location: str | None,
    notes: str | None = None,
) -> str:
    """Save one explicit choice without creating an application record."""

    if decision not in JOB_DECISIONS:
        raise JobDecisionError("Choose Save for later or Pass.")
    if not profile_id.strip() or not job_radar_id.strip():
        raise JobDecisionError("Junior could not identify this job and profile.")
    if not company.strip() or not title.strip():
        raise JobDecisionError("Junior could not identify this job.")

    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        existing = connection.execute(
            """
            SELECT decision
            FROM profile_job_decisions
            WHERE profile_id = ? AND job_radar_id = ?
            """,
            (profile_id, job_radar_id),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO profile_job_decisions (
                profile_id, job_radar_id, decision, company, title,
                source_url, location, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_id, job_radar_id) DO UPDATE SET
                decision = excluded.decision,
                company = excluded.company,
                title = excluded.title,
                source_url = excluded.source_url,
                location = excluded.location,
                notes = COALESCE(excluded.notes, profile_job_decisions.notes),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                profile_id,
                job_radar_id,
                decision,
                company.strip(),
                title.strip(),
                source_url,
                location,
                notes,
            ),
        )
    return "updated" if existing is not None else "new"


def list_job_decisions(
    database_path: str | Path,
    *,
    profile_id: str,
    decision: str | None = None,
) -> list[JobDecision]:
    db_path = initialize_database(database_path)
    parameters: list[str] = [profile_id]
    where = "profile_id = ?"
    if decision is not None:
        if decision not in JOB_DECISIONS:
            raise JobDecisionError("Unknown job-decision view.")
        where += " AND decision = ?"
        parameters.append(decision)

    with connect_database(db_path) as connection:
        rows = connection.execute(
            f"""
            SELECT profile_id, job_radar_id, decision, company, title,
                   source_url, location, notes, updated_at
            FROM profile_job_decisions
            WHERE {where}
            ORDER BY updated_at DESC, company ASC, title ASC
            """,
            parameters,
        ).fetchall()
    return [JobDecision(*row) for row in rows]


def get_decided_job_ids(
    database_path: str | Path,
    *,
    profile_id: str | None,
) -> set[str]:
    if profile_id is None:
        return set()
    return {
        item.job_radar_id
        for item in list_job_decisions(
            database_path,
            profile_id=profile_id,
        )
    }


def delete_job_decision(
    database_path: str | Path,
    *,
    profile_id: str,
    job_radar_id: str,
) -> bool:
    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        cursor = connection.execute(
            """
            DELETE FROM profile_job_decisions
            WHERE profile_id = ? AND job_radar_id = ?
            """,
            (profile_id, job_radar_id),
        )
    return cursor.rowcount > 0
