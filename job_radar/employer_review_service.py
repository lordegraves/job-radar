"""Resolve pending employer submissions through guarded Administration."""

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from job_radar.company_catalog_query_service import evaluate_employer_availability
from job_radar.database import connect_database
from job_radar.employer_storage import (
    get_employer_source,
    list_profile_employer_assignments,
)
from job_radar.storage import initialize_database


PENDING = "PENDING"
MATCHED_EXISTING = "MATCHED_EXISTING"
CONFIGURED_NEW = "CONFIGURED_NEW"
UNSUPPORTED = "UNSUPPORTED"
REJECTED = "REJECTED"
CANCELLED = "CANCELLED"
REVIEW_STATUSES = (
    PENDING,
    MATCHED_EXISTING,
    CONFIGURED_NEW,
    UNSUPPORTED,
    REJECTED,
    CANCELLED,
)


@dataclass(frozen=True)
class EmployerReviewRequest:
    """Present one safe review request without raw collector failures."""

    request_id: str
    submitted_company_name: str | None
    submitted_careers_url: str | None
    requesting_profile_id: str
    requesting_profile_name: str
    detection_result: str
    possible_employer_ids: tuple[str, ...]
    safe_summary: str
    status: str
    created_at: str
    reviewed_at: str | None
    resolved_employer_id: str | None

    @property
    def company_label(self) -> str:
        return (
            self.submitted_company_name
            or self.submitted_careers_url
            or "Unnamed company"
        )

    @property
    def detection_label(self) -> str:
        return {
            "PENDING_REVIEW": "Needs setup",
            "UNSUPPORTED_SITE": "Site not recognized",
            "AMBIGUOUS_MATCH": "Possible duplicate",
        }.get(self.detection_result, "Needs review")


@dataclass(frozen=True)
class ProfileReviewState:
    """Show a normal user only the safe state of their own submission."""

    company_label: str
    state_label: str
    explanation: str


class EmployerReviewError(ValueError):
    """Explain a review action that cannot be completed safely."""


def list_review_requests(
    database_path: str | Path,
    *,
    status: str = PENDING,
) -> tuple[EmployerReviewRequest, ...]:
    """List review requests in stable oldest-first order."""

    db_path = initialize_database(database_path)
    query = """
        SELECT request.*, profile.display_name AS profile_name
        FROM employer_review_requests AS request
        INNER JOIN profiles AS profile
          ON profile.profile_id = request.requesting_profile_id
    """
    parameters: tuple[str, ...] = ()
    if status:
        query += " WHERE request.status = ?"
        parameters = (status,)
    query += " ORDER BY request.created_at, request.request_id"
    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, parameters).fetchall()
    return tuple(_row_to_request(row) for row in rows)


def list_profile_review_states(
    database_path: str | Path,
    profile_id: str,
) -> tuple[ProfileReviewState, ...]:
    """Return safe unresolved/recent states for one profile only."""

    states = []
    assigned_ids = {
        item.employer_id
        for item in list_profile_employer_assignments(database_path, profile_id)
    }
    for review in list_review_requests(database_path, status=""):
        if review.requesting_profile_id != profile_id:
            continue
        if review.status == PENDING:
            states.append(
                ProfileReviewState(
                    review.company_label,
                    "Setup pending",
                    "An administrator still needs to configure this company.",
                )
            )
        elif review.status == UNSUPPORTED:
            states.append(
                ProfileReviewState(
                    review.company_label,
                    "Unsupported",
                    "Junior cannot currently scan this company site.",
                )
            )
        elif (
            review.status in {MATCHED_EXISTING, CONFIGURED_NEW}
            and review.resolved_employer_id
            and review.resolved_employer_id not in assigned_ids
        ):
            employer = get_employer_source(
                database_path, review.resolved_employer_id
            )
            if employer and evaluate_employer_availability(employer).can_assign:
                states.append(
                    ProfileReviewState(
                        review.company_label,
                        "Ready to add",
                        "The company is configured and can now be added.",
                    )
                )
    return tuple(states)


def get_review_request(
    database_path: str | Path,
    request_id: str,
) -> EmployerReviewRequest | None:
    """Load one review request by its opaque ID."""

    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT request.*, profile.display_name AS profile_name
            FROM employer_review_requests AS request
            INNER JOIN profiles AS profile
              ON profile.profile_id = request.requesting_profile_id
            WHERE request.request_id = ?
            """,
            (request_id,),
        ).fetchone()
    return _row_to_request(row) if row is not None else None


def resolve_to_existing_employer(
    database_path: str | Path,
    request_id: str,
    employer_id: str,
    *,
    assign_to_profile: bool,
) -> EmployerReviewRequest:
    """Resolve to an existing employer and optionally assign it atomically."""

    db_path = initialize_database(database_path)
    request = _require_pending(db_path, request_id)
    employer = get_employer_source(db_path, employer_id)
    if employer is None:
        raise EmployerReviewError("Choose an employer that still exists.")

    assignment_completed = False
    if assign_to_profile:
        availability = evaluate_employer_availability(employer)
        if not availability.can_assign:
            raise EmployerReviewError(
                "This employer must be available and fully configured before "
                "it can be assigned."
            )

    with connect_database(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        if assign_to_profile:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO profile_company_associations (
                    profile_id, company_id, enabled
                ) VALUES (?, ?, 1)
                """,
                (request.requesting_profile_id, employer_id),
            )
            assignment_completed = cursor.rowcount > 0
        _finish_request(
            connection,
            request=request,
            status=MATCHED_EXISTING,
            employer_id=employer_id,
            operation="match_existing",
            assignment_requested=assign_to_profile,
            assignment_completed=assignment_completed,
        )
    return get_review_request(db_path, request_id)  # type: ignore[return-value]


