"""Tests HTML report content, recommendation explanations, escaping, and output."""

from pathlib import Path

from job_radar.eligibility import EligibilityReason, EligibilityResult
from job_radar.models import JobPosting
from job_radar.tracker.tracker_models import ApplicationRecord
from job_radar.html_report import render_html_report, write_html_report
from job_radar.report_models import ScanError, ScanReport
from job_radar.scored_posting import ScoredPosting


def make_posting(
    title: str = "Senior Infrastructure Engineer",
    company_name: str = "Example AI",
    source_type: str = "greenhouse",
    source_url: str = "https://boards.greenhouse.io/exampleai/jobs/123",
    description: str = "Build Linux infrastructure.",
) -> JobPosting:
    return JobPosting(
        company_key="example_ai",
        company_name=company_name,
        source_type=source_type,
        source_job_id="123",
        source_url=source_url,
        title=title,
        location="Remote",
        description=description,
        canonical_key="example_ai:senior-infrastructure-engineer:remote",
        content_hash="hash",
    )


def test_render_html_report_includes_summary_and_clickable_job_links() -> None:
    posting = make_posting(title="Data Center Design Execution Lead")

    report = ScanReport(
        generated_at="2026-06-24T12:34:56+00:00",
        companies_enabled=1,
        jobs_collected=1,
        jobs_new=1,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        jobs_stored=1,
        jobs_omitted=0,
        postings=[posting],
        scored_postings=[
            ScoredPosting(
                posting=posting,
                score=158,
                score_reasons=[
                    "+10 body:infrastructure",
                    "+24 title:data center",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
            )
        ],
    )

    html = render_html_report(report)

    assert "<h1>junior Report</h1>" in html
    assert 'class="table-of-contents"' in html
    assert '<h2 id="summary">Summary</h2>' in html
    assert '<a href="#summary">Summary</a>' in html
    assert '<a href="#top-matches">Top Matches</a>' in html
    assert (
        '<a href="#northern-colorado-highlights">'
        "Northern Colorado Highlights</a>"
        in html
    )
    assert '<a href="#review-needed">Review Needed</a>' in html
    assert '<a href="#tracked-applications">Tracked Applications</a>' in html
    assert '<a href="#new-jobs">New Jobs</a>' in html
    assert (
        '<a href="#passed-not-recommended">Passed / Not Recommended</a>'
        in html
    )
    assert '<a href="#collector-errors">Collector Errors</a>' not in html
    assert '<h2 id="top-matches">Top Matches</h2>' in html
    assert (
        '<h2 id="northern-colorado-highlights">'
        "Northern Colorado Highlights</h2>"
        in html
    )
    assert '<h2 id="review-needed">Review Needed</h2>' in html
    assert '<h2 id="tracked-applications">Tracked Applications</h2>' in html
    assert '<h2 id="new-jobs">New Jobs</h2>' in html
    assert (
        '<h2 id="passed-not-recommended">Passed / Not Recommended</h2>'
        in html
    )
    assert "<strong>Generated at:</strong> 2026-06-24 12:34 UTC" in html
    assert "<strong>Actionable jobs stored:</strong> 1" in html
    assert "<strong>Jobs not actionable:</strong> 0" in html
    assert "<strong>Top matches:</strong> 1" in html
    assert "<strong>Review needed:</strong> 0" in html
    assert "<strong>Tracked applications:</strong> 0" in html
    assert "Data Center Design Execution Lead" in html
    assert (
        '<a href="https://boards.greenhouse.io/exampleai/jobs/123" '
        'target="_blank" rel="noopener noreferrer">'
        "Data Center Design Execution Lead</a>"
        in html
    )
    assert '<h2 id="passed-not-recommended">Passed / Not Recommended</h2>' in html

    assert "<style>" in html
    assert 'class="summary"' in html
    assert 'class="quick-view"' in html
    assert 'class="job-card top-match"' in html
    assert "<strong>Posting:</strong>" in html
    assert (
        '<a href="https://boards.greenhouse.io/exampleai/jobs/123" '
        'target="_blank" rel="noopener noreferrer">View posting</a>'
        in html
    )
    assert "<strong>Job Radar ID:</strong>" in html
    assert "<strong>URL:</strong>" not in html


def test_render_html_report_displays_not_eligible_job_and_reasons() -> None:
    posting = make_posting(title="Senior Infrastructure Engineer")
    scored_posting = ScoredPosting(
        posting=posting,
        score=140,
        score_reasons=[
            "+30 title:infrastructure",
            "+100 location_allowed:remote",
        ],
        location_status="allowed",
        top_match_eligible=True,
        eligibility=EligibilityResult(
            status="not_eligible",
            reasons=(
                EligibilityReason(
                    code="compensation_below_floor",
                    message="The advertised compensation is below the profile minimum.",
                ),
                EligibilityReason(
                    code="travel_exceeds_profile_limit",
                    message="Required travel exceeds the profile limit.",
                ),
            ),
        ),
    )
    report = ScanReport(
        companies_enabled=1,
        jobs_collected=1,
        jobs_new=1,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[posting],
        scored_postings=[scored_posting],
    )

    html = render_html_report(report)

    assert "<strong>Eligibility:</strong> Not Eligible" in html
    assert (
        "<strong>Eligibility reasons:</strong> "
        "The advertised compensation is below the profile minimum.; "
        "Required travel exceeds the profile limit."
        in html
    )
    assert '<section class="job-card top-match">' not in html
    assert '<section class="job-card review-needed">' not in html
    assert "<strong>Recommended action:</strong> Pass" in html
    assert "Senior Infrastructure Engineer" in html


def test_needs_review_eligibility_blocks_direct_apply_recommendation() -> None:
    from job_radar.recommendations import _get_action_rationale
    from job_radar.recommendations import _get_recommended_action
    from job_radar.resume_match import ResumeMatchResult

    posting = make_posting(title="Senior Site Reliability Engineer")
    scored_posting = ScoredPosting(
        posting=posting,
        score=180,
        score_reasons=[
            "+30 title:site reliability",
            "+10 body:linux",
            "+8 body:cluster",
            "+8 body:gpu",
            "+100 location_allowed:remote",
        ],
        location_status="allowed",
        top_match_eligible=True,
        review_needed_eligible=True,
        resume_match=ResumeMatchResult(
            label="Very Strong",
            evidence=[
                "Linux infrastructure",
                "cluster systems",
                "reliability engineering",
                "distributed compute",
            ],
            gaps=[],
        ),
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

    assert _get_recommended_action(scored_posting) == "Hold"
    assert _get_action_rationale(scored_posting) == (
        "Hold for eligibility review before applying. "
        "The posting does not provide usable compensation."
    )


def test_tracked_application_overrides_not_eligible_recommendation() -> None:
    from job_radar.recommendations import _get_recommended_action

    posting = make_posting(title="Senior Site Reliability Engineer")
    scored_posting = ScoredPosting(
        posting=posting,
        score=180,
        score_reasons=[
            "+30 title:site reliability",
            "+10 body:linux",
            "+100 location_allowed:remote",
        ],
        location_status="allowed",
        review_needed_eligible=True,
        eligibility=EligibilityResult(
            status="not_eligible",
            reasons=(
                EligibilityReason(
                    code="compensation_below_floor",
                    message="The advertised compensation is below the profile minimum.",
                ),
            ),
        ),
        application=ApplicationRecord(
            job_radar_id=posting.job_radar_id,
            company_name="Example AI",
            role_title="Senior Site Reliability Engineer",
            source_url=posting.source_url,
            status="interviewing",
            outcome="interviewing",
        ),
    )

    assert _get_recommended_action(scored_posting) == "Track Status"


def test_render_html_report_includes_passed_job_details() -> None:
    passed_posting = make_posting(title="Account Executive")

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=1,
        jobs_new=1,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[passed_posting],
        scored_postings=[],
        omitted_scored_postings=[
            ScoredPosting(
                posting=passed_posting,
                score=-60,
                score_reasons=["-60 title:account executive"],
                location_status="allowed",
            ),
        ],
    )

    html = render_html_report(report)

    assert '<h2 id="passed-not-recommended">Passed / Not Recommended</h2>' in html
    assert "<strong>Omitted jobs audit:</strong>" in html
    assert "<strong>Risk / pass signal summary:</strong>" in html
    assert html.count("One job may appear in more than one signal count.") == 2
    assert "Passed jobs most worth reviewing, up to 25" in html
    assert "Account Executive" in html
    assert "<strong>Score:</strong> -60" in html
    assert "<strong>Recommended action:</strong> Pass" in html
    assert "<strong>Why not recommended:</strong>" in html
    assert (
        '<a href="https://boards.greenhouse.io/exampleai/jobs/123" '
        'target="_blank" rel="noopener noreferrer">View posting</a>'
        in html
    )


def test_render_html_report_escapes_html_special_characters() -> None:
    posting = make_posting(
        title="Senior <Linux> & Infrastructure Engineer",
        company_name="Example & AI",
    )

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=1,
        jobs_new=1,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[posting],
    )

    html = render_html_report(report)

    assert "Senior &lt;Linux&gt; &amp; Infrastructure Engineer" in html
    assert "Example &amp; AI" in html


