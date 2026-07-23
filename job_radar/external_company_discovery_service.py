"""Recommend bounded employers found outside the local Employer Catalog."""

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from job_radar.config import SUPPORTED_SOURCE_TYPES
from job_radar.database import connect_database
from job_radar.employer_resolution_service import (
    AMBIGUOUS_MATCH,
    MATCHED_EXISTING,
    PENDING_REVIEW,
    EmployerResolutionResult,
    normalize_company_name,
    resolve_employer_submission,
)
from job_radar.employer_storage import list_employer_sources
from job_radar.profile_storage import get_active_profile
from job_radar.storage import initialize_database


READY_TO_ADD = "READY_TO_ADD"
NEEDS_ADMIN_REVIEW = "NEEDS_ADMIN_REVIEW"
UNSUPPORTED = "UNSUPPORTED"
AMBIGUOUS = "AMBIGUOUS"
DISCOVERY_WINDOW_DAYS = 90
MAX_DISCOVERY_EMPLOYERS = 50


@dataclass(frozen=True)
class ExternalCompanyCandidate:
    """Present one fresh outside-catalog employer without technical details."""

    profile_id: str
    candidate_key: str
    proposed_name: str
    proposed_careers_url: str | None
    discovery_source: str
    evidence: tuple[str, ...]
    potential_existing_match: str | None
    detection_result: str
    confidence: str
    readiness_state: str
    discovered_at: str


class ExternalCompanyDiscoveryError(ValueError):
    """Explain a stale or cross-profile external-candidate action."""


