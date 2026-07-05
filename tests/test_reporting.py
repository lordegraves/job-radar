from pathlib import Path

from job_radar.models import JobPosting
from job_radar.tracker.models import ApplicationRecord
from job_radar.reporting import (
    ScanError,
    ScanReport,
    ScoredPosting,
    render_html_report,
    render_markdown_report,
    write_html_report,
    write_markdown_report,
)


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


def test_render_markdown_report_includes_summary() -> None:
    report = ScanReport(
        companies_enabled=1,
        jobs_collected=1,
        jobs_new=1,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[make_posting()],
    )

    markdown = render_markdown_report(report)

    assert "# Job Radar Report" in markdown
    assert "- Companies enabled: 1" in markdown
    assert "- Jobs collected: 1" in markdown
    assert "- New jobs: 1" in markdown
    assert "- Seen jobs: 0" in markdown
    assert "- Changed jobs: 0" in markdown
    assert "- Collector errors: 0" in markdown


def test_render_markdown_report_includes_collector_errors() -> None:
    report = ScanReport(
        companies_enabled=1,
        jobs_collected=0,
        jobs_new=0,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[
            ScanError(
                company_key="example_ai",
                company_name="Example AI",
                source_type="greenhouse",
                message="Failed to fetch Greenhouse jobs",
            )
        ],
        postings=[],
    )

    markdown = render_markdown_report(report)

    assert "## Collector Errors" in markdown
    assert (
        "- example_ai (Example AI, greenhouse): Failed to fetch Greenhouse jobs"
        in markdown
    )


def test_render_markdown_report_includes_jobs() -> None:
    report = ScanReport(
        companies_enabled=1,
        jobs_collected=1,
        jobs_new=1,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[make_posting()],
    )

    markdown = render_markdown_report(report)

    assert "## Jobs" in markdown
    assert (
        "### [Senior Infrastructure Engineer]"
        "(https://boards.greenhouse.io/exampleai/jobs/123)"
        in markdown
    )
    assert "- Company: Example AI" in markdown
    assert "- Source: greenhouse" in markdown
    assert "- Location: Remote" in markdown
    assert "- URL: https://boards.greenhouse.io/exampleai/jobs/123" in markdown
    assert "- Job Radar ID: `jr-example_ai-" in markdown
    assert (
        "- Canonical key: `example_ai:senior-infrastructure-engineer:remote`"
        in markdown
    )


def test_render_markdown_report_handles_no_jobs() -> None:
    report = ScanReport(
        companies_enabled=1,
        jobs_collected=0,
        jobs_new=0,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[],
    )

    markdown = render_markdown_report(report)

    assert "No jobs were collected during this scan." in markdown


def test_write_markdown_report_writes_file(tmp_path: Path) -> None:
    report_path = tmp_path / "today.md"
    report = ScanReport(
        companies_enabled=1,
        jobs_collected=1,
        jobs_new=1,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[make_posting()],
    )

    written_path = write_markdown_report(report_path, report)

    assert written_path == report_path
    assert report_path.exists()
    assert "# Job Radar Report" in report_path.read_text(encoding="utf-8")


def test_render_markdown_report_includes_match_summary_and_work_arrangement() -> None:
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
            )
        ],
    )

    markdown = render_markdown_report(report)

    assert "- Score: 140" in markdown
    assert "- Why this matched: linux, infrastructure, remote" in markdown
    assert "- Score reasons:" not in markdown
    assert "- Work location fit: remote" in markdown
    assert "- Location status:" not in markdown


def test_render_markdown_report_includes_match_quality_action_and_hiring_risks() -> None:
    posting = make_posting(title="Senior Software Engineer, Infrastructure Security")

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
                score=200,
                score_reasons=[
                    "+30 title:infrastructure",
                    "+8 body:kubernetes",
                    "+8 body:gpu",
                    "+7 body:hardware",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=[
                    "score 200 meets top-match threshold 120",
                    "location fit is acceptable: allowed",
                    "strong signal matched: title:infrastructure",
                ],
            )
        ],
    )

    markdown = render_markdown_report(report)

    assert "- Technical match: Strong" in markdown
    assert "- Hiring probability: Medium" in markdown
    assert "- Recommended action: Network First" in markdown
    assert (
        "- Hiring risks: security-domain translation risk; "
        "software-heavy translation risk; "
        "production Kubernetes translation risk; generic remote competition"
        in markdown
    )


def test_render_markdown_report_keeps_medium_kubernetes_risk_out_of_top_matches() -> None:
    posting = make_posting(
        title="Senior Site Reliability Engineer",
        description=(
            "Own production Kubernetes clusters, support Linux infrastructure, "
            "and improve reliability for remote production systems."
        ),
        source_url="https://example.com/jobs/kubernetes-sre",
    )

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
                score=180,
                score_reasons=[
                    "+30 title:site reliability",
                    "+8 body:kubernetes",
                    "+10 body:linux",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=["eligible"],
                review_needed_eligible=True,
            )
        ],
    )

    markdown = render_markdown_report(report)

    top_matches_section = markdown.split("## Review Needed")[0]
    review_needed_section = markdown.split("## Review Needed")[1].split(
        "## Passed / Not Recommended"
    )[0]

    assert "### [Senior Site Reliability Engineer]" not in top_matches_section
    assert "### [Senior Site Reliability Engineer]" in review_needed_section
    assert "- Hiring probability: Medium" in review_needed_section
    assert (
        "- Hiring risks: production Kubernetes translation risk; "
        "generic remote competition"
        in review_needed_section
    )


