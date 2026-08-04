import json

import pytest
import requests

from job_radar.config import LlmSettings
from job_radar.llm_advisory import (
    LlmAdvisoryError,
    review_job_fit,
    test_openai_connection as check_openai_connection,
)
from job_radar.models import JobPosting
from job_radar.resume_match import ResumeMatchResult


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.value


class FailingResponse:
    def __init__(self, status_code):
        self.status_code = status_code

    def raise_for_status(self):
        response = requests.Response()
        response.status_code = self.status_code
        raise requests.HTTPError(response=response)


def settings(*, enabled: bool = True) -> LlmSettings:
    return LlmSettings(
        enabled=enabled,
        provider="openai",
        model="gpt-test",
        credential_key="llm:test",
        privacy_acknowledged=True,
        max_reviews_per_scan=5,
    )


def posting() -> JobPosting:
    return JobPosting(
        company_key="example",
        company_name="Example",
        source_type="greenhouse",
        source_url="https://example.com/job/1",
        title="Network Reliability Engineer",
        location="Remote - US",
        description="Required: advanced network failure-model expertise. " * 10,
    )


def deterministic() -> ResumeMatchResult:
    return ResumeMatchResult(
        label="Moderate",
        evidence=["Datacenter networking"],
        gaps=["Networking basics"],
        requirements_reviewed=["Advanced network failure-model expertise"],
    )


def test_openai_review_uses_bounded_structured_nonstored_request(monkeypatch) -> None:
    monkeypatch.setattr(
        "job_radar.llm_advisory.get_credential",
        lambda _reference: "secret-not-logged",
    )
    captured = {}

    def post_json(_url, **kwargs):
        captured.update(kwargs)
        return FakeResponse(
            {
                "output_text": json.dumps(
                    {
                        "fit_assessment": "plausible",
                        "evidence": ["Datacenter network operations"],
                        "material_gaps": [
                            {
                                "requirement": "Advanced failure modeling",
                                "summary": "No advanced network failure-model evidence",
                            }
                        ],
                        "explanation": "Related experience, but advanced depth is unclear.",
                    }
                )
            }
        )

    result = review_job_fit(
        settings=settings(),
        posting=posting(),
        resume_text="Operated datacenter networks.",
        deterministic_match=deterministic(),
        post_json=post_json,
    )

    assert result.fit_assessment == "plausible"
    assert result.material_gaps[0].summary == (
        "No advanced network failure-model evidence"
    )
    assert captured["json"]["store"] is False
    assert captured["json"]["text"]["format"]["strict"] is True
    assert captured["timeout"] == 30


def test_connection_check_sends_no_resume_or_job_data(monkeypatch) -> None:
    monkeypatch.setattr(
        "job_radar.llm_advisory.get_credential",
        lambda _reference: "secret-not-logged",
    )
    captured = {}

    def get_json(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse({"id": "gpt-test"})

    result = check_openai_connection(settings=settings(), get_json=get_json)

    assert result.model == "gpt-test"
    assert captured["url"].endswith("/v1/models/gpt-test")
    assert "json" not in captured
    assert "secret-not-logged" not in result.message


def test_connection_check_explains_rejected_key(monkeypatch) -> None:
    monkeypatch.setattr(
        "job_radar.llm_advisory.get_credential",
        lambda _reference: "rejected-key",
    )

    with pytest.raises(LlmAdvisoryError, match="rejected the saved API key"):
        check_openai_connection(
            settings=settings(),
            get_json=lambda *_args, **_kwargs: FailingResponse(401),
        )


def test_refusal_keeps_deterministic_result(monkeypatch) -> None:
    monkeypatch.setattr(
        "job_radar.llm_advisory.get_credential",
        lambda _reference: "secret-not-logged",
    )
    response = FakeResponse(
        {
            "output": [
                {"content": [{"type": "refusal", "refusal": "Declined"}]}
            ]
        }
    )

    with pytest.raises(LlmAdvisoryError, match="declined"):
        review_job_fit(
            settings=settings(),
            posting=posting(),
            resume_text="Operated datacenter networks.",
            deterministic_match=deterministic(),
            post_json=lambda *_args, **_kwargs: response,
        )


def test_disabled_advisory_never_reads_credentials(monkeypatch) -> None:
    monkeypatch.setattr(
        "job_radar.llm_advisory.get_credential",
        lambda _reference: pytest.fail("credential should not be read"),
    )

    with pytest.raises(LlmAdvisoryError, match="disabled"):
        review_job_fit(
            settings=settings(enabled=False),
            posting=posting(),
            resume_text="Resume",
            deterministic_match=deterministic(),
        )


def test_invalid_provider_result_falls_back_safely(monkeypatch) -> None:
    monkeypatch.setattr(
        "job_radar.llm_advisory.get_credential",
        lambda _reference: "secret-not-logged",
    )

    with pytest.raises(LlmAdvisoryError, match="invalid advisory result"):
        review_job_fit(
            settings=settings(),
            posting=posting(),
            resume_text="Resume",
            deterministic_match=deterministic(),
            post_json=lambda *_args, **_kwargs: FakeResponse({"output_text": "no"}),
        )
