"""Provide bounded, optional LLM advice without replacing Junior's hard rules."""

from __future__ import annotations

from dataclasses import dataclass
import json
from time import sleep
from typing import Any, Callable

import requests

from job_radar.config import LlmSettings
from job_radar.credential_store import CredentialStoreError, get_credential
from job_radar.models import JobPosting
from job_radar.resume_match import ResumeMatchResult


PROMPT_VERSION = "job-fit-review-v1"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
_REQUEST_TIMEOUT_SECONDS = 30
_MAX_REQUEST_ATTEMPTS = 2


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


@dataclass(frozen=True)
class LlmConnectionResult:
    """Describe a safe provider check that sends no résumé or job data."""

    provider: str
    model: str
    message: str


def test_openai_connection(
    *,
    settings: LlmSettings,
    get_json: Callable[..., requests.Response] = requests.get,
) -> LlmConnectionResult:
    """Verify the saved API key and selected model without generating text."""

    api_key = _load_api_key(settings)
    try:
        response = get_json(
            f"{OPENAI_MODELS_URL}/{settings.model}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        response.raise_for_status()
        value = response.json()
    except requests.RequestException as error:
        raise LlmAdvisoryError(_connection_failure_message(error)) from error
    except ValueError as error:
        raise LlmAdvisoryError(
            "OpenAI accepted the connection but returned an unreadable model "
            "response. Try again later."
        ) from error
    if not isinstance(value, dict) or value.get("id") != settings.model:
        raise LlmAdvisoryError(
            "OpenAI did not confirm the selected model. Check the model name "
            "and try again."
        )
    return LlmConnectionResult(
        provider=settings.provider,
        model=settings.model,
        message=(
            f"OpenAI confirmed access to {settings.model}. No résumé or job "
            "information was sent during this test."
        ),
    )


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
    api_key = _load_api_key(settings)

    payload = _openai_payload(
        settings=settings,
        posting=posting,
        resume_text=resume_text,
        deterministic_match=deterministic_match,
    )
    raw = _post_review_with_bounded_retry(
        post_json=post_json,
        api_key=api_key,
        payload=payload,
    )
    return _parse_openai_review(raw, settings=settings)


def _load_api_key(settings: LlmSettings) -> str:
    try:
        api_key = get_credential(settings.credential_key)
    except CredentialStoreError as error:
        raise LlmAdvisoryError(str(error)) from error
    if not api_key:
        raise LlmAdvisoryError(
            "The OpenAI API credential is unavailable in secure storage."
        )
    return api_key


def _post_review_with_bounded_retry(
    *,
    post_json: Callable[..., requests.Response],
    api_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    for attempt in range(_MAX_REQUEST_ATTEMPTS):
        try:
            response = post_json(
                OPENAI_RESPONSES_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            value = response.json()
            if not isinstance(value, dict):
                raise ValueError("OpenAI response was not an object")
            return value
        except requests.RequestException as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            retryable = status == 429 or (isinstance(status, int) and status >= 500)
            if retryable and attempt + 1 < _MAX_REQUEST_ATTEMPTS:
                sleep(1)
                continue
            raise LlmAdvisoryError(_review_failure_message(status)) from error
        except ValueError as error:
            raise LlmAdvisoryError(
                "OpenAI returned an unreadable advisory response. Junior kept "
                "its deterministic result."
            ) from error
    raise LlmAdvisoryError(
        "OpenAI could not complete the advisory review. Junior kept its "
        "deterministic result."
    )


def _review_failure_message(status: int | None) -> str:
    if status == 401:
        return "OpenAI rejected the saved API key. Junior kept its deterministic result."
    if status == 403:
        return "OpenAI denied access to the selected model. Junior kept its deterministic result."
    if status == 404:
        return "OpenAI could not find the selected model. Junior kept its deterministic result."
    if status == 429:
        return "OpenAI is rate-limiting requests. Junior kept its deterministic result."
    return "OpenAI could not complete the advisory review. Junior kept its deterministic result."


def _connection_failure_message(error: requests.RequestException) -> str:
    status = getattr(getattr(error, "response", None), "status_code", None)
    if status == 401:
        return "OpenAI rejected the saved API key. Store a valid API key and try again."
    if status == 403:
        return "The saved API key cannot access the selected OpenAI model."
    if status == 404:
        return "OpenAI could not find the selected model. Check the model name."
    if status == 429:
        return "OpenAI is rate-limiting this account. Wait briefly and try again."
    return "Junior could not reach OpenAI. Check the network and try again."


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
    refusal = _nested_refusal(response)
    if refusal:
        raise LlmAdvisoryError(
            "OpenAI declined the advisory request. Junior kept its deterministic result."
        )
    if response.get("status") == "incomplete":
        raise LlmAdvisoryError(
            "OpenAI did not finish the advisory request. Junior kept its "
            "deterministic result."
        )
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


def _nested_refusal(response: dict[str, Any]) -> str | None:
    for output in response.get("output", []):
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("refusal"), str):
                return content["refusal"]
    return None
