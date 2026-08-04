from job_radar.llm_advisory import LlmFitReview, LlmMaterialGap
from job_radar.models import JobPosting
from job_radar.resume_match import ResumeMatchResult
from job_radar.scan_service import _apply_llm_fit_review
from job_radar.scored_posting import ScoredPosting


def scored_posting() -> ScoredPosting:
    posting = JobPosting(
        company_key="example",
        company_name="Example",
        source_type="greenhouse",
        source_url="https://example.com/job/1",
        title="Linux Infrastructure Engineer",
        location="Remote - US",
        description="Required Linux infrastructure experience. " * 10,
        normalization_state="complete",
    )
    return ScoredPosting(
        posting=posting,
        score=100,
        score_reasons=["+100 body: linux"],
        location_status="allowed",
        resume_match=ResumeMatchResult(
            label="Strong",
            evidence=["Linux"],
            gaps=[],
        ),
    )


def scoring_config():
    return {
        "top_matches": {
            "min_score": 50,
            "excluded_title_keywords": [],
            "strong_signals": ["linux"],
            "review_signals": [],
        },
        "review_needed": {
            "min_score": 25,
            "excluded_location_statuses": [],
            "strong_signals": ["linux"],
        },
    }


def test_weak_llm_fit_blocks_recommendation_without_changing_location() -> None:
    original = scored_posting()
    review = LlmFitReview(
        fit_assessment="weak",
        evidence=("Linux operations",),
        material_gaps=(
            LlmMaterialGap(
                requirement="Advanced kernel development",
                summary="No Linux kernel-development experience",
            ),
        ),
        explanation="The central required work is unsupported.",
        provider="openai",
        model="gpt-test",
    )

    result = _apply_llm_fit_review(
        original,
        review=review,
        scoring_config=scoring_config(),
    )

    assert result.location_status == "allowed"
    assert result.top_match_eligible is False
    assert result.review_needed_eligible is False
    assert result.resume_match.label == "Poor Fit"
    assert result.resume_match.gaps == ["No Linux kernel-development experience"]
    assert result.llm_review == review
    assert result.deterministic_resume_match == original.resume_match


def test_strong_llm_fit_can_confirm_top_match() -> None:
    review = LlmFitReview(
        fit_assessment="strong",
        evidence=("Linux infrastructure engineering",),
        material_gaps=(),
        explanation="The required work is supported.",
        provider="openai",
        model="gpt-test",
    )

    result = _apply_llm_fit_review(
        scored_posting(),
        review=review,
        scoring_config=scoring_config(),
    )

    assert result.top_match_eligible is True
    assert result.resume_match.gaps == []
