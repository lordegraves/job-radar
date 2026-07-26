"""Tests how scored jobs are divided among report and email sections."""

from job_radar.eligibility import EligibilityReason, EligibilityResult
from job_radar.models import JobPosting
from job_radar.report_view_model import (
    build_job_output_view_model,
    build_report_view_model,
)
from job_radar.scan_service import _is_storage_relevant_posting
from job_radar.scored_posting import ScoredPosting
from job_radar.tracker.tracker_models import ApplicationRecord


def make_scored_posting(
    *,
    title: str,
    top_match_eligible: bool = False,
    potential_top_match_eligible: bool = False,
    review_needed_eligible: bool = False,
    tracked: bool = False,
    score_reasons: list[str] | None = None,
    top_match_reasons: list[str] | None = None,
    eligibility: EligibilityResult | None = None,
) -> ScoredPosting:
    posting = JobPosting(
        company_key="example",
        company_name="Example",
        source_type="greenhouse",
        source_job_id=title,
        source_url=f"https://example.com/{title}",
        title=title,
        location="Remote",
        description="Linux infrastructure",
        canonical_key=f"example:{title}",
        content_hash=title,
    )

    application = None

    if tracked:
        application = ApplicationRecord(
            job_radar_id=f"jr-{title}",
            company_name="Example",
            role_title=title,
            source_url=posting.source_url,
            status="applied",
            outcome="pending / in progress",
        )

    return ScoredPosting(
        posting=posting,
        score=140,
        score_reasons=score_reasons
        or [
            "+30 title:infrastructure",
            "+10 body:linux",
            "+0 location_allowed:remote",
        ],
        top_match_eligible=top_match_eligible,
        potential_top_match_eligible=potential_top_match_eligible,
        top_match_reasons=top_match_reasons,
        review_needed_eligible=review_needed_eligible,
        eligibility=eligibility,
        application=application,
    )


def test_build_report_view_model_partitions_report_and_email_sections() -> None:
    top_match = make_scored_posting(
        title="top-match",
        top_match_eligible=True,
    )
    review_needed = make_scored_posting(
        title="review-needed",
        review_needed_eligible=True,
    )
    tracked = make_scored_posting(
        title="tracked",
        top_match_eligible=True,
        tracked=True,
    )

    view = build_report_view_model(
        scored_postings=[top_match, tracked],
        omitted_scored_postings=[review_needed],
    )

    assert view.report_scored_postings == [
        top_match,
        tracked,
        review_needed,
    ]
    assert view.top_matches == [top_match]
    assert view.review_needed == [review_needed]
    assert view.tracked_applications == [tracked]
    assert view.email_scored_postings == [
        top_match,
        review_needed,
    ]
    assert view.email_top_matches == [top_match]
    assert view.email_review_needed == [review_needed]


def test_build_job_output_view_model_prepares_shared_display_values() -> None:
    scored_posting = make_scored_posting(
        title="Infrastructure Engineer",
        top_match_eligible=True,
        eligibility=EligibilityResult(
            status="needs_review",
            reasons=(
                EligibilityReason(
                    code="compensation_unknown",
                    message="The posting does not provide usable compensation.",
                ),
                EligibilityReason(
                    code="on_call_schedule_needs_review",
                    message="The posting includes an on-call requirement.",
                ),
            ),
        ),
    )

    job = build_job_output_view_model(scored_posting)

    assert job.title == "Infrastructure Engineer"
    assert job.company == "Example"
    assert job.location == "Remote"
    assert job.job_radar_id == scored_posting.posting.job_radar_id
    assert job.score == 140
    assert job.technical_match
    assert job.resume_match
    assert job.compensation
    assert job.hiring_probability
    assert job.recommended_action
    assert job.action_rationale
    assert job.hiring_risks
    assert job.why_matched == "infrastructure, linux, remote"
    assert job.eligibility_status == "needs_review"
    assert job.eligibility_label == "Needs Review"
    assert job.eligibility_reasons == (
        "The posting does not provide usable compensation.",
        "The posting includes an on-call requirement.",
    )
    assert job.eligibility_reason_text == (
        "The posting does not provide usable compensation.; "
        "The posting includes an on-call requirement."
    )