def test_render_markdown_report_includes_history_context() -> None:
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
                    "Similar prior roles had strong technical match but low response",
                    "Strong / No Interview: 6",
                ],
            )
        ],
    )

    markdown = render_markdown_report(report)

    assert (
        "- History context: Similar prior roles had strong technical match but "
        "low response; Strong / No Interview: 6"
        in markdown
    )


def test_render_markdown_report_uses_none_when_history_context_is_missing() -> None:
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
            )
        ],
    )

    markdown = render_markdown_report(report)

    assert "- History context: None" in markdown


def test_render_markdown_report_flags_role_family_mismatch() -> None:
    posting = make_posting(title="Frontend Engineer - User Interface")

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
                score=170,
                score_reasons=[
                    "+10 body:linux",
                    "+10 body:infrastructure",
                    "+8 body:gpu",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=[
                    "score 170 meets top-match threshold 120",
                    "location fit is acceptable: allowed",
                    "strong signal matched: body:linux",
                ],
            )
        ],
    )

    markdown = render_markdown_report(report)

    assert "### [Engineering Manager - Product & Platform Delivery]" not in markdown
    assert (
        "1 scored jobs were not recommended for apply/review based on fit, "
        "location, compensation, or hiring-risk signals."
        in markdown
    )


def test_render_markdown_report_includes_top_matches_and_omitted_jobs_summary() -> None:
    high_score_posting = make_posting(title="Senior Kubernetes Platform Engineer")
    low_score_posting = make_posting(title="Account Executive")

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=2,
        jobs_new=1,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[high_score_posting, low_score_posting],
        jobs_stored=1,
        jobs_omitted=1,
        scored_postings=[
            ScoredPosting(
                posting=high_score_posting,
                score=100,
                score_reasons=["+24 title:kubernetes"],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=[
                    "score 100 meets top-match threshold 1",
                    "location fit is acceptable: allowed",
                    "strong signal matched: title:kubernetes",
                ],
            ),
            ScoredPosting(
                posting=low_score_posting,
                score=-60,
                score_reasons=["-60 title:account executive"],
                location_status="allowed",
            ),
        ],
    )

    markdown = render_markdown_report(report)

    assert "## Top Matches" in markdown
    assert "## Passed / Not Recommended" in markdown
    assert "## All Jobs" not in markdown
    assert markdown.index("## Top Matches") < markdown.index(
        "## Passed / Not Recommended"
    )
    top_matches_section = markdown.split("## Northern Colorado Highlights")[0]

    assert (
        "### [Senior Kubernetes Platform Engineer]"
        "(https://boards.greenhouse.io/exampleai/jobs/123)"
        in top_matches_section
    )
    assert "### [Account Executive]" not in top_matches_section
    assert "#### [Account Executive]" in markdown
    assert (
        "1 scored jobs were not recommended for apply/review based on fit, "
        "location, compensation, or hiring-risk signals."
        in markdown
    )