def build_external_company_candidates(
    database_path: str | Path,
) -> tuple[ExternalCompanyCandidate, ...]:
    """Find recent profile-owned job employers absent from the catalog."""

    db_path = initialize_database(database_path)
    profile = get_active_profile(db_path)
    if profile is None:
        return ()
    target_tokens = {
        token
        for value in (
            *profile.preferences.target_roles,
            *(item.label for item in profile.preferences.occupation_selections),
        )
        for token in _tokens(value)
        if len(token) >= 3
    }
    if not target_tokens:
        return ()
    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT posting.company_key, company.name AS company_name,
                   posting.source_type, COUNT(DISTINCT posting.id) AS jobs,
                   MAX(event.created_at) AS newest_seen_at,
                   GROUP_CONCAT(DISTINCT posting.title) AS titles
            FROM job_seen_events AS event
            INNER JOIN scan_runs AS scan ON scan.id = event.scan_run_id
            INNER JOIN job_postings AS posting
              ON posting.id = event.job_posting_id
            INNER JOIN companies AS company
              ON company.company_key = posting.company_key
            LEFT JOIN employer_sources AS employer
              ON employer.employer_id = posting.company_key
            WHERE scan.profile_id = ?
              AND employer.employer_id IS NULL
              AND event.created_at >= datetime(
                    'now', '-' || ? || ' days'
              )
            GROUP BY posting.company_key, company.name, posting.source_type
            ORDER BY newest_seen_at DESC, company.name COLLATE NOCASE
            LIMIT ?
            """,
            (
                profile.profile_id,
                DISCOVERY_WINDOW_DAYS,
                MAX_DISCOVERY_EMPLOYERS,
            ),
        ).fetchall()

    candidates = []
    for row in rows:
        titles = tuple(
            title.strip()
            for title in str(row["titles"] or "").split(",")
            if title.strip()
        )
        relevant = sum(
            1 for title in titles if target_tokens & _tokens(title)
        )
        if target_tokens and relevant == 0:
            continue
        evidence = (
            f"Junior found {int(row['jobs'])} recent "
            f"{'job' if int(row['jobs']) == 1 else 'jobs'} from this employer.",
            (
                f"{relevant} matched your target work."
                if target_tokens
                else "The employer appeared in this profile's recent job data."
            ),
        )
        existing = _find_existing_name_match(db_path, row["company_name"])
        supported = str(row["source_type"]) in SUPPORTED_SOURCE_TYPES
        readiness = (
            MATCHED_EXISTING
            if existing is not None
            else NEEDS_ADMIN_REVIEW
            if supported
            else UNSUPPORTED
        )
        candidate = ExternalCompanyCandidate(
            profile_id=profile.profile_id,
            candidate_key=str(row["company_key"]),
            proposed_name=str(row["company_name"]),
            proposed_careers_url=None,
            discovery_source="Recent jobs found for this profile",
            evidence=evidence,
            potential_existing_match=existing,
            detection_result=(
                "Existing catalog match"
                if existing is not None
                else "Recognized job source"
                if supported
                else "Source needs review"
            ),
            confidence="High" if relevant >= 2 else "Moderate",
            readiness_state=readiness,
            discovered_at=str(row["newest_seen_at"]),
        )
        _save_candidate(db_path, candidate)
        candidates.append(candidate)
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                0 if item.confidence == "High" else 1,
                item.proposed_name.casefold(),
                item.candidate_key,
            ),
        )
    )


def send_external_candidate_to_review(
    database_path: str | Path,
    *,
    profile_id: str,
    candidate_key: str,
) -> EmployerResolutionResult:
    """Resolve or queue one candidate without silently creating an employer."""

    db_path = initialize_database(database_path)
    profile = get_active_profile(db_path)
    if profile is None or profile.profile_id != profile_id:
        raise ExternalCompanyDiscoveryError(
            "This company suggestion does not belong to the active profile."
        )
    candidate = _get_candidate(db_path, profile_id, candidate_key)
    if candidate is None:
        raise ExternalCompanyDiscoveryError(
            "That company suggestion is no longer available."
        )
    result = resolve_employer_submission(
        db_path,
        profile_id=profile_id,
        company_name=candidate.proposed_name,
        careers_url=candidate.proposed_careers_url or "",
    )
    readiness = {
        MATCHED_EXISTING: MATCHED_EXISTING,
        PENDING_REVIEW: NEEDS_ADMIN_REVIEW,
        AMBIGUOUS_MATCH: AMBIGUOUS,
    }.get(result.status, NEEDS_ADMIN_REVIEW)
    with connect_database(db_path) as connection:
        connection.execute(
            """
            UPDATE external_employer_discoveries
            SET readiness_state = ?, possible_employer_id = ?,
                review_request_id = ?, last_evaluated_at = CURRENT_TIMESTAMP
            WHERE profile_id = ? AND candidate_key = ?
            """,
            (
                readiness,
                result.employer_id,
                result.review_request_id,
                profile_id,
                candidate_key,
            ),
        )
    return result


def _save_candidate(database_path: Path, candidate: ExternalCompanyCandidate) -> None:
    with connect_database(database_path) as connection:
        connection.execute(
            """
            INSERT INTO external_employer_discoveries (
                profile_id, candidate_key, proposed_name,
                proposed_careers_url, discovery_source, evidence_json,
                possible_employer_id, detection_result, confidence,
                readiness_state, discovered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_id, candidate_key) DO UPDATE SET
                proposed_name = excluded.proposed_name,
                proposed_careers_url = excluded.proposed_careers_url,
                discovery_source = excluded.discovery_source,
                evidence_json = excluded.evidence_json,
                possible_employer_id = excluded.possible_employer_id,
                detection_result = excluded.detection_result,
                confidence = excluded.confidence,
                readiness_state = CASE
                    WHEN external_employer_discoveries.review_request_id IS NULL
                    THEN excluded.readiness_state
                    ELSE external_employer_discoveries.readiness_state
                END,
                discovered_at = excluded.discovered_at,
                last_evaluated_at = CURRENT_TIMESTAMP
            """,
            (
                candidate.profile_id,
                candidate.candidate_key,
                candidate.proposed_name,
                candidate.proposed_careers_url,
                candidate.discovery_source,
                json.dumps(candidate.evidence),
                candidate.potential_existing_match,
                candidate.detection_result,
                candidate.confidence,
                candidate.readiness_state,
                candidate.discovered_at,
            ),
        )


def _get_candidate(
    database_path: Path,
    profile_id: str,
    candidate_key: str,
) -> ExternalCompanyCandidate | None:
    with connect_database(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT * FROM external_employer_discoveries
            WHERE profile_id = ? AND candidate_key = ?
            """,
            (profile_id, candidate_key),
        ).fetchone()
    if row is None:
        return None
    return ExternalCompanyCandidate(
        profile_id=row["profile_id"],
        candidate_key=row["candidate_key"],
        proposed_name=row["proposed_name"],
        proposed_careers_url=row["proposed_careers_url"],
        discovery_source=row["discovery_source"],
        evidence=tuple(json.loads(row["evidence_json"])),
        potential_existing_match=row["possible_employer_id"],
        detection_result=row["detection_result"],
        confidence=row["confidence"],
        readiness_state=row["readiness_state"],
        discovered_at=row["discovered_at"],
    )


def _find_existing_name_match(
    database_path: Path,
    name: str,
) -> str | None:
    normalized = normalize_company_name(name)
    matches = [
        employer.employer_id
        for employer in list_employer_sources(database_path)
        if normalize_company_name(employer.name) == normalized
    ]
    with connect_database(database_path) as connection:
        alias_rows = connection.execute(
            """
            SELECT employer_id FROM employer_aliases
            WHERE normalized_alias = ?
            ORDER BY employer_id
            """,
            (normalized,),
        ).fetchall()
    matches.extend(str(row[0]) for row in alias_rows)
    unique_matches = sorted(set(matches))
    return unique_matches[0] if len(unique_matches) == 1 else None


def _tokens(value: str) -> set[str]:
    return {
        "".join(character for character in token.casefold() if character.isalnum())
        for token in value.replace("/", " ").replace("-", " ").split()
    }
