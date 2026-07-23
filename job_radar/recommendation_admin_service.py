"""Manage global recommendation metadata without exposing it to normal users."""

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from job_radar.company_recommendation_models import NEW
from job_radar.database import connect_database
from job_radar.employer_resolution_service import normalize_company_name
from job_radar.employer_storage import get_employer_source
from job_radar.profile_storage import get_profile, list_profiles
from job_radar.storage import initialize_database


ELIGIBLE = "eligible"
EXCLUDED = "excluded"
NEEDS_REVIEW = "needs_review"
RETIRED = "retired"
ELIGIBILITY_OPTIONS = (ELIGIBLE, EXCLUDED, NEEDS_REVIEW, RETIRED)


class RecommendationAdminError(ValueError):
    """Explain an invalid or stale recommendation administration action."""


@dataclass(frozen=True)
class RecommendationMetadata:
    """Hold global employer facts used only by recommendation generation."""

    employer_id: str
    aliases: tuple[str, ...] = ()
    industries: tuple[str, ...] = ()
    occupation_families: tuple[str, ...] = ()
    employer_type: str = ""
    geographic_presence: tuple[str, ...] = ()
    remote_hiring_metadata: str = ""
    eligibility: str = ELIGIBLE
    updated_at: str | None = None


@dataclass(frozen=True)
class RecommendationDiagnostic:
    """Present stored profile/employer recommendation facts to an admin."""

    profile_id: str
    employer_id: str
    score: int | None
    positive_evidence: tuple[str, ...]
    negative_evidence: tuple[str, ...]
    feedback_state: str
    availability_state: str
    generated_at: str | None
    last_evaluated_at: str | None


def load_recommendation_metadata(
    database_path: str | Path,
    employer_id: str,
) -> RecommendationMetadata:
    """Load metadata, treating pre-milestone employers as eligible."""

    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT *
            FROM employer_recommendation_metadata
            WHERE employer_id = ?
            """,
            (employer_id,),
        ).fetchone()
        aliases = connection.execute(
            """
            SELECT alias
            FROM employer_aliases
            WHERE employer_id = ?
            ORDER BY alias COLLATE NOCASE
            """,
            (employer_id,),
        ).fetchall()
    if row is None:
        return RecommendationMetadata(
            employer_id=employer_id,
            aliases=tuple(item[0] for item in aliases),
        )
    return RecommendationMetadata(
        employer_id=employer_id,
        aliases=tuple(item[0] for item in aliases),
        industries=_load_string_tuple(row["industries_json"]),
        occupation_families=_load_string_tuple(
            row["occupation_families_json"]
        ),
        employer_type=row["employer_type"],
        geographic_presence=_load_string_tuple(
            row["geographic_presence_json"]
        ),
        remote_hiring_metadata=row["remote_hiring_metadata"],
        eligibility=row["eligibility"],
        updated_at=row["updated_at"],
    )


def update_recommendation_metadata(
    database_path: str | Path,
    employer_id: str,
    *,
    aliases: str,
    industries: str,
    occupation_families: str,
    employer_type: str,
    geographic_presence: str,
    remote_hiring_metadata: str,
    eligibility: str,
) -> RecommendationMetadata:
    """Replace one employer's bounded recommendation metadata and aliases."""

    db_path = initialize_database(database_path)
    if get_employer_source(db_path, employer_id) is None:
        raise RecommendationAdminError("That employer no longer exists.")
    if eligibility not in ELIGIBILITY_OPTIONS:
        raise RecommendationAdminError("Choose a valid eligibility state.")
    parsed_aliases = _lines(aliases)
    normalized_aliases = [normalize_company_name(item) for item in parsed_aliases]
    if len(normalized_aliases) != len(set(normalized_aliases)):
        raise RecommendationAdminError("Each employer alias must be unique.")
    try:
        with connect_database(db_path) as connection:
            connection.execute(
                """
                INSERT INTO employer_recommendation_metadata (
                    employer_id, industries_json,
                    occupation_families_json, employer_type,
                    geographic_presence_json, remote_hiring_metadata,
                    eligibility
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(employer_id) DO UPDATE SET
                    industries_json = excluded.industries_json,
                    occupation_families_json =
                        excluded.occupation_families_json,
                    employer_type = excluded.employer_type,
                    geographic_presence_json =
                        excluded.geographic_presence_json,
                    remote_hiring_metadata =
                        excluded.remote_hiring_metadata,
                    eligibility = excluded.eligibility,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    employer_id,
                    json.dumps(_lines(industries)),
                    json.dumps(_lines(occupation_families)),
                    " ".join(employer_type.strip().split()),
                    json.dumps(_lines(geographic_presence)),
                    " ".join(remote_hiring_metadata.strip().split()),
                    eligibility,
                ),
            )
            connection.execute(
                "DELETE FROM employer_aliases WHERE employer_id = ?",
                (employer_id,),
            )
            connection.executemany(
                """
                INSERT INTO employer_aliases (
                    employer_id, alias, normalized_alias
                ) VALUES (?, ?, ?)
                """,
                [
                    (employer_id, alias, normalized)
                    for alias, normalized in zip(
                        parsed_aliases, normalized_aliases, strict=True
                    )
                ],
            )
            _audit(connection, employer_id, None, "update_metadata")
    except sqlite3.IntegrityError as error:
        raise RecommendationAdminError(
            "An alias is already assigned to another employer."
        ) from error
    return load_recommendation_metadata(db_path, employer_id)


def load_recommendation_diagnostic(
    database_path: str | Path,
    profile_id: str,
    employer_id: str,
) -> RecommendationDiagnostic:
    """Load one stored profile/employer result, including hidden feedback."""

    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT *
            FROM company_recommendations
            WHERE profile_id = ? AND employer_id = ?
            """,
            (profile_id, employer_id),
        ).fetchone()
    if row is None:
        return RecommendationDiagnostic(
            profile_id=profile_id,
            employer_id=employer_id,
            score=None,
            positive_evidence=(),
            negative_evidence=(),
            feedback_state="Not generated",
            availability_state="Not evaluated",
            generated_at=None,
            last_evaluated_at=None,
        )
    evidence = _load_string_tuple(row["evidence_json"])
    negative = tuple(item for item in evidence if _is_negative(item))
    return RecommendationDiagnostic(
        profile_id=profile_id,
        employer_id=employer_id,
        score=row["recommendation_score"],
        positive_evidence=tuple(item for item in evidence if item not in negative),
        negative_evidence=negative,
        feedback_state=row["recommendation_state"],
        availability_state=row["availability_state"],
        generated_at=row["generated_at"],
        last_evaluated_at=row["last_evaluated_at"],
    )