def test_render_markdown_report_includes_omitted_reason_summary() -> None:
    from job_radar.compensation import CompensationResult

    below_floor_posting = make_posting(title="Senior Infrastructure Engineer")
    frontend_posting = make_posting(title="Frontend Engineer")
    hold_posting = make_posting(title="Linux Engineer")
    not_top_review_posting = make_posting(title="Senior Site Reliability Engineer")

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=4,
        jobs_new=4,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[
            below_floor_posting,
            frontend_posting,
            hold_posting,
            not_top_review_posting,
        ],
        scored_postings=[
            ScoredPosting(
                posting=below_floor_posting,
                score=180,
                score_reasons=[
                    "+30 title:infrastructure",
                    "+10 body:linux",
                    "+8 body:cluster",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
                compensation=CompensationResult(
                    label="Below floor",
                    range_label="$120,000 - $150,000",
                    min_usd=120000,
                    max_usd=150000,
                ),
            ),
            ScoredPosting(
                posting=frontend_posting,
                score=180,
                score_reasons=[
                    "+10 body:linux",
                    "+10 body:infrastructure",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
            ),
            ScoredPosting(
                posting=hold_posting,
                score=80,
                score_reasons=[
                    "+10 body:linux",
                ],
                location_status="allowed",
                top_match_eligible=False,
                review_needed_eligible=False,
            ),
            ScoredPosting(
                posting=not_top_review_posting,
                score=180,
                score_reasons=[
                    "+30 title:site reliability",
                    "+10 body:linux",
                    "+8 body:cluster",
                    "+8 body:gpu",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=False,
                review_needed_eligible=False,
            ),
        ],
    )

    markdown = render_markdown_report(report)

    assert "## Passed / Not Recommended" in markdown
    assert "- Omitted jobs audit:" in markdown
    assert "- Risk / pass signal summary:" in markdown
    assert markdown.count("  - One job may appear in more than one signal count.") == 2
    assert markdown.count("  - Below compensation floor: 1") == 2
    assert markdown.count("  - Role family mismatch: 1") == 2
    assert markdown.count("  - Low hiring probability: 1") == 2
    assert markdown.count("  - Below Top Match / Review Needed threshold: 1") == 2


def test_render_markdown_report_includes_passed_job_details() -> None:
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

    markdown = render_markdown_report(report)

    assert "## Passed / Not Recommended" in markdown
    assert "### Passed jobs most worth reviewing, up to 25" in markdown
    assert "#### [Account Executive]" in markdown
    assert "- Company: Example AI" in markdown
    assert "- Score: -60" in markdown
    assert "- Recommended action: Pass" in markdown
    assert "- Why not recommended:" in markdown
    assert "- URL: https://boards.greenhouse.io/exampleai/jobs/123" in markdown
    assert "- Job Radar ID: `jr-example_ai-" in markdown


def test_top_matches_only_includes_allowed_locations_without_negative_title_matches() -> None:
    allowed_posting = make_posting(title="Senior Infrastructure Engineer")
    skipped_posting = make_posting(title="Senior Kubernetes Engineer")
    recruiting_posting = make_posting(title="Recruiting Coordinator")

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=3,
        jobs_new=3,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[allowed_posting, skipped_posting, recruiting_posting],
        scored_postings=[
            ScoredPosting(
                posting=allowed_posting,
                score=140,
                score_reasons=[
                    "+30 title:infrastructure",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=["eligible"],
            ),
            ScoredPosting(
                posting=skipped_posting,
                score=200,
                score_reasons=[
                    "+24 title:kubernetes",
                ],
                location_status="skipped",
            ),
            ScoredPosting(
                posting=recruiting_posting,
                score=80,
                score_reasons=[
                    "-36 title:recruiting",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
            ),
        ],
    )

    markdown = render_markdown_report(report)
    top_matches_section = markdown.split("## Review Needed")[0]

    assert "## Top Matches" in markdown
    assert "### [Senior Infrastructure Engineer]" in top_matches_section
    assert "### [Senior Kubernetes Engineer]" not in top_matches_section
    assert "### [Recruiting Coordinator]" not in top_matches_section

    review_needed_section = markdown.split("## Review Needed")[1].split(
        "## Passed / Not Recommended"
    )[0]
    passed_section = markdown.split("## Passed / Not Recommended")[1]

    assert "### [Senior Kubernetes Engineer]" not in review_needed_section
    assert "### [Recruiting Coordinator]" not in review_needed_section
    assert "#### [Senior Kubernetes Engineer]" in passed_section
    assert "#### [Recruiting Coordinator]" in passed_section
    assert "## Passed / Not Recommended" in markdown

def test_top_matches_excludes_business_roles_even_when_location_is_allowed() -> None:
    technical_posting = make_posting(title="Senior Infrastructure Engineer")
    finance_posting = make_posting(title="Head of FX & Risk")
    people_posting = make_posting(title="Staff Software Engineer, People Products")
    sourcing_posting = make_posting(title="Data Center Strategic Sourcing Lead")

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=4,
        jobs_new=4,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[
            technical_posting,
            finance_posting,
            people_posting,
            sourcing_posting,
        ],
        scored_postings=[
            ScoredPosting(
                posting=technical_posting,
                score=140,
                score_reasons=[
                    "+30 title:infrastructure",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=["eligible"],
            ),
            ScoredPosting(
                posting=finance_posting,
                score=120,
                score_reasons=[
                    "+6 body:systems",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
            ),
            ScoredPosting(
                posting=people_posting,
                score=120,
                score_reasons=[
                    "+6 body:systems",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
            ),
            ScoredPosting(
                posting=sourcing_posting,
                score=159,
                score_reasons=[
                    "+24 title:data center",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
            ),
        ],
    )

    markdown = render_markdown_report(report)
    top_matches_section = markdown.split("## Review Needed")[0]

    assert "### [Senior Infrastructure Engineer]" in top_matches_section
    assert "### [Head of FX & Risk]" not in top_matches_section
    assert "### [Staff Software Engineer, People Products]" not in top_matches_section
    assert "### [Data Center Strategic Sourcing Lead]" not in top_matches_section

    review_needed_section = markdown.split("## Review Needed")[1].split(
        "## Passed / Not Recommended"
    )[0]
    passed_section = markdown.split("## Passed / Not Recommended")[1]

    assert "### [Head of FX & Risk]" not in review_needed_section
    assert "### [Staff Software Engineer, People Products]" not in review_needed_section
    assert "### [Data Center Strategic Sourcing Lead]" not in review_needed_section
    assert "#### [Head of FX & Risk]" in passed_section
    assert "#### [Staff Software Engineer, People Products]" in passed_section
    assert "#### [Data Center Strategic Sourcing Lead]" in passed_section
    assert "## Passed / Not Recommended" in markdown

def test_top_matches_requires_strong_technical_signal() -> None:
    weak_posting = make_posting(title="Research Operations, External Artifacts")
    strong_posting = make_posting(title="Senior Kubernetes Platform Engineer")

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=2,
        jobs_new=2,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[weak_posting, strong_posting],
        scored_postings=[
            ScoredPosting(
                posting=weak_posting,
                score=106,
                score_reasons=[
                    "+6 body:systems",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
            ),
            ScoredPosting(
                posting=strong_posting,
                score=124,
                score_reasons=[
                    "+24 title:kubernetes",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=["eligible"]
            ),
        ],
    )

    markdown = render_markdown_report(report)
    top_matches_section = markdown.split("## Review Needed")[0]

    passed_section = markdown.split("## Passed / Not Recommended")[1]

    assert "### [Senior Kubernetes Platform Engineer]" in top_matches_section
    assert "### [Research Operations, External Artifacts]" not in top_matches_section
    assert "#### [Research Operations, External Artifacts]" in passed_section
    assert "## Passed / Not Recommended" in markdown


def test_render_markdown_report_includes_human_readable_match_summary() -> None:
    posting = make_posting(title="Data Center Design Execution Lead")

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
                score=158,
                score_reasons=[
                    "+10 body:infrastructure",
                    "+10 body:hpc",
                    "+8 body:datacenter",
                    "+24 title:data center",
                    "+6 body:systems",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=[
                    "score 158 meets top-match threshold 1",
                    "location fit is acceptable: allowed",
                    "strong signal matched: body:infrastructure",
                ],
            )
        ],
    )

    markdown = render_markdown_report(report)

    assert (
        "- Why this matched: infrastructure, hpc, datacenter, data center, "
        "systems, remote"
        in markdown
    )
    assert "- Score reasons:" not in markdown


def test_render_markdown_report_includes_location_reason_in_status() -> None:
    posting = make_posting(
        title="Data Center Hardware Engineer",
        company_name="AMD",
    )

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
                score=121,
                score_reasons=[
                    "+8 body:data center",
                    "+7 body:hardware",
                    "+6 body:systems",
                    "+100 location_allowed:fort collins",
                ],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=["eligible"],
            )
        ],
    )

    markdown = render_markdown_report(report)

    assert "- Work location fit: fort collins" in markdown
    assert "- Location status:" not in markdown


def test_render_markdown_report_includes_work_arrangement_summary() -> None:
    allowed_posting = make_posting(title="Senior Infrastructure Engineer")
    mixed_posting = make_posting(title="Senior Systems Engineer")
    unknown_posting = make_posting(title="Research Engineer")

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=3,
        jobs_new=3,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[allowed_posting, mixed_posting, unknown_posting],
        scored_postings=[
            ScoredPosting(
                posting=allowed_posting,
                score=140,
                score_reasons=[
                    "+30 title:infrastructure",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=["eligible"],
            ),
            ScoredPosting(
                posting=mixed_posting,
                score=100,
                score_reasons=[
                    "+100 location_allowed:remote",
                ],
                location_status="mixed",
            ),
            ScoredPosting(
                posting=unknown_posting,
                score=10,
                score_reasons=[
                    "+10 body:infrastructure",
                ],
                location_status="unknown",
            ),
        ],
    )

    markdown = render_markdown_report(report)

    assert "- Work location fit:" in markdown
    assert "  - Remote-friendly: 2" in markdown
    assert "  - Needs location confirmation: 1" in markdown
    assert "- Location statuses:" not in markdown


def test_render_markdown_report_includes_history_risk_summary() -> None:
    caution_posting = make_posting(
        title="Senior Site Reliability Engineer",
        company_name="Example AI",
    )
    blocker_posting = make_posting(
        title="Senior Kubernetes Platform Engineer",
        company_name="Example AI",
    )
    no_history_posting = make_posting(
        title="Senior Linux Infrastructure Engineer",
        company_name="Example AI",
    )

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=3,
        jobs_new=3,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[caution_posting, blocker_posting, no_history_posting],
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
            ScoredPosting(
                posting=no_history_posting,
                score=140,
                score_reasons=["+30 title:linux"],
                location_status="allowed",
            ),
        ],
    )

    markdown = render_markdown_report(report)

    assert "- History risk summary:" in markdown
    assert "  - blocker_review: 1" in markdown
    assert "  - caution: 1" in markdown
    assert "  - neutral:" not in markdown