def test_render_html_report_includes_history_context() -> None:
    posting = make_posting(title="Senior Linux Infrastructure Engineer")

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=1,
        jobs_new=1,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[posting],
        scored_postings=[
            ScoredPosting(
                posting=posting,
                score=140,
                score_reasons=[
                    "+30 title:linux",
                    "+10 body:infrastructure",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=[
                    "score 140 meets top-match threshold 1",
                    "location fit is acceptable: allowed",
                    "strong signal matched: title:linux",
                ],
                history_context=[
                    "Strong / No Interview: 6",
                    "Very Strong / No Interview: 3",
                ],
            )
        ],
    )

    html = render_html_report(report)

    assert (
        "<li><strong>History context:</strong> "
        "Strong / No Interview: 6; Very Strong / No Interview: 3</li>"
        in html
    )


def test_render_html_report_includes_history_risk_summary() -> None:
    caution_posting = make_posting(
        title="Senior Site Reliability Engineer",
        company_name="Example AI",
    )
    blocker_posting = make_posting(
        title="Senior Kubernetes Platform Engineer",
        company_name="Example AI",
    )

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=2,
        jobs_new=2,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[caution_posting, blocker_posting],
        scored_postings=[
            ScoredPosting(
                posting=caution_posting,
                score=140,
                score_reasons=["+30 title:site reliability"],
                location_status="allowed",
                history_risk_level="caution",
                history_risk_reasons=["prior_no_interview_despite_strong_match"],
            ),
            ScoredPosting(
                posting=blocker_posting,
                score=140,
                score_reasons=["+24 title:kubernetes"],
                location_status="allowed",
                history_risk_level="blocker_review",
                history_risk_reasons=["prior_blocker:kubernetes_production"],
            ),
        ],
    )

    html = render_html_report(report)

    assert "<strong>History risk summary:</strong>" in html
    assert "<li>blocker_review: 1</li>" in html
    assert "<li>caution: 1</li>" in html