def test_build_report_view_model_applies_email_limit() -> None:
    top_matches = [
        make_scored_posting(
            title=f"top-match-{index}",
            top_match_eligible=True,
        )
        for index in range(12)
    ]

    view = build_report_view_model(
        scored_postings=top_matches,
        email_postings_limit=10,
    )

    assert len(view.top_matches) == 12
    assert len(view.email_top_matches) == 10


def test_unconfigured_industry_terms_do_not_create_global_risk() -> None:
    posting = make_scored_posting(
        title="Senior Site Reliability Engineer",
        top_match_eligible=True,
        review_needed_eligible=True,
        score_reasons=[
            "+30 title:site reliability",
            "+8 body:kubernetes",
            "+10 body:linux",
            "+100 location_allowed:remote",
        ],
    )

    view = build_report_view_model(scored_postings=[posting])

    assert view.top_matches == [posting]
    assert view.review_needed == []
    assert view.tracked_applications == []


def test_build_report_view_model_excludes_noneligible_roles_from_action_sections() -> None:
    top_match = make_scored_posting(
        title="Senior Infrastructure Engineer",
        top_match_eligible=True,
    )
    skipped = make_scored_posting(title="Senior Kubernetes Engineer")
    business = make_scored_posting(title="Recruiting Coordinator")

    view = build_report_view_model(
        scored_postings=[top_match, skipped, business],
    )

    assert view.top_matches == [top_match]
    assert view.review_needed == []
    assert view.tracked_applications == []


def test_build_report_view_model_routes_tracked_role_out_of_apply_sections() -> None:
    tracked = make_scored_posting(
        title="Site Reliability Engineer",
        top_match_eligible=True,
        review_needed_eligible=True,
        tracked=True,
    )

    view = build_report_view_model(scored_postings=[tracked])

    assert view.top_matches == []
    assert view.review_needed == []
    assert view.tracked_applications == [tracked]
    assert view.email_scored_postings == []
    assert view.email_top_matches == []
    assert view.email_review_needed == []


def test_not_eligible_role_is_excluded_from_action_sections() -> None:
    posting = make_scored_posting(
        title="Senior Infrastructure Engineer",
        top_match_eligible=True,
        eligibility=EligibilityResult(
            status="not_eligible",
            reasons=(
                EligibilityReason(
                    code="location_outside_selected_areas",
                    message="The job location is outside this profile's selected areas.",
                ),
            ),
        ),
    )

    view = build_report_view_model(scored_postings=[posting])

    assert view.top_matches == []
    assert view.review_needed == []
    assert view.email_top_matches == []
    assert view.email_review_needed == []


def test_needs_review_role_moves_from_top_match_to_potential_top_match() -> None:
    posting = make_scored_posting(
        title="Senior Infrastructure Engineer",
        top_match_eligible=True,
        eligibility=EligibilityResult(
            status="needs_review",
            reasons=(
                EligibilityReason(
                    code="compensation_unknown",
                    message="The posting does not provide usable compensation.",
                ),
            ),
        ),
    )

    view = build_report_view_model(scored_postings=[posting])

    assert view.top_matches == []
    assert view.potential_top_matches == [posting]
    assert view.review_needed == []
    assert view.email_top_matches == []
    assert view.email_potential_top_matches == [posting]
    assert view.email_review_needed == []


def test_practical_unknown_is_review_needed_even_below_legacy_score_gate() -> None:
    posting = make_scored_posting(
        title="Unfamiliar but potentially relevant role",
        eligibility=EligibilityResult(
            status="needs_review",
            reasons=(
                EligibilityReason(
                    code="work_arrangement_unknown",
                    message="The posting does not clearly identify a workplace arrangement.",
                ),
            ),
        ),
    )

    view = build_report_view_model(scored_postings=[posting])

    assert view.top_matches == []
    assert view.potential_top_matches == []
    assert view.review_needed == [posting]
    assert view.email_top_matches == []
    assert view.email_potential_top_matches == []
    assert view.email_review_needed == [posting]
    assert _is_storage_relevant_posting(posting)