def test_render_markdown_report_includes_companies_scanned_summary() -> None:
    anthropic_posting = make_posting(
        company_name="Anthropic",
        title="Senior Infrastructure Engineer",
    )
    scale_posting = make_posting(
        company_name="Scale AI",
        title="Data Center Engineer",
    )
    distro_posting = make_posting(
        company_name="Distro",
        title="Network Engineer",
    )

    report = ScanReport(
        companies_enabled=3,
        jobs_collected=3,
        jobs_new=3,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[anthropic_posting, scale_posting, distro_posting],
        scored_postings=[
            ScoredPosting(
                posting=anthropic_posting,
                score=140,
                score_reasons=["+100 location_allowed:remote"],
                location_status="allowed",
            ),
            ScoredPosting(
                posting=scale_posting,
                score=80,
                score_reasons=["-100 location_skipped:san francisco"],
                location_status="skipped",
            ),
            ScoredPosting(
                posting=distro_posting,
                score=10,
                score_reasons=["+10 body:infrastructure"],
                location_status="unknown",
            ),
        ],
    )

    markdown = render_markdown_report(report)

    assert "- Companies scanned:" in markdown
    assert "  - Anthropic: 1" in markdown
    assert "  - Scale AI: 1" in markdown
    assert "  - Distro: 1" in markdown


