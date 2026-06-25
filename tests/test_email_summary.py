from job_radar.email_summary import (
    build_email_body,
    build_email_subject,
    write_email_preview,
)
from job_radar.models import JobPosting
from job_radar.reporting import TOP_MATCHES_LIMIT, ScanReport, ScoredPosting


def make_posting(
    title: str,
    company_name: str = "Example AI",
    source_job_id: str = "123",
    location: str = "Remote",
    source_url: str = "https://boards.greenhouse.io/exampleai/jobs/123",
) -> JobPosting:
    return JobPosting(
        company_key="example_ai",
        company_name=company_name,
        source_type="greenhouse",
        source_job_id=source_job_id,
        source_url=source_url,
        title=title,
        location=location,
        description="Example description",
    )


def test_build_email_subject_summarizes_report() -> None:
    top_match = make_posting(
        title="Data Center Design Execution Lead",
        company_name="Anthropic",
    )
    review_needed = make_posting(
        title="Data Center Strategic Sourcing Lead",
        company_name="Anthropic",
    )

    report = ScanReport(
        generated_at="2026-06-24T17:08:47+00:00",
        companies_enabled=3,
        jobs_collected=811,
        jobs_new=811,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[top_match, review_needed],
        scored_postings=[
            ScoredPosting(
                posting=top_match,
                score=158,
                score_reasons=["+24 title:data center"],
                location_status="allowed",
                top_match_eligible=True,
            ),
            ScoredPosting(
                posting=review_needed,
                score=159,
                score_reasons=["+24 title:data center"],
                location_status="allowed",
                review_needed_eligible=True,
            ),
        ],
    )

    subject = build_email_subject(report)

    assert subject == (
        "Job Radar Report - 2026-06-24 - "
        "811 jobs - 1 top match - 1 review needed"
    )


def test_build_email_body_includes_rich_top_match_details() -> None:
    top_match = make_posting(
        title="Data Center Design Execution Lead",
        company_name="Anthropic",
        source_url="https://boards.greenhouse.io/anthropic/jobs/123",
    )

    report = ScanReport(
        generated_at="2026-06-24T17:08:47+00:00",
        companies_enabled=3,
        jobs_collected=811,
        jobs_new=811,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[top_match],
        scored_postings=[
            ScoredPosting(
                posting=top_match,
                score=158,
                score_reasons=[
                    "+24 title:data center",
                    "+10 body:linux",
                ],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=[
                    "score meets top match threshold",
                    "location is acceptable",
                    "required strong signal found",
                ],
            ),
        ],
    )

    body = build_email_body(report, "reports/live-test.md")

    assert "Generated at: 2026-06-24T17:08:47+00:00" in body
    assert "Companies enabled: 3" in body
    assert "Jobs collected: 811" in body
    assert "New jobs: 811" in body
    assert "Seen jobs: 0" in body
    assert "Changed jobs: 0" in body
    assert "Collector errors: 0" in body
    assert f"Top Matches, up to {TOP_MATCHES_LIMIT}:" in body
    assert "1. Data Center Design Execution Lead" in body
    assert "   Company: Anthropic" in body
    assert "   Score: 158" in body
    assert "   Location: Remote" in body
    assert "   URL: https://boards.greenhouse.io/anthropic/jobs/123" in body
    assert "   Why it is a top match:" in body
    assert "      - score meets top match threshold" in body
    assert "      - location is acceptable" in body
    assert "      - required strong signal found" in body
    assert "   Why it scored:" in body
    assert "      - +24 title:data center" in body
    assert "      - +10 body:linux" in body
    assert "Full report:" in body
    assert "reports/live-test.md" in body


def test_build_email_body_includes_rich_review_needed_details() -> None:
    review_needed = make_posting(
        title="Operations Sourcing Manager, Data Center",
        company_name="Anthropic",
        source_url="https://boards.greenhouse.io/anthropic/jobs/456",
    )

    report = ScanReport(
        generated_at="2026-06-24T17:08:47+00:00",
        companies_enabled=3,
        jobs_collected=811,
        jobs_new=811,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[review_needed],
        scored_postings=[
            ScoredPosting(
                posting=review_needed,
                score=151,
                score_reasons=[
                    "+24 title:data center",
                    "+10 body:infrastructure",
                ],
                location_status="allowed",
                review_needed_eligible=True,
            ),
        ],
    )

    body = build_email_body(report, "reports/live-test.md")

    assert f"Review Needed, up to {TOP_MATCHES_LIMIT}:" in body
    assert "1. Operations Sourcing Manager, Data Center" in body
    assert "   Company: Anthropic" in body
    assert "   Score: 151" in body
    assert "   Location: Remote" in body
    assert "   URL: https://boards.greenhouse.io/anthropic/jobs/456" in body
    assert "   Why it needs review:" in body
    assert "      - marked eligible by review-needed scoring rules" in body
    assert "      - location status: allowed" in body
    assert "   Why it scored:" in body
    assert "      - +24 title:data center" in body
    assert "      - +10 body:infrastructure" in body


