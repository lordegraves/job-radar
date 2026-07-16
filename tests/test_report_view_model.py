from job_radar.models import JobPosting
from job_radar.report_view_model import build_report_view_model
from job_radar.scored_posting import ScoredPosting
from job_radar.tracker.tracker_models import ApplicationRecord


def make_scored_posting(
    *,
    title: str,
    top_match_eligible: bool = False,
    review_needed_eligible: bool = False,
    tracked: bool = False,
    score_reasons: list[str] | None = None,
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
        review_needed_eligible=review_needed_eligible,
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


def test_build_report_view_model_routes_kubernetes_risk_to_review_needed() -> None:
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

    assert view.top_matches == []
    assert view.review_needed == [posting]
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