def test_render_markdown_report_includes_review_needed_section() -> None:
    top_match_posting = make_posting(title="Senior Infrastructure Engineer")
    mixed_posting = make_posting(title="Senior Systems Engineer")
    conditional_posting = make_posting(title="Senior Linux Engineer")
    allowed_high_score_posting = make_posting(
        title="Data Center Strategic Sourcing Lead"
    )
    weak_allowed_posting = make_posting(title="Administrative Assistant")
    skipped_posting = make_posting(title="Account Executive")

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=6,
        jobs_new=6,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[
            top_match_posting,
            mixed_posting,
            conditional_posting,
            allowed_high_score_posting,
            weak_allowed_posting,
            skipped_posting,
        ],
        scored_postings=[
            ScoredPosting(
                posting=top_match_posting,
                score=140,
                score_reasons=[
                    "+30 title:infrastructure",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=["eligible"],
                review_needed_eligible=False,
            ),
            ScoredPosting(
                posting=mixed_posting,
                score=120,
                score_reasons=[
                    "+20 title:systems",
                    "+10 body:infrastructure",
                    "+100 location_allowed:remote",
                ],
                location_status="mixed",
                review_needed_eligible=True,
            ),
            ScoredPosting(
                posting=conditional_posting,
                score=110,
                score_reasons=[
                    "+10 title:linux",
                    "+100 location_allowed:remote",
                ],
                location_status="conditional",
                review_needed_eligible=True,
            ),
            ScoredPosting(
                posting=allowed_high_score_posting,
                score=159,
                score_reasons=[
                    "+24 title:data center",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                review_needed_eligible=True,
            ),
            ScoredPosting(
                posting=weak_allowed_posting,
                score=106,
                score_reasons=[
                    "+6 body:systems",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                review_needed_eligible=False,
            ),
            ScoredPosting(
                posting=skipped_posting,
                score=-20,
                score_reasons=[
                    "-20 title:account executive",
                ],
                location_status="skipped",
                review_needed_eligible=False,
            ),
        ],
    )

    markdown = render_markdown_report(report)

    assert "## Top Matches" in markdown
    assert "## Review Needed" in markdown
    assert "## Passed / Not Recommended" in markdown
    assert "## All Jobs" not in markdown

    assert markdown.index("## Top Matches") < markdown.index("## Review Needed")
    assert markdown.index("## Review Needed") < markdown.index("## Passed / Not Recommended")

    review_needed_section = markdown.split("## Review Needed")[1].split("## Passed / Not Recommended")[0]

    assert "### [Senior Systems Engineer]" in review_needed_section
    assert "### [Senior Linux Engineer]" in review_needed_section
    assert "### [Data Center Strategic Sourcing Lead]" not in review_needed_section

    assert "### [Senior Infrastructure Engineer]" not in review_needed_section
    assert "### [Administrative Assistant]" not in review_needed_section
    assert "### [Account Executive]" not in review_needed_section

def test_render_markdown_report_includes_generated_at() -> None:
    report = ScanReport(
        generated_at="2026-06-24T12:34:56+00:00",
        companies_enabled=1,
        jobs_collected=0,
        jobs_new=0,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[],
    )

    markdown = render_markdown_report(report)

    assert "- Generated at: 2026-06-24 12:34 UTC" in markdown


def test_render_markdown_report_includes_source_type_summary() -> None:
    greenhouse_posting = make_posting(
        title="Infrastructure Engineer",
        company_name="Anthropic",
        source_type="greenhouse",
    )
    lever_posting = make_posting(
        title="Systems Engineer",
        company_name="Distro",
        source_type="lever",
    )

    report = ScanReport(
        companies_enabled=2,
        jobs_collected=3,
        jobs_new=3,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[
            greenhouse_posting,
            greenhouse_posting,
            lever_posting,
        ],
    )

    markdown = render_markdown_report(report)

    assert "- Source types:" in markdown
    assert "  - greenhouse: 2" in markdown
    assert "  - lever: 1" in markdown


def test_render_markdown_report_includes_stored_and_omitted_counts() -> None:
    report = ScanReport(
        companies_enabled=1,
        jobs_collected=10,
        jobs_new=1,
        jobs_seen=2,
        jobs_changed=0,
        collector_errors=[],
        postings=[make_posting()],
        jobs_stored=3,
        jobs_omitted=7,
    )

    markdown = render_markdown_report(report)

    assert "- Actionable jobs stored: 3" in markdown
    assert "- Jobs not actionable: 7" in markdown


def test_render_markdown_report_includes_tracker_workflow_summary() -> None:
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

    markdown = render_markdown_report(report)

    assert "- Tracker workflow summary:" in markdown
    assert "  - follow_up_due: 1" in markdown
    assert "  - waiting: 3" in markdown
    assert "  - stale: 2" in markdown
    assert markdown.index("  - follow_up_due: 1") < markdown.index("  - waiting: 3")
    assert markdown.index("  - waiting: 3") < markdown.index("  - stale: 2")


def test_render_markdown_report_keeps_unparseable_generated_at_value() -> None:
    report = ScanReport(
        generated_at="not-a-timestamp",
        companies_enabled=1,
        jobs_collected=0,
        jobs_new=0,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[],
    )

    markdown = render_markdown_report(report)

    assert "- Generated at: not-a-timestamp" in markdown


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

    assert "<h1>Job Radar Report</h1>" in html
    assert "<strong>Generated at:</strong> 2026-06-24 12:34 UTC" in html
    assert "<strong>Actionable jobs stored:</strong> 1" in html
    assert "<strong>Jobs not actionable:</strong> 0" in html
    assert "Data Center Design Execution Lead" in html
    assert (
        '<a href="https://boards.greenhouse.io/exampleai/jobs/123">'
        "Data Center Design Execution Lead</a>"
        in html
    )
    assert "<h2>Passed / Not Recommended</h2>" in html

    assert "<style>" in html
    assert 'class="summary"' in html
    assert 'class="quick-view"' in html
    assert 'class="job-card top-match"' in html
    assert "<strong>Posting:</strong>" in html
    assert "View posting</a>" in html
    assert "<strong>Job Radar ID:</strong>" in html
    assert "<strong>URL:</strong>" not in html


def test_render_markdown_report_orders_passed_jobs_by_review_value() -> None:
    weak_business_posting = make_posting(title="Account Executive")
    blocked_infra_posting = make_posting(title="Senior Infrastructure Engineer APAC")

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=2,
        jobs_new=2,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[weak_business_posting, blocked_infra_posting],
        scored_postings=[],
        omitted_scored_postings=[
            ScoredPosting(
                posting=weak_business_posting,
                score=50,
                score_reasons=[
                    "-60 title:account executive",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
            ),
            ScoredPosting(
                posting=blocked_infra_posting,
                score=40,
                score_reasons=[
                    "+30 title:infrastructure",
                    "+10 body:linux",
                    "-100 location_skipped:apac",
                ],
                location_status="skipped",
            ),
        ],
    )

    markdown = render_markdown_report(report)

    assert markdown.index("#### [Senior Infrastructure Engineer APAC]") < markdown.index(
        "#### [Account Executive]"
    )


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

    assert "<h2>Passed / Not Recommended</h2>" in html
    assert "<strong>Omitted jobs audit:</strong>" in html
    assert "<strong>Risk / pass signal summary:</strong>" in html
    assert html.count("One job may appear in more than one signal count.") == 2
    assert "Passed jobs most worth reviewing, up to 25" in html
    assert "Account Executive" in html
    assert "<strong>Score:</strong> -60" in html
    assert "<strong>Recommended action:</strong> Pass" in html
    assert "<strong>Why not recommended:</strong>" in html
    assert "View posting</a>" in html


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
    assert "<h1>Job Radar Report</h1>" in report_path.read_text(encoding="utf-8")


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


def test_render_markdown_report_explains_review_needed_cards() -> None:
    review_needed_posting = make_posting(title="Data Center Design Execution Lead")

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=1,
        jobs_new=1,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[review_needed_posting],
        scored_postings=[
            ScoredPosting(
                posting=review_needed_posting,
                score=158,
                score_reasons=[
                    "+10 body:infrastructure",
                    "+10 body:hpc",
                    "+8 body:datacenter",
                    "+24 title:data center",
                    "+6 body:systems",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                review_needed_eligible=True,
            )
        ],
    )

    markdown = render_markdown_report(report)

    assert "## Review Needed" in markdown
    assert "### [Data Center Design Execution Lead]" in markdown
    assert (
        "- Why it needs review: Network First recommended, "
        "but review risk first: leadership ambiguity risk."
        in markdown
    )
    assert (
        "- Why this matched: infrastructure, hpc, datacenter, data center, "
        "systems, remote"
        in markdown
    )


def test_render_markdown_report_flags_remote_region_mismatch() -> None:
    posting = JobPosting(
        company_key="example_ai",
        company_name="Example AI",
        source_type="greenhouse",
        source_job_id="123",
        source_url="https://boards.greenhouse.io/exampleai/jobs/123",
        title="Forward Deployed Engineer APAC",
        location="Remote - APAC",
        description="Build Linux infrastructure.",
        canonical_key="example_ai:forward-deployed-engineer-apac:remote-apac",
        content_hash="hash",
    )

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
                score=153,
                score_reasons=[
                    "+10 body:linux",
                    "+10 body:infrastructure",
                    "+8 body:gpu",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=["eligible"],
            )
        ],
    )

    markdown = render_markdown_report(report)

    passed_section = markdown.split("## Passed / Not Recommended")[1]

    assert "### [Forward Deployed Engineer APAC]" not in markdown.split(
        "## Passed / Not Recommended"
    )[0]
    assert "#### [Forward Deployed Engineer APAC]" in passed_section
    assert (
        "1 scored jobs were not recommended for apply/review based on fit, "
        "location, compensation, or hiring-risk signals."
        in markdown
    )