def reset_recommendation_feedback(
    database_path: str | Path,
    profile_id: str,
    employer_id: str,
    *,
    confirmation: str,
) -> None:
    """Reset exactly one profile/employer feedback record with an audit."""

    if confirmation != "RESET":
        raise RecommendationAdminError("Type RESET to confirm this action.")
    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE company_recommendations
            SET recommendation_state = ?, hidden_until = NULL
            WHERE profile_id = ? AND employer_id = ?
            """,
            (NEW, profile_id, employer_id),
        )
        if cursor.rowcount != 1:
            raise RecommendationAdminError(
                "No recommendation feedback exists for that pair."
            )
        _audit(connection, employer_id, profile_id, "reset_feedback")


def rebuild_recommendations(
    database_path: str | Path,
    *,
    profile_id: str | None = None,
    employer_id: str | None = None,
    all_profiles_confirmation: str = "",
) -> int:
    """Rebuild one profile, one employer, or explicitly all profiles."""

    from job_radar.company_recommendation_service import (
        build_company_recommendations_for_profile,
    )

    db_path = initialize_database(database_path)
    if profile_id:
        if get_profile(db_path, profile_id) is None:
            raise RecommendationAdminError("That profile no longer exists.")
        build_company_recommendations_for_profile(
            db_path,
            profile_id,
            employer_ids={employer_id} if employer_id else None,
        )
        _write_audit(db_path, employer_id or "*", profile_id, "rebuild")
        return 1
    if employer_id:
        profiles = list_profiles(db_path)
        for profile in profiles:
            build_company_recommendations_for_profile(
                db_path,
                profile.profile_id,
                employer_ids={employer_id},
            )
        _write_audit(db_path, employer_id, None, "rebuild_employer")
        return len(profiles)
    if all_profiles_confirmation != "REBUILD ALL":
        raise RecommendationAdminError(
            "Type REBUILD ALL to rebuild every profile."
        )
    profiles = list_profiles(db_path)
    for profile in profiles:
        build_company_recommendations_for_profile(db_path, profile.profile_id)
    _write_audit(db_path, "*", None, "rebuild_all")
    return len(profiles)


def list_recommendation_audit(
    database_path: str | Path,
    employer_id: str,
) -> tuple[sqlite3.Row, ...]:
    """List the sanitized recent audit for one employer."""

    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT *
            FROM recommendation_admin_audit
            WHERE employer_id IN (?, '*')
            ORDER BY audit_id DESC
            LIMIT 25
            """,
            (employer_id,),
        ).fetchall()
    return tuple(rows)


def _write_audit(
    database_path: Path,
    employer_id: str,
    profile_id: str | None,
    operation: str,
) -> None:
    with connect_database(database_path) as connection:
        _audit(connection, employer_id, profile_id, operation)


def _audit(
    connection: sqlite3.Connection,
    employer_id: str,
    profile_id: str | None,
    operation: str,
) -> None:
    connection.execute(
        """
        INSERT INTO recommendation_admin_audit (
            employer_id, profile_id, operation
        ) VALUES (?, ?, ?)
        """,
        (employer_id, profile_id, operation),
    )


def _lines(value: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            cleaned
            for line in value.splitlines()
            if (cleaned := " ".join(line.strip().split()))
        )
    )


def _load_string_tuple(value: str) -> tuple[str, ...]:
    loaded = json.loads(value)
    if not isinstance(loaded, list):
        return ()
    return tuple(item for item in loaded if isinstance(item, str))


def _is_negative(value: str) -> bool:
    lowered = value.casefold()
    return any(
        term in lowered
        for term in ("conflict", "below", "does not", "unavailable", "missing")
    )