def test_render_html_report_includes_tracker_workflow_summary() -> None:
    report = ScanReport(
        companies_enabled=1,
        jobs_collected=1,
        jobs_new=1,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[make_posting()],
        tracker_workflow_summary={
            "waiting": 3,
            "stale": 2,
            "follow_up_due": 1,
        },
    )

    html = render_html_report(report)

    assert "<strong>Tracker workflow summary:</strong>" in html
    assert "<li>follow_up_due: 1</li>" in html
    assert "<li>waiting: 3</li>" in html
    assert "<li>stale: 2</li>" in html
    assert html.index("<li>follow_up_due: 1</li>") < html.index(
        "<li>waiting: 3</li>"
    )
    assert html.index("<li>waiting: 3</li>") < html.index("<li>stale: 2</li>")


def test_render_html_report_includes_tracker_action_summary() -> None:
    report = ScanReport(
        companies_enabled=1,
        jobs_collected=1,
        jobs_new=1,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[make_posting()],
        tracker_workflow_summary={
            "follow_up_due": 2,
            "needs_date_review": 1,
            "active_pipeline": 3,
            "dormant": 4,
            "stale": 5,
            "presumed_closed": 6,
            "waiting": 7,
            "closed": 8,
        },
    )

    html = render_html_report(report)

    assert "<strong>Tracker action summary:</strong>" in html
    assert "<li>Needs action: 6</li>" in html
    assert "<li>Needs review: 16</li>" in html
    assert html.index("<strong>Tracker action summary:</strong>") < html.index(
        "<strong>Tracker workflow summary:</strong>"
    )


