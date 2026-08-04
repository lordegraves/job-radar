"""Reuse unchanged LLM fit reviews without storing the private request text."""

from hashlib import sha256
import json
from pathlib import Path

from job_radar.config import LlmSettings
from job_radar.llm_advisory import (
    LlmFitReview,
    LlmMaterialGap,
    PROMPT_VERSION,
)
from job_radar.models import JobPosting
from job_radar.resume_match import ResumeMatchResult
from job_radar.storage import connect_database, initialize_database


def advisory_input_hash(
    *,
    settings: LlmSettings,
    posting: JobPosting,
    resume_text: str,
    deterministic_match: ResumeMatchResult,
) -> str:
    value = {
        "provider": settings.provider,
        "model": settings.model,
        "prompt_version": PROMPT_VERSION,
        "title": posting.title,
        "description": posting.description or "",
        "resume": resume_text,
        "requirements": deterministic_match.requirements_reviewed or [],
        "evidence": deterministic_match.evidence,
        "gaps": deterministic_match.gaps,
    }
    return sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def fetch_cached_advisory(
    database_path: str | Path,
    *,
    profile_id: str,
    job_radar_id: str,
    input_hash: str,
) -> LlmFitReview | None:
    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        row = connection.execute(
            """
            SELECT result_json
            FROM llm_advisory_cache
            WHERE profile_id = ? AND job_radar_id = ? AND input_hash = ?
            """,
            (profile_id, job_radar_id, input_hash),
        ).fetchone()
        if row is None:
            return None
        connection.execute(
            """
            UPDATE llm_advisory_cache
            SET last_used_at = CURRENT_TIMESTAMP
            WHERE profile_id = ? AND job_radar_id = ? AND input_hash = ?
            """,
            (profile_id, job_radar_id, input_hash),
        )
    try:
        value = json.loads(row[0])
        return _review_from_dict(value)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def store_advisory(
    database_path: str | Path,
    *,
    profile_id: str,
    job_radar_id: str,
    input_hash: str,
    review: LlmFitReview,
) -> None:
    db_path = initialize_database(database_path)
    result_json = json.dumps(_review_to_dict(review), ensure_ascii=False)
    with connect_database(db_path) as connection:
        connection.execute(
            """
            INSERT INTO llm_advisory_cache (
                profile_id, job_radar_id, input_hash, provider, model,
                prompt_version, result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_id, job_radar_id, input_hash) DO UPDATE SET
                result_json = excluded.result_json,
                last_used_at = CURRENT_TIMESTAMP
            """,
            (
                profile_id,
                job_radar_id,
                input_hash,
                review.provider,
                review.model,
                review.prompt_version,
                result_json,
            ),
        )


def _review_to_dict(review: LlmFitReview) -> dict[str, object]:
    return {
        "fit_assessment": review.fit_assessment,
        "evidence": list(review.evidence),
        "material_gaps": [
            {"requirement": gap.requirement, "summary": gap.summary}
            for gap in review.material_gaps
        ],
        "explanation": review.explanation,
        "provider": review.provider,
        "model": review.model,
        "prompt_version": review.prompt_version,
    }


def _review_from_dict(value: dict[str, object]) -> LlmFitReview:
    raw_gaps = value.get("material_gaps", [])
    if not isinstance(raw_gaps, list):
        raise ValueError("Invalid cached gaps")
    return LlmFitReview(
        fit_assessment=str(value["fit_assessment"]),
        evidence=tuple(str(item) for item in value.get("evidence", [])),
        material_gaps=tuple(
            LlmMaterialGap(
                requirement=str(item["requirement"]),
                summary=str(item["summary"]),
            )
            for item in raw_gaps
            if isinstance(item, dict)
        ),
        explanation=str(value.get("explanation", "")),
        provider=str(value["provider"]),
        model=str(value["model"]),
        prompt_version=str(value["prompt_version"]),
    )
