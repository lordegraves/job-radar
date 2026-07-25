"""Store profile-owned job bookmarks and passes outside application history."""

from dataclasses import dataclass
from pathlib import Path

from job_radar.database import connect_database
from job_radar.storage import initialize_database


DECISION_SAVED = "saved"
DECISION_PASSED = "passed"
JOB_DECISIONS = {DECISION_SAVED, DECISION_PASSED}
PASS_REASONS = (
    "Location",
    "Compensation",
    "Contract duration",
    "Responsibilities",
    "Experience level",
    "Not interested",
    "Duplicate or stale posting",
    "Other",
)
MAX_JOB_DECISION_NOTES_LENGTH = 300


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
    decision_reason: str | None
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
    decision_reason: str | None = None,
) -> str:
    """Save one explicit choice without creating an application record."""

    if decision not in JOB_DECISIONS:
        raise JobDecisionError("Choose Save for later or Pass.")
    if not profile_id.strip() or not job_radar_id.strip():
        raise JobDecisionError("Junior could not identify this job and profile.")
    if not company.strip() or not title.strip():
        raise JobDecisionError("Junior could not identify this job.")
    normalized_notes = _normalize_notes(notes)
    normalized_reason = _normalize_reason(
        decision=decision,
        decision_reason=decision_reason,
    )

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
                source_url, location, notes, decision_reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_id, job_radar_id) DO UPDATE SET
                decision = excluded.decision,
                company = excluded.company,
                title = excluded.title,
                source_url = excluded.source_url,
                location = excluded.location,
                notes = COALESCE(excluded.notes, profile_job_decisions.notes),
                decision_reason = excluded.decision_reason,
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
                normalized_notes,
                normalized_reason,
            ),
        )
    return "updated" if existing is not None else "new"


def save_job_decisions_bulk(
    database_path: str | Path,
    *,
    profile_id: str,
    jobs: list[dict[str, str | None]],
    decision: str,
    decision_reason: str | None = None,
) -> int:
    """Save a verified group atomically so partial bulk decisions are impossible."""

    if not jobs:
        raise JobDecisionError("Select at least one job.")
    normalized_reason = _normalize_reason(
        decision=decision,
        decision_reason=decision_reason,
    )
    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        for job in jobs:
            job_radar_id = (job.get("job_radar_id") or "").strip()
            company = (job.get("company") or "").strip()
            title = (job.get("title") or "").strip()
            if not profile_id.strip() or not job_radar_id or not company or not title:
                raise JobDecisionError(
                    "Junior could not identify every selected job."
                )
            connection.execute(
                """
                INSERT INTO profile_job_decisions (
                    profile_id, job_radar_id, decision, company, title,
                    source_url, location, notes, decision_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
                ON CONFLICT(profile_id, job_radar_id) DO UPDATE SET
                    decision = excluded.decision,
                    company = excluded.company,
                    title = excluded.title,
                    source_url = excluded.source_url,
                    location = excluded.location,
                    decision_reason = excluded.decision_reason,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    profile_id,
                    job_radar_id,
                    decision,
                    company,
                    title,
                    job.get("source_url"),
                    job.get("location"),
                    normalized_reason,
                ),
            )
    return len(jobs)


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
                   source_url, location, notes, decision_reason, updated_at
            FROM profile_job_decisions
            WHERE {where}
            ORDER BY updated_at DESC, company ASC, title ASC
            """,
            parameters,
        ).fetchall()
    return [JobDecision(*row) for row in rows]


def _normalize_notes(notes: str | None) -> str | None:
    if notes is None:
        return None
    normalized = notes.strip()
    if not normalized:
        return None
    if len(normalized) > MAX_JOB_DECISION_NOTES_LENGTH:
        raise JobDecisionError(
            f"Notes must be {MAX_JOB_DECISION_NOTES_LENGTH} characters or fewer."
        )
    return normalized


def _normalize_reason(
    *,
    decision: str,
    decision_reason: str | None,
) -> str | None:
    if decision not in JOB_DECISIONS:
        raise JobDecisionError("Choose Save for later or Pass.")
    normalized = (decision_reason or "").strip()
    if not normalized:
        return None
    if decision != DECISION_PASSED or normalized not in PASS_REASONS:
        raise JobDecisionError("Choose a listed reason for passing.")
    return normalized


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
