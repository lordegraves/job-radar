from job_radar.email_summary import (
    EMAIL_POSTINGS_LIMIT,
    build_email_body,
    build_email_html_body,
    build_email_subject,
    write_email_preview,
)
from job_radar.models import JobPosting
from job_radar.reporting import ScanReport, ScoredPosting


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
        jobs_stored=1,
        jobs_omitted=810,
        postings=[top_match],
        top_match_min_score=120,
        review_needed_min_score=100,
        scored_postings=[
            ScoredPosting(
                posting=top_match,
                score=158,
                score_reasons=[
                    "+24 title:data center",
                    "+10 body:linux",
                    "+100 location_allowed:remote",
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

    assert "Generated at: 2026-06-24 17:08 UTC" in body
    assert "Companies enabled: 3" in body
    assert "Jobs collected: 811" in body
    assert "Jobs stored: 1" in body
    assert "Jobs omitted: 810" in body
    assert "New jobs: 811" in body
    assert "Seen jobs: 0" in body
    assert "Changed jobs: 0" in body
    assert "Collector errors: 0" in body
    assert "Top match score threshold: 120" in body
    assert "Review-needed score threshold: 100" in body
    assert f"Top Matches, up to {EMAIL_POSTINGS_LIMIT}:" in body
    assert "1. Data Center Design Execution Lead" in body
    assert "   Company: Anthropic" in body
    assert "   Score: 158" in body
    assert "   Location: Remote" in body
    assert "   Technical match: Strong" in body
    assert "   Hiring probability: Medium" in body
    assert "   Recommended action: Tailor Resume" in body
    assert "   Hiring risks: generic remote competition" in body
    assert "   URL:" not in body
    assert "https://boards.greenhouse.io/anthropic/jobs/123" not in body
    assert "   Why it is a top match:" in body
    assert "      - score meets top match threshold" in body
    assert "      - location is acceptable" in body
    assert "      - required strong signal found" in body
    assert "   Why it scored:" not in body
    assert "   Signals: data center, linux" in body
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
                    "+100 location_allowed:remote",
                ],
                location_status="allowed",
                review_needed_eligible=True,
            ),
        ],
    )

    body = build_email_body(report, "reports/live-test.md")

    assert f"Review Needed, up to {EMAIL_POSTINGS_LIMIT}:" in body
    assert "1. Operations Sourcing Manager, Data Center" in body
    assert "   Company: Anthropic" in body
    assert "   Score: 151" in body
    assert "   Location: Remote" in body
    assert "   Technical match: Weak" in body
    assert "   Hiring probability: Low" in body
    assert "   Recommended action: Pass" in body
    assert "   Hiring risks: role family mismatch; generic remote competition" in body
    assert "   URL:" not in body
    assert "https://boards.greenhouse.io/anthropic/jobs/456" not in body
    assert "   Why it needs review:" in body
    assert "      - marked eligible by review-needed scoring rules" in body
    assert "      - location status: allowed" in body
    assert "   Why it scored:" not in body
    assert "   Signals: data center, infrastructure" in body


