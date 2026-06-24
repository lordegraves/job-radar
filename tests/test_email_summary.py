from job_radar.email_summary import (
    build_email_body,
    build_email_subject,
    write_email_preview,
)
from job_radar.models import JobPosting
from job_radar.reporting import ScanReport, ScoredPosting


def make_posting(
    title: str,
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


def test_build_email_body_includes_top_matches_and_review_needed() -> None:
    top_match = make_posting(
        title="Data Center Design Execution Lead",
        company_name="Anthropic",
    )
    review_needed = make_posting(
        title="Operations Sourcing Manager, Data Center",
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
                score=151,
                score_reasons=["+24 title:data center"],
                location_status="allowed",
                review_needed_eligible=True,
            ),
        ],
    )

    body = build_email_body(report, "reports/live-test.md")

    assert "Generated at: 2026-06-24T17:08:47+00:00" in body
    assert "Companies enabled: 3" in body
    assert "Jobs collected: 811" in body
    assert "New jobs: 811" in body
    assert "Changed jobs: 0" in body
    assert "Collector errors: 0" in body
    assert "Top Matches:" in body
    assert "- Data Center Design Execution Lead - Anthropic - 158" in body
    assert "Review Needed:" in body
    assert "- Operations Sourcing Manager, Data Center - Anthropic - 151" in body
    assert "Full report:" in body
    assert "reports/live-test.md" in body


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
    assert "Top Matches:\n- None" in body
    assert "Review Needed:\n- None" in body


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
    assert "Top Matches:" in preview_text
    assert "- Data Center Design Execution Lead - Anthropic - 158" in preview_text
    assert "Full report:" in preview_text
    assert "reports/live-test.md" in preview_text