def test_render_html_report_links_to_collector_errors_when_present() -> None:
    report = ScanReport(
        companies_enabled=1,
        jobs_collected=0,
        jobs_new=0,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[
            ScanError(
                company_key="example",
                company_name="Example",
                source_type="greenhouse",
                message="Temporary collection failure.",
            ),
        ],
        postings=[],
    )

    html = render_html_report(report)

    assert '<a href="#collector-errors">Collector Errors</a>' in html
    assert '<h2 id="collector-errors">Collector Errors</h2>' in html
    assert '<a href="#jobs">Jobs</a>' in html
    assert '<h2 id="jobs">Jobs</h2>' in html


def test_write_html_report_writes_file(tmp_path: Path) -> None:
    report_path = tmp_path / "today.html"
    report = ScanReport(
        companies_enabled=1,
        jobs_collected=1,
        jobs_new=1,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[make_posting()],
    )

    written_path = write_html_report(report_path, report)

    assert written_path == report_path
    assert report_path.exists()
    assert "<h1>junior Report</h1>" in report_path.read_text(encoding="utf-8")


def test_render_html_report_explains_top_match_and_review_needed_cards() -> None:
    top_match_posting = make_posting(title="Senior Linux Infrastructure Engineer")
    review_needed_posting = make_posting(title="Senior Systems Engineer")

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=2,
        jobs_new=2,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[top_match_posting, review_needed_posting],
        scored_postings=[
            ScoredPosting(
                posting=top_match_posting,
                score=140,
                score_reasons=[
                    "+30 title:linux",
                    "+10 body:infrastructure",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=[
                    "score 140 meets top-match threshold 1",
                    "location fit is acceptable: allowed",
                    "strong signal matched: title:linux",
                ],
            ),
            ScoredPosting(
                posting=review_needed_posting,
                score=120,
                score_reasons=[
                    "+20 title:systems",
                    "+10 body:infrastructure",
                    "+100 location_allowed:remote",
                ],
                location_status="mixed",
                review_needed_eligible=True,
            ),
        ],
    )

    html = render_html_report(report)

    assert "<strong>Why it is a top match:</strong>" in html
    assert "score 140 meets top-match threshold 1" in html
    assert "location fit is acceptable: allowed" in html
    assert "strong signal matched: title:linux" in html

    assert "<strong>Why it needs review:</strong>" in html
    assert (
        "This role has enough technical signal to review manually, "
        "but the location fit needs confirmation."
        in html
    )


def test_below_floor_compensation_blocks_recommendation() -> None:
    from job_radar.compensation import CompensationResult
    from job_radar.recommendations import _format_hiring_risk_flags
    from job_radar.recommendations import _get_recommended_action

    posting = make_posting(
        title="Senior Infrastructure Engineer",
    )

    scored_posting = ScoredPosting(
        posting=posting,
        score=180,
        score_reasons=[
            "+30 title:infrastructure",
            "+10 body:linux",
            "+8 body:cluster",
            "+8 body:gpu",
            "+100 location_allowed:remote",
        ],
        location_status="allowed",
        top_match_eligible=True,
        compensation=CompensationResult(
            label="Below floor",
            range_label="$100,000 - $140,000",
            min_usd=100000,
            max_usd=140000,
        ),
    )

    assert _format_hiring_risk_flags(scored_posting) == "below compensation floor"
    assert _get_recommended_action(scored_posting) == "Pass"


