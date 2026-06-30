from pathlib import Path

from job_radar.models import JobPosting
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
) -> JobPosting:
    return JobPosting(
        company_key="example_ai",
        company_name=company_name,
        source_type=source_type,
        source_job_id="123",
        source_url="https://boards.greenhouse.io/exampleai/jobs/123",
        title=title,
        location="Remote",
        description="Build Linux infrastructure.",
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


def test_render_markdown_report_includes_score_reasons_and_location_status() -> None:
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
                    "location status is acceptable: allowed",
                    "strong signal matched: title:linux",
                ],
            )
        ],
    )

    markdown = render_markdown_report(report)

    assert "- Score: 140" in markdown
    assert (
        "- Score reasons: +30 title:linux, +10 body:infrastructure, "
        "+100 location_allowed:remote"
        in markdown
    )
    assert "- Location status: allowed" in markdown


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
                    "location status is acceptable: allowed",
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
                    "location status is acceptable: allowed",
                    "strong signal matched: body:linux",
                ],
            )
        ],
    )

    markdown = render_markdown_report(report)

    assert "### [Engineering Manager - Product & Platform Delivery]" not in markdown
    assert (
        "1 scored jobs were omitted because they did not qualify as actionable "
        "Top Match or Review Needed roles."
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
                    "location status is acceptable: allowed",
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
    assert "## Omitted Jobs" in markdown
    assert "## All Jobs" not in markdown
    assert markdown.index("## Top Matches") < markdown.index("## Omitted Jobs")
    assert (
        "### [Senior Kubernetes Platform Engineer]"
        "(https://boards.greenhouse.io/exampleai/jobs/123)"
        in markdown
    )
    assert "### [Account Executive]" not in markdown
    assert (
        "1 scored jobs were omitted because they did not qualify as actionable "
        "Top Match or Review Needed roles."
        in markdown
    )


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

    assert "### [Senior Kubernetes Engineer]" not in markdown
    assert "### [Recruiting Coordinator]" not in markdown
    assert "## Omitted Jobs" in markdown

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

    assert "### [Head of FX & Risk]" not in markdown
    assert "### [Staff Software Engineer, People Products]" not in markdown
    assert "### [Data Center Strategic Sourcing Lead]" not in markdown
    assert "## Omitted Jobs" in markdown

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

    assert "### [Senior Kubernetes Platform Engineer]" in top_matches_section
    assert "### [Research Operations, External Artifacts]" not in top_matches_section
    assert "### [Research Operations, External Artifacts]" not in markdown
    assert "## Omitted Jobs" in markdown


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
                    "location status is acceptable: allowed",
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
    assert "- Score reasons:" in markdown


def test_render_markdown_report_includes_location_status_summary() -> None:
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

    assert "- Location statuses:" in markdown
    assert "  - allowed: 1" in markdown
    assert "  - mixed: 1" in markdown
    assert "  - unknown: 1" in markdown


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
    assert "## Omitted Jobs" in markdown
    assert "## All Jobs" not in markdown

    assert markdown.index("## Top Matches") < markdown.index("## Review Needed")
    assert markdown.index("## Review Needed") < markdown.index("## Omitted Jobs")

    review_needed_section = markdown.split("## Review Needed")[1].split("## Omitted Jobs")[0]

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

    assert "- Jobs stored: 3" in markdown
    assert "- Jobs omitted: 7" in markdown


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
    assert "<strong>Jobs stored:</strong> 1" in html
    assert "<strong>Jobs omitted:</strong> 0" in html
    assert "Data Center Design Execution Lead" in html
    assert (
        '<a href="https://boards.greenhouse.io/exampleai/jobs/123">'
        "Data Center Design Execution Lead</a>"
        in html
    )
    assert "<h2>Omitted Jobs</h2>" in html

    assert "<style>" in html
    assert 'class="summary"' in html
    assert 'class="quick-view"' in html
    assert 'class="job-card top-match"' in html
    assert "<strong>Posting:</strong>" in html
    assert "View posting</a>" in html
    assert "<strong>URL:</strong>" not in html


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
                    "location status is acceptable: allowed",
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
    assert "location status is acceptable: allowed" in html
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
        "- Why it needs review: This role has enough signal to review manually, "
        "but it did not qualify as a Top Match."
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

    assert "### [Forward Deployed Engineer APAC]" not in markdown
    assert (
        "1 scored jobs were omitted because they did not qualify as actionable "
        "Top Match or Review Needed roles."
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

    assert "### [Engineering Manager - Product & Platform Delivery]" not in markdown
    assert (
        "1 scored jobs were omitted because they did not qualify as actionable "
        "Top Match or Review Needed roles."
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

    for title in false_positive_titles:
        assert f"### [{title}]" not in markdown

    assert (
        f"{len(false_positive_titles)} scored jobs were omitted because they did not "
        "qualify as actionable Top Match or Review Needed roles."
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
    assert "- Recommended action: Apply + Recruiter Message" in markdown
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
        "- Hiring risks: high competition employer; "
        "security-domain translation risk; "
        "software-heavy translation risk; "
        "production Kubernetes translation risk"
        in markdown
    )
    