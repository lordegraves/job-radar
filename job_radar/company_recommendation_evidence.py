"""Aggregate bounded, profile-owned job evidence for company recommendations."""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from job_radar.database import connect_database
from job_radar.compensation import evaluate_compensation
from job_radar.eligibility import evaluate_workplace_eligibility
from job_radar.models import JobPosting
from job_radar.profile_models import ManagedProfile
from job_radar.storage import initialize_database


DEFAULT_RECENCY_DAYS = 90
MAX_RECENT_POSTINGS_PER_EMPLOYER = 500


@dataclass(frozen=True)
class EmployerJobEvidence:
    """Summarize recent role evidence without retaining job descriptions."""

    relevant_jobs: int = 0
    strong_matches: int = 0
    remote_compatible_jobs: int = 0
    location_conflicts: int = 0
    compensation_below_floor: int = 0
    compensation_known: int = 0
    newest_seen_at: str | None = None

    @property
    def has_evidence(self) -> bool:
        return self.relevant_jobs > 0


def aggregate_employer_job_evidence(
    database_path: str | Path,
    *,
    profile: ManagedProfile,
    employer_id: str,
    recency_days: int = DEFAULT_RECENCY_DAYS,
    max_postings: int = MAX_RECENT_POSTINGS_PER_EMPLOYER,
) -> EmployerJobEvidence:
    """Evaluate only recent jobs seen during scans owned by this profile."""

    if recency_days <= 0 or max_postings <= 0:
        raise ValueError("recommendation evidence bounds must be positive")
    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT posting.company_key, posting.source_type,
                   posting.source_job_id, posting.source_url, posting.title,
                   posting.location, posting.remote_status,
                   posting.salary_text, posting.description,
                   posting.canonical_key, posting.content_hash,
                   MAX(event.created_at) AS newest_seen_at
            FROM job_seen_events AS event
            INNER JOIN scan_runs AS scan ON scan.id = event.scan_run_id
            INNER JOIN job_postings AS posting
              ON posting.id = event.job_posting_id
            WHERE scan.profile_id = ?
              AND posting.company_key = ?
              AND event.created_at >= datetime(
                    'now', '-' || ? || ' days'
              )
            GROUP BY posting.id
            ORDER BY newest_seen_at DESC, posting.id DESC
            LIMIT ?
            """,
            (profile.profile_id, employer_id, recency_days, max_postings),
        ).fetchall()

    target_phrases = _target_phrases(profile)
    target_tokens = {
        token
        for phrase in target_phrases
        for token in _tokens(phrase)
        if len(token) >= 3
    }
    relevant = 0
    strong = 0
    remote = 0
    location_conflicts = 0
    compensation_below_floor = 0
    compensation_known = 0
    newest = rows[0]["newest_seen_at"] if rows else None
    accepts_remote = any(
        value.casefold() == "remote"
        for value in profile.preferences.work_arrangements
    )
    for row in rows:
        title = str(row["title"])
        title_folded = title.casefold()
        title_tokens = _tokens(title)
        overlap = target_tokens & title_tokens
        is_relevant = bool(overlap) or any(
            phrase.casefold() in title_folded for phrase in target_phrases
        )
        if not is_relevant:
            continue
        relevant += 1
        required_overlap = max(1, min(2, len(target_tokens)))
        if any(
            phrase.casefold() in title_folded for phrase in target_phrases
        ) or len(overlap) >= required_overlap:
            strong += 1
        posting = _row_to_posting(row)
        workplace = evaluate_workplace_eligibility(
            posting, profile.preferences
        )
        workplace_codes = {
            reason.code for reason in workplace.reasons
        } if workplace is not None else set()
        if accepts_remote and "remote_arrangement_selected" in workplace_codes:
            remote += 1
        if workplace_codes & {
            "location_outside_selected_areas",
            "remote_region_outside_selected_areas",
            "workplace_arrangement_not_selected",
        }:
            location_conflicts += 1
        compensation = evaluate_compensation(
            posting.salary_text,
            profile.preferences.compensation_floor_usd,
        )
        if compensation.label != "Unknown":
            compensation_known += 1
        if compensation.label == "Below floor":
            compensation_below_floor += 1
    return EmployerJobEvidence(
        relevant,
        strong,
        remote,
        location_conflicts,
        compensation_below_floor,
        compensation_known,
        newest,
    )


def format_job_evidence(
    evidence: EmployerJobEvidence,
) -> tuple[int, tuple[str, ...]]:
    """Convert evidence into transparent ranking points and explanations."""

    if not evidence.has_evidence:
        return 0, ()
    score = min(evidence.relevant_jobs, 10) * 3
    score += min(evidence.strong_matches, 5) * 5
    score += min(evidence.remote_compatible_jobs, 5) * 2
    score -= min(evidence.location_conflicts, 5) * 4
    if evidence.compensation_known >= 2:
        score -= min(evidence.compensation_below_floor, 5) * 3
    reasons = [
        (
            f"Junior found {evidence.relevant_jobs} recent "
            f"{'job' if evidence.relevant_jobs == 1 else 'jobs'} from this "
            "company that matched your target work."
        )
    ]
    if evidence.strong_matches:
        reasons.append(
            f"{evidence.strong_matches} "
            f"{'was' if evidence.strong_matches == 1 else 'were'} strong "
            "title matches."
        )
    if evidence.remote_compatible_jobs:
        reasons.append(
            f"{evidence.remote_compatible_jobs} matched your Remote preference."
        )
    if evidence.location_conflicts:
        reasons.append(
            f"{evidence.location_conflicts} recent "
            f"{'job had' if evidence.location_conflicts == 1 else 'jobs had'} "
            "a workplace or location conflict."
        )
    if evidence.compensation_known >= 2 and evidence.compensation_below_floor:
        reasons.append(
            f"{evidence.compensation_below_floor} of "
            f"{evidence.compensation_known} jobs with usable pay information "
            "were below this profile's minimum."
        )
    if evidence.newest_seen_at:
        age = _age_in_days(evidence.newest_seen_at)
        if age is not None:
            reasons.append(
                "The newest matching job was "
                + ("seen today." if age == 0 else f"seen {age} days ago.")
            )
    return score, tuple(reasons)


def _target_phrases(profile: ManagedProfile) -> tuple[str, ...]:
    return tuple(
        value.strip()
        for value in (
            *profile.preferences.target_roles,
            *(item.label for item in profile.preferences.occupation_selections),
        )
        if value.strip()
    )


def _tokens(value: str) -> set[str]:
    return {
        "".join(character for character in token.casefold() if character.isalnum())
        for token in value.replace("/", " ").replace("-", " ").split()
    }


def _age_in_days(value: str) -> int | None:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return max(0, (datetime.now(UTC) - timestamp).days)


def _row_to_posting(row: sqlite3.Row) -> JobPosting:
    return JobPosting(
        company_key=row["company_key"],
        company_name=row["company_key"],
        source_type=row["source_type"],
        source_job_id=row["source_job_id"],
        source_url=row["source_url"],
        title=row["title"],
        location=row["location"],
        remote_status=row["remote_status"],
        salary_text=row["salary_text"],
        description=row["description"],
        canonical_key=row["canonical_key"],
        content_hash=row["content_hash"],
    )
