from job_radar.llm_advisory import LlmFitReview, LlmMaterialGap
from job_radar.llm_advisory_cache import fetch_cached_advisory, store_advisory


def test_cached_advisory_round_trip_uses_hash_without_prompt_text(tmp_path) -> None:
    database_path = tmp_path / "junior.sqlite3"
    review = LlmFitReview(
        fit_assessment="plausible",
        evidence=("Linux infrastructure",),
        material_gaps=(
            LlmMaterialGap(
                requirement="Advanced routing failure analysis",
                summary="No advanced routing failure-analysis evidence",
            ),
        ),
        explanation="Related background; advanced depth remains unclear.",
        provider="openai",
        model="gpt-test",
    )

    store_advisory(
        database_path,
        profile_id="profile_test",
        job_radar_id="jr-test-1",
        input_hash="a" * 64,
        review=review,
    )

    assert fetch_cached_advisory(
        database_path,
        profile_id="profile_test",
        job_radar_id="jr-test-1",
        input_hash="a" * 64,
    ) == review
    assert fetch_cached_advisory(
        database_path,
        profile_id="profile_test",
        job_radar_id="jr-test-1",
        input_hash="b" * 64,
    ) is None