def test_render_markdown_report_flags_management_delivery_roles() -> None:
    posting = make_posting(title="Engineering Manager - Product & Platform Delivery")

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
                score=168,
                score_reasons=[
                    "+10 body:linux",
                    "+10 body:infrastructure",
                    "+8 body:kubernetes",
                    "+8 body:gpu",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=["eligible"],
            )
        ],
    )

    markdown = render_markdown_report(report)

    passed_section = markdown.split("## Passed / Not Recommended")[1]

    assert "### [Engineering Manager - Product & Platform Delivery]" not in markdown.split(
        "## Passed / Not Recommended"
    )[0]
    assert "#### [Engineering Manager - Product & Platform Delivery]" in passed_section
    assert (
        "1 scored jobs were not recommended for apply/review based on fit, "
        "location, compensation, or hiring-risk signals."
        in markdown
    )

def test_render_markdown_report_filters_business_and_strategy_false_positives() -> None:
    false_positive_titles = [
        "Director, GTM - Physical AI",
        "Senior Sales Engineer - Token Factory",
        "Commercial Customer Success Manager",
        "Project Executive",
        "GPU Cluster Architect",
        "Manager, HPC Storage Engineer",
        "Senior Incident Manager",
        "Field Services Manager - Mission Critical",
    ]

    scored_postings: list[ScoredPosting] = []

    for index, title in enumerate(false_positive_titles):
        posting = make_posting(title=title)
        scored_postings.append(
            ScoredPosting(
                posting=posting,
                score=168,
                score_reasons=[
                    "+10 body:linux",
                    "+10 body:infrastructure",
                    "+8 body:kubernetes",
                    "+8 body:gpu",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=["eligible"],
            )
        )

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=len(false_positive_titles),
        jobs_new=len(false_positive_titles),
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[scored_posting.posting for scored_posting in scored_postings],
        scored_postings=scored_postings,
    )

    markdown = render_markdown_report(report)

    passed_section = markdown.split("## Passed / Not Recommended")[1]
    report_before_passed_section = markdown.split("## Passed / Not Recommended")[0]

    for title in false_positive_titles:
        assert f"### [{title}]" not in report_before_passed_section
        assert f"#### [{title}]" in passed_section

    assert (
        f"{len(false_positive_titles)} scored jobs were not recommended for "
        "apply/review based on fit, location, compensation, or hiring-risk "
        "signals."
        in markdown
    )