def test_clean_apply_requires_very_strong_resume_match() -> None:
    from job_radar.recommendations import _get_recommended_action
    from job_radar.resume_match import ResumeMatchResult

    posting = make_posting(
        title="Senior Site Reliability Engineer",
    )

    scored_posting = ScoredPosting(
        posting=posting,
        score=180,
        score_reasons=[
            "+30 title:site reliability",
            "+10 body:linux",
            "+8 body:cluster",
            "+8 body:gpu",
            "+100 location_allowed:remote",
        ],
        location_status="allowed",
        top_match_eligible=True,
        resume_match=ResumeMatchResult(
            label="Strong",
            evidence=["Linux infrastructure", "cluster systems"],
            gaps=[],
        ),
    )

    assert _get_recommended_action(scored_posting) == "Apply + Recruiter Message"


def test_clean_apply_allows_very_strong_resume_match() -> None:
    from job_radar.recommendations import _get_recommended_action
    from job_radar.resume_match import ResumeMatchResult

    posting = make_posting(
        title="Senior Site Reliability Engineer",
    )

    scored_posting = ScoredPosting(
        posting=posting,
        score=180,
        score_reasons=[
            "+30 title:site reliability",
            "+10 body:linux",
            "+8 body:cluster",
            "+8 body:gpu",
            "+100 location_allowed:remote",
        ],
        location_status="allowed",
        top_match_eligible=True,
        resume_match=ResumeMatchResult(
            label="Very Strong",
            evidence=[
                "Linux infrastructure",
                "cluster systems",
                "reliability engineering",
                "distributed compute",
            ],
            gaps=[],
        ),
    )

    assert _get_recommended_action(scored_posting) == "Apply"


def test_hiring_probability_requires_very_strong_resume_match_for_high() -> None:
    from job_radar.recommendations import _get_hiring_probability_label
    from job_radar.resume_match import ResumeMatchResult

    posting = make_posting(
        title="Senior Site Reliability Engineer",
    )

    scored_posting = ScoredPosting(
        posting=posting,
        score=180,
        score_reasons=[
            "+30 title:site reliability",
            "+10 body:linux",
            "+8 body:cluster",
            "+8 body:gpu",
            "+100 location_allowed:remote",
        ],
        location_status="allowed",
        top_match_eligible=True,
        resume_match=ResumeMatchResult(
            label="Strong",
            evidence=["Linux infrastructure", "cluster systems"],
            gaps=[],
        ),
    )

    assert _get_hiring_probability_label(scored_posting) == "Medium"


def test_hiring_probability_allows_high_with_very_strong_resume_match() -> None:
    from job_radar.recommendations import _get_hiring_probability_label
    from job_radar.resume_match import ResumeMatchResult

    posting = make_posting(
        title="Senior Site Reliability Engineer",
    )

    scored_posting = ScoredPosting(
        posting=posting,
        score=180,
        score_reasons=[
            "+30 title:site reliability",
            "+10 body:linux",
            "+8 body:cluster",
            "+8 body:gpu",
            "+100 location_allowed:remote",
        ],
        location_status="allowed",
        top_match_eligible=True,
        resume_match=ResumeMatchResult(
            label="Very Strong",
            evidence=[
                "Linux infrastructure",
                "cluster systems",
                "reliability engineering",
                "distributed compute",
            ],
            gaps=[],
        ),
    )

    assert _get_hiring_probability_label(scored_posting) == "High"


def test_hiring_probability_caps_weak_resume_match_at_low() -> None:
    from job_radar.recommendations import _get_hiring_probability_label
    from job_radar.resume_match import ResumeMatchResult

    posting = make_posting(
        title="Senior Site Reliability Engineer",
    )

    scored_posting = ScoredPosting(
        posting=posting,
        score=180,
        score_reasons=[
            "+30 title:site reliability",
            "+10 body:linux",
            "+8 body:cluster",
            "+8 body:gpu",
            "+100 location_allowed:remote",
        ],
        location_status="allowed",
        top_match_eligible=True,
        resume_match=ResumeMatchResult(
            label="Weak",
            evidence=[],
            gaps=["production Kubernetes ownership"],
        ),
    )

    assert _get_hiring_probability_label(scored_posting) == "Low"