def test_build_email_body_handles_empty_sections() -> None:
    report = ScanReport(
        generated_at=None,
        companies_enabled=0,
        jobs_collected=0,
        jobs_new=0,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[],
        scored_postings=[],
    )

    subject = build_email_subject(report)
    body = build_email_body(report, "reports/empty.md")

    assert subject == (
        "Job Radar Report - unknown-date - "
        "0 jobs - 0 top matches - 0 review needed"
    )
    assert "Generated at: Unknown" in body
    assert f"Top Matches, up to {TOP_MATCHES_LIMIT}:\n- None" in body
    assert f"Review Needed, up to {TOP_MATCHES_LIMIT}:\n- None" in body


def test_build_email_body_limits_top_matches_and_review_needed() -> None:
    scored_postings: list[ScoredPosting] = []

    for index in range(TOP_MATCHES_LIMIT + 1):
        top_match = make_posting(
            title=f"Top Match {index}",
            source_job_id=f"top-{index}",
            source_url=f"https://example.com/top-{index}",
        )
        review_needed = make_posting(
            title=f"Review Needed {index}",
            source_job_id=f"review-{index}",
            source_url=f"https://example.com/review-{index}",
        )

        scored_postings.extend(
            [
                ScoredPosting(
                    posting=top_match,
                    score=200 - index,
                    score_reasons=["+24 title:data center"],
                    location_status="allowed",
                    top_match_eligible=True,
                ),
                ScoredPosting(
                    posting=review_needed,
                    score=150 - index,
                    score_reasons=["+24 title:data center"],
                    location_status="allowed",
                    review_needed_eligible=True,
                ),
            ]
        )

    report = ScanReport(
        generated_at="2026-06-24T17:08:47+00:00",
        companies_enabled=1,
        jobs_collected=len(scored_postings),
        jobs_new=len(scored_postings),
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[scored_posting.posting for scored_posting in scored_postings],
        scored_postings=scored_postings,
    )

    body = build_email_body(report, "reports/live-test.md")

    assert f"{TOP_MATCHES_LIMIT}. Top Match {TOP_MATCHES_LIMIT - 1}" in body
    assert f"{TOP_MATCHES_LIMIT + 1}. Top Match {TOP_MATCHES_LIMIT}" not in body
    assert f"{TOP_MATCHES_LIMIT}. Review Needed {TOP_MATCHES_LIMIT - 1}" in body
    assert f"{TOP_MATCHES_LIMIT + 1}. Review Needed {TOP_MATCHES_LIMIT}" not in body


def test_build_email_body_handles_missing_location_and_url() -> None:
    top_match = make_posting(
        title="Linux Infrastructure Engineer",
        location="",
        source_url="",
    )

    report = ScanReport(
        generated_at="2026-06-24T17:08:47+00:00",
        companies_enabled=1,
        jobs_collected=1,
        jobs_new=1,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[top_match],
        scored_postings=[
            ScoredPosting(
                posting=top_match,
                score=140,
                score_reasons=[],
                location_status="unknown",
                top_match_eligible=True,
            ),
        ],
    )

    body = build_email_body(report, "reports/live-test.md")

    assert "1. Linux Infrastructure Engineer" in body
    assert "   Location: Unknown" in body
    assert "   URL: Unknown" in body
    assert "   Why it scored:" in body
    assert "      - None" in body


def test_write_email_preview_writes_subject_and_body(tmp_path) -> None:
    top_match = make_posting(
        title="Data Center Design Execution Lead",
        company_name="Anthropic",
    )

    report = ScanReport(
        generated_at="2026-06-24T17:08:47+00:00",
        companies_enabled=3,
        jobs_collected=811,
        jobs_new=811,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[top_match],
        scored_postings=[
            ScoredPosting(
                posting=top_match,
                score=158,
                score_reasons=["+24 title:data center"],
                location_status="allowed",
                top_match_eligible=True,
            ),
        ],
    )

    preview_path = tmp_path / "email-preview.txt"

    written_path = write_email_preview(
        preview_path,
        report,
        "reports/live-test.md",
    )

    preview_text = written_path.read_text(encoding="utf-8")

    assert written_path == preview_path
    assert preview_text.startswith(
        "Subject: Job Radar Report - 2026-06-24 - "
        "811 jobs - 1 top match - 0 review needed"
    )
    assert "Generated at: 2026-06-24T17:08:47+00:00" in preview_text
    assert f"Top Matches, up to {TOP_MATCHES_LIMIT}:" in preview_text
    assert "1. Data Center Design Execution Lead" in preview_text
    assert "   Company: Anthropic" in preview_text
    assert "   Score: 158" in preview_text
    assert "Full report:" in preview_text
    assert "reports/live-test.md" in preview_text