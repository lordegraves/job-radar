"""Tests the structured practical-eligibility result carried by scored jobs."""

import pytest

from job_radar.compensation import evaluate_compensation
from job_radar.eligibility import (
    ELIGIBILITY_ELIGIBLE,
    ELIGIBILITY_NEEDS_REVIEW,
    ELIGIBILITY_NOT_ELIGIBLE,
    EligibilityReason,
    EligibilityResult,
    evaluate_practical_eligibility,
    evaluate_workplace_eligibility,
)
from job_radar.models import JobPosting
from job_radar.profile_models import LocationPreference, ProfilePreferences
from job_radar.scored_posting import ScoredPosting


def make_posting(
    *,
    location: str | None = "Remote",
    remote_status: str | None = None,
    salary_text: str | None = None,
    description: str = "Build Linux infrastructure.",
) -> JobPosting:
    return JobPosting(
        company_key="example",
        company_name="Example",
        source_type="greenhouse",
        source_job_id="123",
        source_url="https://example.com/jobs/123",
        title="Senior Infrastructure Engineer",
        location=location,
        description=description,
        remote_status=remote_status,
        salary_text=salary_text,
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


@pytest.mark.parametrize(
    ("location", "remote_status"),
    [
        ("Remote", None),
        ("United States", "Remote"),
        ("Virtual", None),
    ],
)
def test_remote_job_is_eligible_when_remote_is_selected(
    location: str,
    remote_status: str | None,
) -> None:
    result = evaluate_workplace_eligibility(
        posting=make_posting(
            location=location,
            remote_status=remote_status,
        ),
        preferences=ProfilePreferences(work_arrangements=("Remote",)),
    )

    assert result is not None
    assert result.status == ELIGIBILITY_ELIGIBLE
    assert result.reasons[0].code == "remote_arrangement_selected"


def test_remote_job_is_not_eligible_when_remote_is_not_selected() -> None:
    result = evaluate_workplace_eligibility(
        posting=make_posting(location="Remote"),
        preferences=ProfilePreferences(work_arrangements=("Hybrid",)),
    )

    assert result is not None
    assert result.status == ELIGIBILITY_NOT_ELIGIBLE
    assert result.reasons[0].code == "workplace_arrangement_not_selected"


@pytest.mark.parametrize(
    ("location", "remote_status", "selected_arrangement"),
    [
        ("Fort Collins, CO", "Hybrid", "Hybrid"),
        ("On-site - Fort Collins, CO", None, "On-site"),
    ],
)
def test_location_based_job_is_eligible_when_location_matches(
    location: str,
    remote_status: str | None,
    selected_arrangement: str,
) -> None:
    result = evaluate_workplace_eligibility(
        posting=make_posting(
            location=location,
            remote_status=remote_status,
        ),
        preferences=ProfilePreferences(
            work_arrangements=(selected_arrangement,),
            location_selections=(
                LocationPreference(
                    value="place:fort-collins",
                    label="Fort Collins, Colorado",
                    latitude=40.5853,
                    longitude=-105.0844,
                    radius_miles=25,
                ),
            ),
        ),
    )

    assert result is not None
    assert result.status == ELIGIBILITY_ELIGIBLE
    assert result.reasons[0].code == "location_matches_selected_area"


def test_location_matching_normalizes_multiword_state_names_safely() -> None:
    result = evaluate_workplace_eligibility(
        posting=make_posting(
            location="Charleston, WV",
            remote_status="On-site",
        ),
        preferences=ProfilePreferences(
            work_arrangements=("On-site",),
            preferred_locations=("Charleston, West Virginia",),
        ),
    )

    assert result is not None
    assert result.status == ELIGIBILITY_ELIGIBLE
    assert result.reasons[0].code == "location_matches_selected_area"


def test_location_based_job_is_not_eligible_for_clear_mismatch() -> None:
    result = evaluate_workplace_eligibility(
        posting=make_posting(
            location="Denver, CO",
            remote_status="Hybrid",
        ),
        preferences=ProfilePreferences(
            work_arrangements=("Hybrid",),
            location_selections=(
                LocationPreference(
                    value="place:fort-collins",
                    label="Fort Collins, Colorado",
                    latitude=40.5853,
                    longitude=-105.0844,
                    radius_miles=25,
                ),
            ),
        ),
    )

    assert result is not None
    assert result.status == ELIGIBILITY_NOT_ELIGIBLE
    assert result.reasons[0].code == "location_outside_selected_areas"


def test_location_based_job_needs_review_without_selected_locations() -> None:
    result = evaluate_workplace_eligibility(
        posting=make_posting(
            location="Fort Collins, CO",
            remote_status="Hybrid",
        ),
        preferences=ProfilePreferences(
            work_arrangements=("Hybrid",),
        ),
    )

    assert result is not None
    assert result.status == ELIGIBILITY_NEEDS_REVIEW
    assert result.reasons[0].code == "no_preferred_locations_configured"


def test_location_based_job_needs_review_for_broad_location() -> None:
    result = evaluate_workplace_eligibility(
        posting=make_posting(
            location="Multiple locations",
            remote_status="Hybrid",
        ),
        preferences=ProfilePreferences(
            work_arrangements=("Hybrid",),
            preferred_locations=("Fort Collins, Colorado",),
        ),
    )

    assert result is not None
    assert result.status == ELIGIBILITY_NEEDS_REVIEW
    assert result.reasons[0].code == "job_location_ambiguous"


def test_unclear_workplace_arrangement_needs_review() -> None:
    result = evaluate_workplace_eligibility(
        posting=make_posting(
            location="Fort Collins, CO",
            remote_status=None,
        ),
        preferences=ProfilePreferences(
            work_arrangements=("Remote", "Hybrid", "On-site"),
        ),
    )

    assert result is not None
    assert result.status == ELIGIBILITY_NEEDS_REVIEW
    assert result.reasons[0].code == "workplace_arrangement_unclear"


def test_legacy_context_does_not_create_structured_eligibility() -> None:
    result = evaluate_workplace_eligibility(
        posting=make_posting(),
        preferences=None,
    )

    assert result is None


def test_practical_eligibility_combines_workplace_and_compensation() -> None:
    posting = make_posting(
        location="Remote",
        salary_text="$180K - $220K",
    )
    preferences = ProfilePreferences(
        work_arrangements=("Remote",),
        compensation_floor_usd=160000,
    )

    result = evaluate_practical_eligibility(
        posting=posting,
        preferences=preferences,
        compensation=evaluate_compensation(
            posting.salary_text,
            preferences.compensation_floor_usd,
        ),
    )

    assert result is not None
    assert result.status == ELIGIBILITY_ELIGIBLE
    assert [reason.code for reason in result.reasons] == [
        "remote_arrangement_selected",
        "compensation_meets_floor",
    ]


def test_below_floor_compensation_overrides_eligible_workplace() -> None:
    posting = make_posting(
        location="Remote",
        salary_text="$100K - $140K",
    )
    preferences = ProfilePreferences(
        work_arrangements=("Remote",),
        compensation_floor_usd=160000,
    )

    result = evaluate_practical_eligibility(
        posting=posting,
        preferences=preferences,
        compensation=evaluate_compensation(
            posting.salary_text,
            preferences.compensation_floor_usd,
        ),
    )

    assert result is not None
    assert result.status == ELIGIBILITY_NOT_ELIGIBLE
    assert [reason.code for reason in result.reasons] == [
        "remote_arrangement_selected",
        "compensation_below_floor",
    ]


@pytest.mark.parametrize(
    ("salary_text", "expected_code"),
    [
        (None, "compensation_unknown"),
        ("$120K - $180K", "compensation_partially_meets_floor"),
    ],
)
def test_uncertain_compensation_requires_review(
    salary_text: str | None,
    expected_code: str,
) -> None:
    posting = make_posting(
        location="Remote",
        salary_text=salary_text,
    )
    preferences = ProfilePreferences(
        work_arrangements=("Remote",),
        compensation_floor_usd=160000,
    )

    result = evaluate_practical_eligibility(
        posting=posting,
        preferences=preferences,
        compensation=evaluate_compensation(
            posting.salary_text,
            preferences.compensation_floor_usd,
        ),
    )

    assert result is not None
    assert result.status == ELIGIBILITY_NEEDS_REVIEW
    assert result.reasons[-1].code == expected_code


def test_remote_state_restriction_matches_selected_location() -> None:
    result = evaluate_workplace_eligibility(
        posting=make_posting(
            location="Remote - Colorado",
            remote_status="Remote",
        ),
        preferences=ProfilePreferences(
            work_arrangements=("Remote",),
            preferred_locations=("Fort Collins, Colorado",),
        ),
    )

    assert result is not None
    assert result.status == ELIGIBILITY_ELIGIBLE
    assert result.reasons[0].code == "remote_region_matches_selected_area"


def test_remote_state_restriction_rejects_clear_state_mismatch() -> None:
    result = evaluate_workplace_eligibility(
        posting=make_posting(
            location="Remote - California",
            remote_status="Remote",
        ),
        preferences=ProfilePreferences(
            work_arrangements=("Remote",),
            preferred_locations=("Fort Collins, Colorado",),
        ),
    )

    assert result is not None
    assert result.status == ELIGIBILITY_NOT_ELIGIBLE
    assert result.reasons[0].code == "remote_region_outside_selected_areas"


@pytest.mark.parametrize(
    "location",
    [
        "Remote (United States)",
        "Remote - United States",
        "Remote (United States); Cincinnati, OH",
        "Remote | New York, NY",
    ],
)
def test_remote_national_or_multi_location_job_remains_eligible(
    location: str,
) -> None:
    result = evaluate_workplace_eligibility(
        posting=make_posting(
            location=location,
            remote_status="Remote",
        ),
        preferences=ProfilePreferences(
            work_arrangements=("Remote",),
            preferred_locations=("Fort Collins, Colorado",),
        ),
    )

    assert result is not None
    assert result.status == ELIGIBILITY_ELIGIBLE
    assert result.reasons[0].code == "remote_arrangement_selected"


def test_selected_employment_type_is_eligible() -> None:
    posting = make_posting(
        description="This is a full-time infrastructure engineering position.",
    )
    preferences = ProfilePreferences(
        work_arrangements=("Remote",),
        employment_types=("Full-time",),
    )

    result = evaluate_practical_eligibility(
        posting=posting,
        preferences=preferences,
        compensation=None,
    )

    assert result is not None
    assert result.status == ELIGIBILITY_ELIGIBLE
    assert result.reasons[-1].code == "employment_type_selected"


def test_unselected_employment_type_is_not_eligible() -> None:
    posting = make_posting(
        description="This is a contract role supporting Linux infrastructure.",
    )
    preferences = ProfilePreferences(
        work_arrangements=("Remote",),
        employment_types=("Full-time",),
    )

    result = evaluate_practical_eligibility(
        posting=posting,
        preferences=preferences,
        compensation=None,
    )

    assert result is not None
    assert result.status == ELIGIBILITY_NOT_ELIGIBLE
    assert result.reasons[-1].code == "employment_type_not_selected"


def test_unclear_employment_type_needs_review() -> None:
    preferences = ProfilePreferences(
        work_arrangements=("Remote",),
        employment_types=("Full-time",),
    )

    result = evaluate_practical_eligibility(
        posting=make_posting(),
        preferences=preferences,
        compensation=None,
    )

    assert result is not None
    assert result.status == ELIGIBILITY_NEEDS_REVIEW
    assert result.reasons[-1].code == "employment_type_unclear"


def test_matching_schedule_is_eligible() -> None:
    posting = make_posting(
        description="This position works the day shift.",
    )
    preferences = ProfilePreferences(
        work_arrangements=("Remote",),
        schedule_preference="Day shift",
    )

    result = evaluate_practical_eligibility(
        posting=posting,
        preferences=preferences,
        compensation=None,
    )

    assert result is not None
    assert result.status == ELIGIBILITY_ELIGIBLE
    assert result.reasons[-1].code == "schedule_matches_preference"


def test_conflicting_schedule_is_not_eligible() -> None:
    posting = make_posting(
        description="This position works the night shift.",
    )
    preferences = ProfilePreferences(
        work_arrangements=("Remote",),
        schedule_preference="Day shift",
    )

    result = evaluate_practical_eligibility(
        posting=posting,
        preferences=preferences,
        compensation=None,
    )

    assert result is not None
    assert result.status == ELIGIBILITY_NOT_ELIGIBLE
    assert result.reasons[-1].code == "schedule_conflicts_with_preference"


def test_on_call_schedule_needs_review() -> None:
    posting = make_posting(
        description="Participate in an on-call rotation.",
    )
    preferences = ProfilePreferences(
        work_arrangements=("Remote",),
        schedule_preference="Weekdays",
    )

    result = evaluate_practical_eligibility(
        posting=posting,
        preferences=preferences,
        compensation=None,
    )

    assert result is not None
    assert result.status == ELIGIBILITY_NEEDS_REVIEW
    assert result.reasons[-1].code == "on_call_schedule_needs_review"


@pytest.mark.parametrize(
    ("description", "travel_limit", "expected_status", "expected_code"),
    [
        (
            "Travel required 10-20%.",
            "20",
            ELIGIBILITY_ELIGIBLE,
            "travel_within_profile_limit",
        ),
        (
            "Up to 25% travel is required.",
            "10",
            ELIGIBILITY_NOT_ELIGIBLE,
            "travel_exceeds_profile_limit",
        ),
        (
            "Travel is required for customer sites.",
            "10",
            ELIGIBILITY_NEEDS_REVIEW,
            "travel_percentage_unclear",
        ),
    ],
)
def test_travel_requirements_are_compared_with_profile_limit(
    description: str,
    travel_limit: str,
    expected_status: str,
    expected_code: str,
) -> None:
    posting = make_posting(description=description)
    preferences = ProfilePreferences(
        work_arrangements=("Remote",),
        travel_tolerance=travel_limit,
    )

    result = evaluate_practical_eligibility(
        posting=posting,
        preferences=preferences,
        compensation=None,
    )

    assert result is not None
    assert result.status == expected_status
    assert result.reasons[-1].code == expected_code


def test_any_schedule_does_not_create_schedule_uncertainty() -> None:
    result = evaluate_practical_eligibility(
        posting=make_posting(),
        preferences=ProfilePreferences(
            work_arrangements=("Remote",),
            schedule_preference="Any schedule",
        ),
        compensation=None,
    )

    assert result is not None
    assert result.status == ELIGIBILITY_ELIGIBLE
    assert [reason.code for reason in result.reasons] == [
        "remote_arrangement_selected",
    ]