def test_render_markdown_report_does_not_mark_lead_roles_as_clean_apply() -> None:
    lead_titles = [
        "Lead Software Systems Engineer - GPU Performance",
        "Data Center Design Execution Lead",
    ]

    scored_postings: list[ScoredPosting] = []

    for index, title in enumerate(lead_titles):
        posting = make_posting(title=title)
        scored_postings.append(
            ScoredPosting(
                posting=posting,
                score=168,
                score_reasons=[
                    "+10 body:linux",
                    "+10 body:infrastructure",
                    "+8 body:gpu",
                    "+8 body:cluster",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=["eligible"],
            )
        )

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=len(lead_titles),
        jobs_new=len(lead_titles),
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[scored_posting.posting for scored_posting in scored_postings],
        scored_postings=scored_postings,
    )

    markdown = render_markdown_report(report)

    for title in lead_titles:
        assert f"### [{title}]" in markdown

    assert "- Recommended action: Apply\n" not in markdown
    assert "- Recommended action: Apply + Recruiter Message" not in markdown
    assert "- Recommended action: Network First" in markdown
    assert "- Hiring risks: leadership ambiguity risk" in markdown


def test_render_markdown_report_marks_high_competition_employers_as_risky() -> None:
    posting = make_posting(
        title="Hardware Operations Engineer",
        company_name="OpenAI",
    )

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
                score=168,
                score_reasons=[
                    "+10 body:linux",
                    "+10 body:infrastructure",
                    "+8 body:gpu",
                    "+8 body:cluster",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=["eligible"],
            )
        ],
    )

    markdown = render_markdown_report(report)

    assert "### [Hardware Operations Engineer]" in markdown
    assert "- Technical match: Very Strong" in markdown
    assert "- Hiring probability: Medium" in markdown
    assert "- Recommended action: Apply + Recruiter Message" in markdown
    assert (
        "- Action rationale: Apply with recruiter outreach. Strong fit, but "
        "frame the high-competition employer clearly."
        in markdown
    )
    assert "- Hiring risks: high competition employer" in markdown
    assert "- Recommended action: Apply\n" not in markdown


def test_render_markdown_report_routes_software_security_roles_to_network_first() -> None:
    posting = make_posting(
        title="Software Engineer, Infrastructure Security",
        company_name="OpenAI",
    )

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
                score=168,
                score_reasons=[
                    "+10 body:linux",
                    "+10 body:infrastructure",
                    "+8 body:kubernetes",
                    "+8 body:gpu",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=["eligible"],
            )
        ],
    )

    markdown = render_markdown_report(report)

    assert "### [Software Engineer, Infrastructure Security]" in markdown
    assert "- Technical match: Strong" in markdown
    assert "- Hiring probability: Medium" in markdown
    assert "- Recommended action: Network First" in markdown
    assert (
        "- Action rationale: Network first. Useful technical signal, but direct "
        "apply is weaker because of "
        in markdown
    )
    assert "high competition employer" in markdown
    assert "security-domain translation risk" in markdown
    assert "software-heavy translation risk" in markdown
    assert "production Kubernetes translation risk" in markdown
    assert (
        "- Hiring risks: high competition employer; "
        "security-domain translation risk; "
        "software-heavy translation risk; "
        "production Kubernetes translation risk"
        in markdown
    )


def test_render_markdown_report_includes_resume_match_fields() -> None:
    from job_radar.resume_match import ResumeMatchResult

    posting = make_posting(
        title="Senior Linux Infrastructure Engineer",
    )
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
                resume_match=ResumeMatchResult(
                    label="Strong",
                    evidence=["Linux infrastructure", "cluster systems"],
                    gaps=["production Kubernetes ownership"],
                ),
            ),
        ],
    )

    markdown = render_markdown_report(report)

    assert "- Resume match: Strong" in markdown
    assert "- Resume evidence: Linux infrastructure; cluster systems" in markdown
    assert "- Resume gaps: production Kubernetes ownership" in markdown


def test_render_markdown_report_includes_compensation_fields() -> None:
    from job_radar.compensation import CompensationResult

    posting = make_posting(
        title="Senior Infrastructure Engineer",
    )

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
                    "+30 title:infrastructure",
                    "+10 body:linux",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
                compensation=CompensationResult(
                    label="Meets floor",
                    range_label="$180,000 - $220,000",
                    min_usd=180000,
                    max_usd=220000,
                ),
            ),
        ],
    )

    markdown = render_markdown_report(report)

    assert "- Compensation: Meets floor" in markdown
    assert "- Compensation range: $180,000 - $220,000" in markdown