def test_profile_avoid_match_blocks_recommendation() -> None:
    from job_radar.recommendations import _format_hiring_risk_flags
    from job_radar.recommendations import _get_recommended_action
    from job_radar.resume_match import ResumeMatchResult

    posting = make_posting(
        title="Senior Frontend Engineer",
    )

    scored_posting = ScoredPosting(
        posting=posting,
        score=180,
        score_reasons=[
            "+30 title:infrastructure",
            "+10 body:linux",
            "+8 body:cluster",
            "+8 body:gpu",
            "+100 location_allowed:remote",
        ],
        location_status="allowed",
        top_match_eligible=True,
        resume_match=ResumeMatchResult(
            label="Very Strong",
            evidence=[
                "Linux infrastructure",
                "cluster systems",
                "reliability engineering",
                "distributed compute",
            ],
            gaps=[],
        ),
        profile_avoid_matches=["frontend"],
    )

    hiring_risks = _format_hiring_risk_flags(scored_posting)

    assert "role family mismatch" in hiring_risks
    assert "profile avoid match: frontend" in hiring_risks
    assert _get_recommended_action(scored_posting) == "Pass"


def test_profile_avoid_match_blocks_even_without_existing_role_family_mismatch() -> None:
    from job_radar.recommendations import _format_hiring_risk_flags
    from job_radar.recommendations import _get_recommended_action
    from job_radar.resume_match import ResumeMatchResult

    posting = make_posting(
        title="Senior Infrastructure Engineer",
    )

    scored_posting = ScoredPosting(
        posting=posting,
        score=180,
        score_reasons=[
            "+30 title:infrastructure",
            "+10 body:linux",
            "+8 body:cluster",
            "+8 body:gpu",
            "+100 location_allowed:remote",
        ],
        location_status="allowed",
        top_match_eligible=True,
        resume_match=ResumeMatchResult(
            label="Very Strong",
            evidence=[
                "Linux infrastructure",
                "cluster systems",
                "reliability engineering",
                "distributed compute",
            ],
            gaps=[],
        ),
        profile_avoid_matches=["product management"],
    )

    assert _format_hiring_risk_flags(scored_posting) == (
        "profile avoid match: product management"
    )
    assert _get_recommended_action(scored_posting) == "Pass"


def test_render_html_report_includes_track_status_for_tracked_application() -> None:
    posting = make_posting(title="Senior Site Reliability Engineer")

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=1,
        jobs_new=0,
        jobs_seen=1,
        jobs_changed=0,
        collector_errors=[],
        postings=[posting],
        scored_postings=[
            ScoredPosting(
                posting=posting,
                score=180,
                score_reasons=[
                    "+30 title:site reliability",
                    "+10 body:linux",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                review_needed_eligible=True,
                application=ApplicationRecord(
                    job_radar_id=posting.job_radar_id,
                    company_name="Example AI",
                    role_title="Senior Site Reliability Engineer",
                    source_url=posting.source_url,
                    status="interviewing",
                    follow_up_on="2026-07-10",
                    outcome="interviewing",
                    notes="Recruiter replied.",
                ),
            )
        ],
    )

    html = render_html_report(report)

    assert "<strong>Track Status:</strong>" in html
    assert "<li>Status: interviewing</li>" in html
    assert "<li>Workflow: active_pipeline</li>" in html
    assert "<li>Follow up on: 2026-07-10</li>" in html
    assert "<li>Outcome: interviewing</li>" in html
    assert "<li>Notes: Recruiter replied.</li>" in html


def test_render_html_report_styles_track_status_as_tracked_application() -> None:
    posting = make_posting(title="Site Reliability Engineer")

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=1,
        jobs_new=1,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[posting],
        scored_postings=[
            ScoredPosting(
                posting=posting,
                score=120,
                score_reasons=[
                    "+30 title:site reliability",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=["eligible"],
                review_needed_eligible=True,
                history_risk_level="track_status",
                history_risk_reasons=["already_applied"],
            )
        ],
    )

    html = render_html_report(report)

    assert '<h2 id="tracked-applications">Tracked Applications</h2>' in html
    assert '<section class="job-card tracked-application">' in html
    assert '<section class="job-card review-needed">' not in html
    assert '<section class="job-card top-match">' not in html
    assert "<strong>Recommended action:</strong> Track Status" in html
