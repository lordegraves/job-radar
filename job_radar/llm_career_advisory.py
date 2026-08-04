"""Provide bounded, user-requested career advice for one selected job."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable

import requests

from job_radar.config import LlmSettings
from job_radar.llm_advisory import (
    LlmAdvisoryError,
    _load_api_key,
    _post_review_with_bounded_retry,
)
from job_radar.models import JobPosting


TAILORING_PROMPT_VERSION = "resume-tailoring-v1"


@dataclass(frozen=True)
class ResumeEditAdvice:
    section: str
    suggestion: str
    resume_evidence: str


@dataclass(frozen=True)
class ResumeTailoringAdvice:
    summary: str
    edits: tuple[ResumeEditAdvice, ...]
    cautions: tuple[str, ...]
    provider: str
    model: str
    prompt_version: str = TAILORING_PROMPT_VERSION


def build_resume_tailoring_advice(
    *,
    settings: LlmSettings,
    posting: JobPosting,
    resume_text: str,
    post_json: Callable[..., requests.Response] = requests.post,
) -> ResumeTailoringAdvice:
    """Suggest evidence-grounded edits without inventing qualifications."""

    _require_enabled_advisory(settings)
    value = _request_structured(
        settings=settings,
        instructions=(
            "Act as a résumé-tailoring adviser. Suggest at most six concise edits "
            "that improve alignment with this job while preserving the candidate's "
            "voice. Every suggestion must cite supporting evidence already present "
            "in the résumé. Never invent experience, credentials, dates, metrics, "
            "tools, or responsibilities. Put unsupported job requirements in "
            "cautions instead of suggesting that the candidate claim them."
        ),
        private_input={
            "job_title": posting.title,
            "job_description": posting.description or "",
            "resume": resume_text,
        },
        schema=_tailoring_schema(),
        schema_name="junior_resume_tailoring",
        post_json=post_json,
    )
    edits = tuple(
        ResumeEditAdvice(
            section=str(item["section"]).strip(),
            suggestion=str(item["suggestion"]).strip(),
            resume_evidence=str(item["resume_evidence"]).strip(),
        )
        for item in value["edits"][:6]
    )
    return ResumeTailoringAdvice(
        summary=str(value["summary"]).strip(),
        edits=edits,
        cautions=tuple(str(item).strip() for item in value["cautions"][:6]),
        provider=settings.provider,
        model=settings.model,
    )


def _require_enabled_advisory(settings: LlmSettings) -> None:
    if not settings.enabled:
        raise LlmAdvisoryError("LLM assistance is disabled.")
    if not settings.privacy_acknowledged:
        raise LlmAdvisoryError("LLM privacy acknowledgement is required.")


def _request_structured(
    *,
    settings: LlmSettings,
    instructions: str,
    private_input: dict[str, Any],
    schema: dict[str, Any],
    schema_name: str,
    post_json: Callable[..., requests.Response],
) -> dict[str, Any]:
    api_key = _load_api_key(settings)
    payload = {
        "model": settings.model,
        "store": False,
        "reasoning": {"effort": "medium"},
        "instructions": instructions,
        "input": json.dumps(private_input, ensure_ascii=False),
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": schema,
            }
        },
    }
    response = _post_review_with_bounded_retry(
        post_json=post_json,
        api_key=api_key,
        payload=payload,
    )
    if response.get("status") == "incomplete":
        raise LlmAdvisoryError("OpenAI did not finish the requested advice.")
    output_text = response.get("output_text")
    if not isinstance(output_text, str):
        for output in response.get("output", []):
            for content in output.get("content", []) if isinstance(output, dict) else []:
                if isinstance(content, dict) and content.get("refusal"):
                    raise LlmAdvisoryError("OpenAI declined the requested advice.")
                if isinstance(content, dict) and isinstance(content.get("text"), str):
                    output_text = content["text"]
                    break
    try:
        value = json.loads(output_text)
    except (TypeError, json.JSONDecodeError) as error:
        raise LlmAdvisoryError("OpenAI returned unreadable advice.") from error
    if not isinstance(value, dict):
        raise LlmAdvisoryError("OpenAI returned unreadable advice.")
    return value


def _tailoring_schema() -> dict[str, Any]:
    edit = {
        "type": "object",
        "additionalProperties": False,
        "required": ["section", "suggestion", "resume_evidence"],
        "properties": {
            "section": {"type": "string", "maxLength": 80},
            "suggestion": {"type": "string", "maxLength": 500},
            "resume_evidence": {"type": "string", "maxLength": 500},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "edits", "cautions"],
        "properties": {
            "summary": {"type": "string", "maxLength": 700},
            "edits": {"type": "array", "maxItems": 6, "items": edit},
            "cautions": {
                "type": "array",
                "maxItems": 6,
                "items": {"type": "string", "maxLength": 300},
            },
        },
    }
