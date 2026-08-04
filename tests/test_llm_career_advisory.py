import json

from job_radar.config import LlmSettings
from job_radar.llm_career_advisory import build_resume_tailoring_advice
from job_radar.models import JobPosting


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def raise_for_status(self):
        return None

    def json(self):
        return self.value


def settings() -> LlmSettings:
    return LlmSettings(
        enabled=True,
        provider="openai",
        model="gpt-test",
        credential_key="llm:test",
        privacy_acknowledged=True,
        max_reviews_per_scan=5,
    )


def posting() -> JobPosting:
    return JobPosting(
        company_key="example",
        company_name="Example Systems",
        source_type="greenhouse",
        source_url="https://example.com/jobs/1",
        title="Platform Engineer",
        location="Remote - US",
        description="Requires Linux platform engineering and Kubernetes.",
    )


def test_resume_tailoring_requires_existing_resume_evidence(monkeypatch) -> None:
    monkeypatch.setattr(
        "job_radar.llm_advisory.get_credential",
        lambda _reference: "secret",
    )
    captured = {}

    def post_json(_url, **kwargs):
        captured.update(kwargs["json"])
        return FakeResponse(
            {
                "output_text": json.dumps(
                    {
                        "summary": "Lead with supported Linux platform work.",
                        "edits": [
                            {
                                "section": "Experience",
                                "suggestion": "Move Linux platform ownership earlier.",
                                "resume_evidence": "Operated Linux HPC platforms.",
                            }
                        ],
                        "cautions": ["Do not claim Kubernetes administration."],
                    }
                )
            }
        )

    advice = build_resume_tailoring_advice(
        settings=settings(),
        posting=posting(),
        resume_text="Operated Linux HPC platforms.",
        post_json=post_json,
    )

    assert advice.edits[0].resume_evidence == "Operated Linux HPC platforms."
    assert "Do not claim Kubernetes" in advice.cautions[0]
    assert captured["store"] is False
    assert "Never invent" in captured["instructions"]