def mark_review_status(
    database_path: str | Path,
    request_id: str,
    status: str,
) -> EmployerReviewRequest:
    """Mark a pending request unsupported, rejected, or duplicate/cancelled."""

    if status not in {UNSUPPORTED, REJECTED, CANCELLED}:
        raise EmployerReviewError("Choose a supported review decision.")
    db_path = initialize_database(database_path)
    request = _require_pending(db_path, request_id)
    with connect_database(db_path) as connection:
        _finish_request(
            connection,
            request=request,
            status=status,
            employer_id=None,
            operation=status.casefold(),
            assignment_requested=False,
            assignment_completed=False,
        )
    return get_review_request(db_path, request_id)  # type: ignore[return-value]


def mark_configured_new(
    database_path: str | Path,
    request_id: str,
    employer_id: str,
) -> EmployerReviewRequest:
    """Link an administrator-created employer back to its review request."""

    db_path = initialize_database(database_path)
    request = _require_pending(db_path, request_id)
    if get_employer_source(db_path, employer_id) is None:
        raise EmployerReviewError("The configured employer no longer exists.")
    with connect_database(db_path) as connection:
        _finish_request(
            connection,
            request=request,
            status=CONFIGURED_NEW,
            employer_id=employer_id,
            operation="configure_new",
            assignment_requested=False,
            assignment_completed=False,
        )
    return get_review_request(db_path, request_id)  # type: ignore[return-value]


def assign_resolved_employer(
    database_path: str | Path,
    request_id: str,
) -> bool:
    """Assign a resolved, globally available employer to the requesting profile."""

    db_path = initialize_database(database_path)
    request = get_review_request(db_path, request_id)
    if request is None or request.resolved_employer_id is None:
        raise EmployerReviewError("This review has no resolved employer to assign.")
    employer = get_employer_source(db_path, request.resolved_employer_id)
    if employer is None or not evaluate_employer_availability(employer).can_assign:
        raise EmployerReviewError(
            "Validate and enable this employer before assigning it."
        )
    with connect_database(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO profile_company_associations (
                profile_id, company_id, enabled
            ) VALUES (?, ?, 1)
            """,
            (request.requesting_profile_id, request.resolved_employer_id),
        )
        connection.execute(
            """
            INSERT INTO employer_review_audit (
                request_id, operation, previous_status, new_status,
                resolved_employer_id, assignment_requested,
                assignment_completed
            ) VALUES (?, 'assign_resolved', ?, ?, ?, 1, ?)
            """,
            (
                request_id,
                request.status,
                request.status,
                request.resolved_employer_id,
                int(cursor.rowcount > 0),
            ),
        )
    return cursor.rowcount > 0


def list_review_audit(
    database_path: str | Path,
    request_id: str,
) -> tuple[dict[str, object], ...]:
    """Return the sanitized decision history for one request."""

    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT operation, previous_status, new_status,
                   resolved_employer_id, assignment_requested,
                   assignment_completed, created_at
            FROM employer_review_audit
            WHERE request_id = ?
            ORDER BY audit_id DESC
            """,
            (request_id,),
        ).fetchall()
    return tuple(dict(row) for row in rows)


def _require_pending(
    database_path: Path,
    request_id: str,
) -> EmployerReviewRequest:
    request = get_review_request(database_path, request_id)
    if request is None:
        raise EmployerReviewError("That review request no longer exists.")
    if request.status != PENDING:
        raise EmployerReviewError("That review request has already been resolved.")
    return request


def _finish_request(
    connection: sqlite3.Connection,
    *,
    request: EmployerReviewRequest,
    status: str,
    employer_id: str | None,
    operation: str,
    assignment_requested: bool,
    assignment_completed: bool,
) -> None:
    cursor = connection.execute(
        """
        UPDATE employer_review_requests
        SET status = ?, reviewed_at = CURRENT_TIMESTAMP,
            resolved_employer_id = ?
        WHERE request_id = ? AND status = 'PENDING'
        """,
        (status, employer_id, request.request_id),
    )
    if cursor.rowcount != 1:
        raise EmployerReviewError("That review request was resolved elsewhere.")
    connection.execute(
        """
        INSERT INTO employer_review_audit (
            request_id, operation, previous_status, new_status,
            resolved_employer_id, assignment_requested,
            assignment_completed
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            request.request_id,
            operation,
            request.status,
            status,
            employer_id,
            int(assignment_requested),
            int(assignment_completed),
        ),
    )


def _row_to_request(row: sqlite3.Row) -> EmployerReviewRequest:
    try:
        possible = json.loads(row["possible_employer_ids_json"])
    except (TypeError, json.JSONDecodeError):
        possible = []
    return EmployerReviewRequest(
        request_id=row["request_id"],
        submitted_company_name=row["submitted_company_name"],
        submitted_careers_url=row["submitted_careers_url"],
        requesting_profile_id=row["requesting_profile_id"],
        requesting_profile_name=row["profile_name"],
        detection_result=row["detection_result"],
        possible_employer_ids=tuple(
            str(value) for value in possible if isinstance(value, str)
        ),
        safe_summary=row["safe_summary"],
        status=row["status"],
        created_at=row["created_at"],
        reviewed_at=row["reviewed_at"],
        resolved_employer_id=row["resolved_employer_id"],
    )
