from job_radar.eligibility import EligibilityReason, EligibilityResult
from job_radar.scan_service import _should_compare_resume


def test_location_outlier_is_compared_only_when_role_reaches_review_floor() -> None:
    eligibility = EligibilityResult(
        status="not_eligible",
        reasons=(EligibilityReason("location_outside_selected_areas", "Outside"),),
    )

    assert _should_compare_resume(
        normalization_state="complete",
        eligibility=eligibility,
        include_location_outliers=True,
        score=110,
        review_floor=100,
    )
    assert not _should_compare_resume(
        normalization_state="complete",
        eligibility=eligibility,
        include_location_outliers=True,
        score=20,
        review_floor=100,
    )


def test_non_location_disqualification_never_gets_expensive_resume_match() -> None:
    eligibility = EligibilityResult(
        status="not_eligible",
        reasons=(EligibilityReason("work_authorization_required", "Citizenship"),),
    )

    assert not _should_compare_resume(
        normalization_state="complete",
        eligibility=eligibility,
        include_location_outliers=True,
        score=200,
        review_floor=100,
    )