def test_build_email_body_includes_hiring_risk_action_for_false_positive() -> None:
    top_match = make_posting(
        title="Forward Deployed Engineer APAC",
        company_name="RunPod",
        location="Remote - APAC",
        source_url="https://jobs.ashbyhq.com/runpod/jobs/123",
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

    body = build_email_body(report, "reports/live-test.md")

    assert "1. Forward Deployed Engineer APAC" in body
    assert "   Company: RunPod" in body
    assert "   Location: Remote - APAC" in body
    assert "   Technical match: Weak" in body
    assert "   Hiring probability: Very Low" in body
    assert "   Recommended action: Pass" in body
    assert (
        "   Hiring risks: hard location mismatch; role family mismatch; "
        "generic remote competition"
        in body
    )


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
    assert f"Top Matches, up to {EMAIL_POSTINGS_LIMIT}:\n- None" in body
    assert f"Review Needed, up to {EMAIL_POSTINGS_LIMIT}:\n- None" in body


def test_build_email_body_limits_top_matches_and_review_needed() -> None:
    scored_postings: list[ScoredPosting] = []

    for index in range(EMAIL_POSTINGS_LIMIT + 1):
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

    assert f"{EMAIL_POSTINGS_LIMIT}. Top Match {EMAIL_POSTINGS_LIMIT - 1}" in body
    assert f"{EMAIL_POSTINGS_LIMIT + 1}. Top Match {EMAIL_POSTINGS_LIMIT}" not in body
    assert f"{EMAIL_POSTINGS_LIMIT}. Review Needed {EMAIL_POSTINGS_LIMIT - 1}" in body
    assert f"{EMAIL_POSTINGS_LIMIT + 1}. Review Needed {EMAIL_POSTINGS_LIMIT}" not in body


def test_build_email_body_handles_missing_location_and_empty_signals() -> None:
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
    assert "   URL:" not in body
    assert "   Why it scored:" not in body
    assert "   Signals: None" in body


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
    assert "Generated at: 2026-06-24 17:08 UTC" in preview_text
    assert f"Top Matches, up to {EMAIL_POSTINGS_LIMIT}:" in preview_text
    assert "1. Data Center Design Execution Lead" in preview_text
    assert "   Company: Anthropic" in preview_text
    assert "   Score: 158" in preview_text
    assert "Full report:" in preview_text
    assert "reports/live-test.md" in preview_text


def test_build_email_body_can_reference_attached_report_instead_of_path() -> None:
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

    body = build_email_body(
        report=report,
        report_path="reports/live-test.md",
        include_report_path=False,
    )

    assert "Full report:" in body
    assert "Attached as HTML file." in body
    assert "reports/live-test.md" not in body


def test_build_email_body_keeps_unparseable_generated_at_value() -> None:
    report = ScanReport(
        generated_at="not-a-timestamp",
        companies_enabled=0,
        jobs_collected=0,
        jobs_new=0,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[],
        scored_postings=[],
    )

    body = build_email_body(report, "reports/empty.md")

    assert "Generated at: not-a-timestamp" in body


def test_build_email_body_does_not_include_raw_posting_urls() -> None:
    top_match = make_posting(
        title="Data Center Design Execution Lead",
        company_name="Anthropic",
        source_url="https://job-boards.greenhouse.io/anthropic/jobs/123",
    )
    review_needed = make_posting(
        title="Operations Sourcing Manager, Data Center",
        company_name="Anthropic",
        source_url="https://job-boards.greenhouse.io/anthropic/jobs/456",
    )

    report = ScanReport(
        generated_at="2026-06-24T17:08:47+00:00",
        companies_enabled=3,
        jobs_collected=2,
        jobs_new=2,
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
                score_reasons=["+10 body:infrastructure"],
                location_status="allowed",
                review_needed_eligible=True,
            ),
        ],
    )

    body = build_email_body(report, "reports/live-test.md")

    assert "   URL:" not in body
    assert "https://job-boards.greenhouse.io/anthropic/jobs/123" not in body
    assert "https://job-boards.greenhouse.io/anthropic/jobs/456" not in body


def test_build_email_html_body_includes_clickable_posting_links() -> None:
    top_match = make_posting(
        title="Data Center Design Execution Lead",
        company_name="Anthropic",
        source_url="https://job-boards.greenhouse.io/anthropic/jobs/123",
    )
    review_needed = make_posting(
        title="Operations Sourcing Manager, Data Center",
        company_name="Anthropic",
        source_url="https://job-boards.greenhouse.io/anthropic/jobs/456",
    )

    report = ScanReport(
        generated_at="2026-06-24T17:08:47+00:00",
        companies_enabled=3,
        jobs_collected=2,
        jobs_new=2,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        jobs_stored=2,
        jobs_omitted=0,
        postings=[top_match, review_needed],
        scored_postings=[
            ScoredPosting(
                posting=top_match,
                score=158,
                score_reasons=["+24 title:data center"],
                location_status="allowed",
                top_match_eligible=True,
                top_match_reasons=[
                    "score 158 meets top-match threshold 120",
                    "location status is acceptable: allowed",
                    "strong signal matched: body:infrastructure",
                ],
            ),
            ScoredPosting(
                posting=review_needed,
                score=151,
                score_reasons=["+10 body:infrastructure"],
                location_status="allowed",
                review_needed_eligible=True,
            ),
        ],
    )

    html_body = build_email_html_body(
        report=report,
        report_path="reports/live-test.md",
        include_report_path=False,
    )

    assert "<h1>Job Radar Report</h1>" in html_body
    assert "Data Center Design Execution Lead" in html_body
    assert "Operations Sourcing Manager, Data Center" in html_body
    assert (
        '<a href="https://job-boards.greenhouse.io/anthropic/jobs/123">'
        "View posting</a>"
        in html_body
    )
    assert (
        '<a href="https://job-boards.greenhouse.io/anthropic/jobs/456">'
        "View posting</a>"
        in html_body
    )
    assert "Attached as HTML file." in html_body


def test_build_email_html_body_escapes_html_special_characters() -> None:
    top_match = make_posting(
        title="Senior <Linux> & Infrastructure Engineer",
        company_name="Example & AI",
        source_url="https://example.com/jobs?id=123&source=test",
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
                score_reasons=["+10 body:linux"],
                location_status="allowed",
                top_match_eligible=True,
            ),
        ],
    )

    html_body = build_email_html_body(report, "reports/live-test.md")

    assert "Senior &lt;Linux&gt; &amp; Infrastructure Engineer" in html_body
    assert "Example &amp; AI" in html_body
    assert 'href="https://example.com/jobs?id=123&amp;source=test"' in html_body