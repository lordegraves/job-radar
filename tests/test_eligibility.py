"""Tests the structured practical-eligibility result carried by scored jobs."""

import pytest

from job_radar.eligibility import (
    ELIGIBILITY_ELIGIBLE,
    ELIGIBILITY_NEEDS_REVIEW,
    ELIGIBILITY_NOT_ELIGIBLE,
    EligibilityReason,
    EligibilityResult,
)
from job_radar.models import JobPosting
from job_radar.scored_posting import ScoredPosting


def make_posting() -> JobPosting:
    return JobPosting(
        company_key="example",
        company_name="Example",
        source_type="greenhouse",
        source_job_id="123",
        source_url="https://example.com/jobs/123",
        title="Senior Infrastructure Engineer",
        location="Remote",
        description="Build Linux infrastructure.",
        canonical_key="example:senior-infrastructure-engineer:remote",
        content_hash="hash",
    )


@pytest.mark.parametrize(
    "status",
    [
        ELIGIBILITY_ELIGIBLE,
        ELIGIBILITY_NEEDS_REVIEW,
        ELIGIBILITY_NOT_ELIGIBLE,
    ],
)
def test_eligibility_result_accepts_supported_statuses(status: str) -> None:
    result = EligibilityResult(
        status=status,
        reasons=(
            EligibilityReason(
                code="example_reason",
                message="Example plain-English explanation.",
            ),
        ),
    )

    assert result.status == status
    assert result.reasons[0].code == "example_reason"
    assert result.reasons[0].message == "Example plain-English explanation."


def test_eligibility_result_rejects_unknown_status() -> None:
    with pytest.raises(ValueError, match="unsupported eligibility status"):
        EligibilityResult(status="maybe")


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("", "Readable reason."),
        ("   ", "Readable reason."),
        ("reason_code", ""),
        ("reason_code", "   "),
    ],
)
def test_eligibility_reason_requires_code_and_message(
    code: str,
    message: str,
) -> None:
    with pytest.raises(ValueError):
        EligibilityReason(code=code, message=message)


def test_scored_posting_can_carry_structured_eligibility() -> None:
    eligibility = EligibilityResult(
        status=ELIGIBILITY_NEEDS_REVIEW,
        reasons=(
            EligibilityReason(
                code="location_unclear",
                message="The workplace location needs confirmation.",
            ),
        ),
    )

    scored_posting = ScoredPosting(
        posting=make_posting(),
        score=40,
        score_reasons=["+30 title:infrastructure", "+10 body:linux"],
        eligibility=eligibility,
    )

    assert scored_posting.eligibility == eligibility
    assert scored_posting.eligibility.status == ELIGIBILITY_NEEDS_REVIEW
    assert scored_posting.eligibility.reasons[0].code == "location_unclear"


def test_scored_posting_preserves_legacy_default_without_eligibility() -> None:
    scored_posting = ScoredPosting(
        posting=make_posting(),
        score=40,
        score_reasons=["+30 title:infrastructure", "+10 body:linux"],
    )

    assert scored_posting.eligibility is None
