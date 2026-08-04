"""Provide bounded, optional LLM advice without replacing Junior's hard rules."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable

import requests

from job_radar.config import LlmSettings
from job_radar.credential_store import CredentialStoreError, get_credential
from job_radar.models import JobPosting
from job_radar.resume_match import ResumeMatchResult


PROMPT_VERSION = "job-fit-review-v1"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


class LlmAdvisoryError(RuntimeError):
    """Report a safe advisory failure without exposing prompts or credentials."""


@dataclass(frozen=True)
class LlmMaterialGap:
    requirement: str
    summary: str


@dataclass(frozen=True)
class LlmFitReview:
    fit_assessment: str
    evidence: tuple[str, ...]
    material_gaps: tuple[LlmMaterialGap, ...]
    explanation: str
    provider: str
    model: str
    prompt_version: str = PROMPT_VERSION


def review_job_fit(
    *,
    settings: LlmSettings,
    posting: JobPosting,
    resume_text: str,
    deterministic_match: ResumeMatchResult,
    post_json: Callable[..., requests.Response] = requests.post,
) -> LlmFitReview:
    """Review professional fit only after deterministic eligibility has passed."""

    if not settings.enabled:
        raise LlmAdvisoryError("LLM assistance is disabled.")
    if not settings.privacy_acknowledged:
        raise LlmAdvisoryError("LLM privacy acknowledgement is required.")
    try:
        api_key = get_credential(settings.credential_key)
    except CredentialStoreError as error:
        raise LlmAdvisoryError(str(error)) from error
    if not api_key:
        raise LlmAdvisoryError(
            "The OpenAI API credential is unavailable in secure storage."
        )

    payload = _openai_payload(
        settings=settings,
        posting=posting,
        resume_text=resume_text,
        deterministic_match=deterministic_match,
    )
    try:
        response = post_json(
            OPENAI_RESPONSES_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=45,
        )
        response.raise_for_status()
        raw = response.json()
    except (requests.RequestException, ValueError) as error:
        raise LlmAdvisoryError(
            "OpenAI could not complete the advisory review. Junior kept its "
            "deterministic result."
        ) from error
    return _parse_openai_review(raw, settings=settings)


def _openai_payload(
    *,
    settings: LlmSettings,
    posting: JobPosting,
    resume_text: str,
    deterministic_match: ResumeMatchResult,
) -> dict[str, Any]:
    private_input = {
        "job_title": posting.title,
        "job_description": posting.description or "",
        "resume": resume_text,
        "deterministic_required_qualifications": (
            deterministic_match.requirements_reviewed or []
        ),
        "deterministic_evidence": deterministic_match.evidence,
        "deterministic_gaps": deterministic_match.gaps,
    }
    return {
        "model": settings.model,
        "store": False,
        "reasoning": {"effort": "medium"},
        "instructions": (
            "Act as an advisory job-fit reviewer. Compare every explicit required "
            "qualification against the entire resume. Infer transferable evidence "
            "when the resume clearly supports it, but never invent experience. "
            "Report at most four largest material required-qualification gaps. "
            "Do not evaluate location, remote region, compensation, clearance, or "
            "employment type; Junior handles those deterministically. A gap summary "
            "must describe the missing advanced capability precisely and must not "
            "claim the candidate lacks a broader basic skill they demonstrably have."
        ),
        "input": json.dumps(private_input, ensure_ascii=False),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "junior_job_fit_review",
                "strict": True,
                "schema": _review_schema(),
            }
        },
    }


def _review_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["fit_assessment", "evidence", "material_gaps", "explanation"],
        "properties": {
            "fit_assessment": {
                "type": "string",
                "enum": ["strong", "plausible", "weak"],
            },
            "evidence": {
                "type": "array",
                "maxItems": 6,
                "items": {"type": "string", "maxLength": 240},
            },
            "material_gaps": {
                "type": "array",
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["requirement", "summary"],
                    "properties": {
                        "requirement": {"type": "string", "maxLength": 500},
                        "summary": {"type": "string", "maxLength": 240},
                    },
                },
            },
            "explanation": {"type": "string", "maxLength": 600},
        },
    }


def _parse_openai_review(
    response: dict[str, Any],
    *,
    settings: LlmSettings,
) -> LlmFitReview:
    output_text = response.get("output_text")
    if not isinstance(output_text, str):
        output_text = _nested_output_text(response)
    try:
        value = json.loads(output_text)
    except (TypeError, json.JSONDecodeError) as error:
        raise LlmAdvisoryError(
            "OpenAI returned an invalid advisory result. Junior kept its "
            "deterministic result."
        ) from error
    if value.get("fit_assessment") not in {"strong", "plausible", "weak"}:
        raise LlmAdvisoryError(
            "OpenAI returned an unsupported fit assessment. Junior kept its "
            "deterministic result."
        )
    gaps = tuple(
        LlmMaterialGap(
            requirement=str(item.get("requirement", "")).strip(),
            summary=str(item.get("summary", "")).strip(),
        )
        for item in value.get("material_gaps", [])[:4]
        if isinstance(item, dict)
        and str(item.get("requirement", "")).strip()
        and str(item.get("summary", "")).strip()
    )
    return LlmFitReview(
        fit_assessment=value["fit_assessment"],
        evidence=tuple(str(item).strip() for item in value.get("evidence", [])[:6]),
        material_gaps=gaps,
        explanation=str(value.get("explanation", "")).strip(),
        provider=settings.provider,
        model=settings.model,
    )


def _nested_output_text(response: dict[str, Any]) -> str | None:
    for output in response.get("output", []):
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                return content["text"]
    return None