def test_location_alone_does_not_make_unrelated_work_review_worthy() -> None:
    posting = make_scored_posting(
        title="Courtesy Clerk / Grocery Bagger",
        score_reasons=["+0 location_allowed:fort collins"],
        eligibility=EligibilityResult(
            status="needs_review",
            reasons=(
                EligibilityReason(
                    code="work_arrangement_unknown",
                    message="The posting does not clearly identify a workplace arrangement.",
                ),
                EligibilityReason(
                    code="compensation_unknown",
                    message="The posting does not provide usable compensation.",
                ),
            ),
        ),
    )

    view = build_report_view_model(scored_postings=[posting])

    assert view.top_matches == []
    assert view.potential_top_matches == []
    assert view.review_needed == []
    assert view.email_review_needed == []
    assert not _is_storage_relevant_posting(posting)


def test_one_incidental_body_signal_does_not_make_unrelated_work_review_worthy() -> None:
    posting = make_scored_posting(
        title="Produce Department Leader",
        score_reasons=[
            "+10 body:operations",
            "+0 location_allowed:fort collins",
        ],
        eligibility=EligibilityResult(
            status="needs_review",
            reasons=(
                EligibilityReason(
                    code="employment_type_unknown",
                    message="The posting does not clearly identify an employment type.",
                ),
            ),
        ),
    )

    view = build_report_view_model(scored_postings=[posting])

    assert view.review_needed == []
    assert view.email_review_needed == []
    assert not _is_storage_relevant_posting(posting)


def test_strong_role_with_unresolved_location_is_potential_top_match() -> None:
    posting = make_scored_posting(
        title="Senior Infrastructure Engineer",
        potential_top_match_eligible=True,
        eligibility=EligibilityResult(
            status="needs_review",
            reasons=(
                EligibilityReason(
                    code="job_location_ambiguous",
                    message="The posting location needs confirmation.",
                ),
            ),
        ),
    )

    view = build_report_view_model(scored_postings=[posting])

    assert view.top_matches == []
    assert view.potential_top_matches == [posting]
    assert view.review_needed == []
    assert _is_storage_relevant_posting(posting)


def test_tracked_role_preserves_track_status_when_not_eligible() -> None:
    tracked = make_scored_posting(
        title="Tracked Infrastructure Engineer",
        top_match_eligible=True,
        review_needed_eligible=True,
        tracked=True,
        eligibility=EligibilityResult(
            status="not_eligible",
            reasons=(
                EligibilityReason(
                    code="compensation_below_floor",
                    message="The advertised compensation is below the profile minimum.",
                ),
            ),
        ),
    )

    view = build_report_view_model(scored_postings=[tracked])

    assert view.top_matches == []
    assert view.review_needed == []
    assert view.tracked_applications == [tracked]
    assert view.email_scored_postings == []


def test_storage_omits_new_not_eligible_role() -> None:
    posting = make_scored_posting(
        title="Not Eligible Infrastructure Engineer",
        top_match_eligible=True,
        review_needed_eligible=True,
        eligibility=EligibilityResult(
            status="not_eligible",
            reasons=(
                EligibilityReason(
                    code="location_outside_selected_areas",
                    message="The job location is outside this profile's selected areas.",
                ),
            ),
        ),
    )

    assert not _is_storage_relevant_posting(posting)


def test_storage_keeps_top_match_downgraded_to_review_needed() -> None:
    posting = make_scored_posting(
        title="Eligibility Review Infrastructure Engineer",
        top_match_eligible=True,
        eligibility=EligibilityResult(
            status="needs_review",
            reasons=(
                EligibilityReason(
                    code="compensation_unknown",
                    message="The posting does not provide usable compensation.",
                ),
            ),
        ),
    )

    assert _is_storage_relevant_posting(posting)


def test_storage_keeps_legacy_actionable_role_without_eligibility() -> None:
    posting = make_scored_posting(
        title="Legacy Infrastructure Engineer",
        top_match_eligible=True,
    )

    assert _is_storage_relevant_posting(posting)


def test_storage_keeps_tracked_role_when_not_eligible() -> None:
    posting = make_scored_posting(
        title="Tracked Not Eligible Infrastructure Engineer",
        top_match_eligible=True,
        tracked=True,
        eligibility=EligibilityResult(
            status="not_eligible",
            reasons=(
                EligibilityReason(
                    code="compensation_below_floor",
                    message="The advertised compensation is below the profile minimum.",
                ),
            ),
        ),
    )

    assert _is_storage_relevant_posting(posting)