def test_render_markdown_report_includes_clean_apply_action_rationale() -> None:
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

    markdown = render_markdown_report(report)

    assert "- Recommended action: Apply" in markdown
    assert (
        "- Action rationale: Clean apply: very strong technical match, very "
        "strong resume match, high hiring probability, and no hiring risks."
        in markdown
    )
    assert "- Hiring risks: None" in markdown


def test_clean_apply_rationale_includes_history_caution_without_changing_action() -> None:
    from job_radar.resume_match import ResumeMatchResult

    posting = make_posting(
        title="Senior Site Reliability Engineer",
        company_name="Example AI",
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
        history_context=[
            (
                "Prior similar application at Example AI ended "
                "No Interview despite Strong technical match"
            )
        ],
        history_risk_level="caution",
        history_risk_reasons=["prior_no_interview_despite_strong_match"],
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

    markdown = render_markdown_report(report)

    assert "- Recommended action: Track Status" in markdown
    assert "- History risk: caution: prior_no_interview_despite_strong_match" in markdown
    assert (
        "- Action rationale: You already applied for this job. Track the existing "
        "application instead of applying again."
        in markdown
    )


def test_blocker_review_history_marks_posting_as_previously_reviewed() -> None:
    from job_radar.reporting import (
        ScanReport,
        ScoredPosting,
        _get_recommended_action,
        render_markdown_report,
    )
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
        review_needed_eligible=False,
        resume_match=ResumeMatchResult(
            label="Very Strong",
            evidence=["Linux", "HPC", "Infrastructure"],
            gaps=[],
        ),
        history_context=[
            (
                "Previously reviewed and skipped similar role at Example AI; "
                "prior blocker: Role Family Mismatch"
            )
        ],
        history_risk_level="blocker_review",
        history_risk_reasons=["prior_blocker:family_mismatch_role"],
    )

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=1,
        jobs_new=0,
        jobs_seen=1,
        jobs_changed=0,
        collector_errors=[],
        postings=[posting],
        scored_postings=[scored_posting],
    )

    markdown = render_markdown_report(report)

    assert _get_recommended_action(scored_posting) == "Previously Reviewed"
    assert "- Recommended action: Previously Reviewed" in markdown
    assert (
        "- Why not recommended: Already reviewed in prior history; revisit only "
        "if something changed."
        in markdown
    )
    assert "## Top Matches\n\nNo top matches found." in markdown
    assert "## Passed / Not Recommended" in markdown


def test_recommendation_summary_counts_omitted_history_actions() -> None:
    apply_posting = make_posting(
        title="Senior Site Reliability Engineer",
        source_url="https://example.com/jobs/apply",
    )
    track_status_posting = make_posting(
        title="Site Reliability Engineer",
        source_url="https://example.com/jobs/track",
    )

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=2,
        jobs_new=0,
        jobs_seen=2,
        jobs_changed=0,
        collector_errors=[],
        postings=[apply_posting, track_status_posting],
        scored_postings=[
            ScoredPosting(
                posting=apply_posting,
                score=140,
                score_reasons=[
                    "+30 title:site reliability",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                top_match_eligible=True,
            ),
        ],
        omitted_scored_postings=[
            ScoredPosting(
                posting=track_status_posting,
                score=110,
                score_reasons=[
                    "+30 title:site reliability",
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                history_risk_level="track_status",
                history_risk_reasons=["already_applied"],
            ),
        ],
    )

    markdown = render_markdown_report(report)

    assert "  - Track Status: 1" in markdown
    assert "## Review Needed" in markdown
    assert "- Recommended action: Track Status" in markdown
    assert (
        "- Why it needs review: You already applied for this job. Track the existing "
        "application instead of applying again."
        in markdown
    )
    assert "- Why not recommended: Prior application history matches this role;" not in markdown


def test_below_floor_compensation_blocks_recommendation() -> None:
    from job_radar.compensation import CompensationResult
    from job_radar.reporting import _format_hiring_risk_flags
    from job_radar.reporting import _get_recommended_action

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
    from job_radar.reporting import _get_recommended_action
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
    from job_radar.reporting import _get_recommended_action
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
    from job_radar.reporting import _get_hiring_probability_label
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
    from job_radar.reporting import _get_hiring_probability_label
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
    from job_radar.reporting import _get_hiring_probability_label
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
    from job_radar.reporting import _format_hiring_risk_flags
    from job_radar.reporting import _get_recommended_action
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
    from job_radar.reporting import _format_hiring_risk_flags
    from job_radar.reporting import _get_recommended_action
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


def test_render_markdown_report_includes_track_status_for_tracked_application() -> None:
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

    markdown = render_markdown_report(report)

    assert "- Track Status:" in markdown
    assert "  - Status: interviewing" in markdown
    assert "  - Workflow: active_pipeline" in markdown
    assert "  - Follow up on: 2026-07-10" in markdown
    assert "  - Outcome: interviewing" in markdown
    assert "  - Notes: Recruiter replied." in markdown


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


def test_render_html_report_styles_track_status_as_review_needed() -> None:
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

    assert '<section class="job-card review-needed">' in html
    assert '<section class="job-card top-match">' not in html
    assert "<strong>Recommended action:</strong> Track Status" in html
