from pathlib import Path

from job_radar.models import JobPosting
from job_radar.reporting import (
    ScanError,
    ScanReport,
    ScoredPosting,
    render_markdown_report,
    write_markdown_report,
)


def make_posting(
    title: str = "Senior Infrastructure Engineer",
    company_name: str = "Example AI",
) -> JobPosting:
    return JobPosting(
        company_key="example_ai",
        company_name=company_name,
        source_type="greenhouse",
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


def test_render_markdown_report_includes_top_matches_and_all_jobs() -> None:
    high_score_posting = make_posting(title="Senior Kubernetes Platform Engineer")
    low_score_posting = make_posting(title="Account Executive")

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=2,
        jobs_new=2,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[high_score_posting, low_score_posting],
        scored_postings=[
            ScoredPosting(
                posting=high_score_posting,
                score=100,
                score_reasons=["+24 title:kubernetes"],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=["eligible"],
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
    assert "## All Jobs" in markdown
    assert markdown.index("## Top Matches") < markdown.index("## All Jobs")
    assert (
        "### [Senior Kubernetes Platform Engineer]"
        "(https://boards.greenhouse.io/exampleai/jobs/123)"
        in markdown
    )
    assert "### [Account Executive]" in markdown


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

    assert "### [Senior Kubernetes Engineer]" in markdown
    assert "### [Recruiting Coordinator]" in markdown

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

    assert "### [Head of FX & Risk]" in markdown
    assert "### [Staff Software Engineer, People Products]" in markdown
    assert "### [Data Center Strategic Sourcing Lead]" in markdown

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
    assert "### [Research Operations, External Artifacts]" in markdown


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
    assert "## All Jobs" in markdown

    assert markdown.index("## Top Matches") < markdown.index("## Review Needed")
    assert markdown.index("## Review Needed") < markdown.index("## All Jobs")

    review_needed_section = markdown.split("## Review Needed")[1].split("## All Jobs")[0]

    assert "### [Senior Systems Engineer]" in review_needed_section
    assert "### [Senior Linux Engineer]" in review_needed_section
    assert "### [Data Center Strategic Sourcing Lead]" in review_needed_section

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

    assert "- Generated at: 2026-06-24T12:34:56+00:00" in markdown