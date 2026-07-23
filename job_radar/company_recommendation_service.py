"""Build transparent catalog-only company recommendations."""

import json
from pathlib import Path

from job_radar.company_catalog_query_service import (
    AVAILABLE,
    evaluate_employer_availability,
)
from job_radar.company_recommendation_models import CompanyRecommendation
from job_radar.company_recommendation_evidence import (
    aggregate_employer_job_evidence,
    format_job_evidence,
)
from job_radar.company_recommendation_storage import (
    load_visible_rows,
    save_recommendation,
    set_feedback,
)
from job_radar.employer_storage import (
    list_employer_sources,
    list_profile_employer_assignments,
)
from job_radar.profile_storage import get_active_profile


class CompanyRecommendationError(ValueError):
    """Explain an invalid or stale recommendation action."""


def build_company_recommendations(
    database_path: str | Path,
) -> tuple[CompanyRecommendation, ...]:
    """Generate catalog-only recommendations for the active profile."""

    profile = get_active_profile(database_path)
    if profile is None:
        return ()
    assigned_ids = {
        item.employer_id
        for item in list_profile_employer_assignments(
            database_path, profile.profile_id
        )
    }
    profile_terms = _profile_terms(profile)
    if not profile_terms:
        return ()
    qualified_employer_ids: set[str] = set()

    for employer in list_employer_sources(database_path):
        if employer.employer_id in assigned_ids:
            continue
        availability = evaluate_employer_availability(employer)
        if availability.state != AVAILABLE:
            continue
        score, evidence, metadata_matches = _rank_employer(
            employer, profile_terms
        )
        employer_job_evidence = aggregate_employer_job_evidence(
            database_path,
            profile=profile,
            employer_id=employer.employer_id,
        )
        evidence_score, job_evidence = format_job_evidence(
            employer_job_evidence
        )
        if not metadata_matches and not employer_job_evidence.has_evidence:
            continue
        qualified_employer_ids.add(employer.employer_id)
        save_recommendation(
            database_path,
            profile_id=profile.profile_id,
            employer_id=employer.employer_id,
            score=score + evidence_score,
            evidence=job_evidence + evidence,
            availability_state=availability.state,
        )

    recommendations = []
    for row in load_visible_rows(database_path, profile.profile_id):
        if row["employer_id"] not in qualified_employer_ids:
            continue
        recommendations.append(
            CompanyRecommendation(
                profile_id=row["profile_id"],
                employer_id=row["employer_id"],
                employer_name=row["employer_name"],
                evidence=tuple(json.loads(row["evidence_json"])),
                can_scan=row["availability_state"] == AVAILABLE,
                state=row["recommendation_state"],
                generated_at=row["generated_at"],
                last_evaluated_at=row["last_evaluated_at"],
            )
        )
    return tuple(recommendations)


def record_recommendation_feedback(
    database_path: str | Path,
    *,
    profile_id: str,
    employer_id: str,
    state: str,
) -> None:
    """Record feedback only when the named profile is still active."""

    profile = get_active_profile(database_path)
    if profile is None or profile.profile_id != profile_id:
        raise CompanyRecommendationError(
            "This recommendation does not belong to the active profile."
        )
    if not set_feedback(
        database_path,
        profile_id=profile_id,
        employer_id=employer_id,
        state=state,
    ):
        raise CompanyRecommendationError(
            "That recommendation is no longer available."
        )


def _profile_terms(profile) -> set[str]:
    values = [
        *profile.preferences.target_roles,
        *(item.label for item in profile.preferences.occupation_selections),
    ]
    return {
        token
        for value in values
        for token in _tokens(value)
        if len(token) >= 3
    }


def _rank_employer(
    employer,
    profile_terms: set[str],
) -> tuple[int, tuple[str, ...], bool]:
    metadata = employer.source_config
    metadata_values = [
        employer.name,
        str(metadata.get("industry", "")),
        " ".join(_string_list(metadata.get("tags"))),
        " ".join(_string_list(metadata.get("categories"))),
    ]
    employer_terms = {
        token
        for value in metadata_values
        for token in _tokens(value)
        if len(token) >= 3
    }
    overlap = sorted(profile_terms & employer_terms)
    evidence = []
    score = 0
    if overlap:
        score += 10 * len(overlap)
        evidence.append(
            "Its catalog details overlap with your target work: "
            + ", ".join(overlap[:4])
            + "."
        )
    evidence.append("Junior already has a supported, scan-ready careers source.")
    return score, tuple(evidence), bool(overlap)


def _tokens(value: str) -> set[str]:
    return {
        "".join(character for character in token.casefold() if character.isalnum())
        for token in value.replace("/", " ").replace("-", " ").split()
    }


def _string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))
