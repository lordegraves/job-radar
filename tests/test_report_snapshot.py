from pathlib import Path

from job_radar.compensation import CompensationResult
from job_radar.resume_match import ResumeMatchResult
from job_radar.models import JobPosting
from job_radar.report_snapshot import (
    build_report_snapshot,
    load_report_snapshot,
    write_report_snapshot,
)
from job_radar.reporting import ScanError, ScanReport
from job_radar.scored_posting import ScoredPosting
from job_radar.tracker.tracker_models import ApplicationRecord


def make_scored_posting(
    *,
    title: str,
    top_match_eligible: bool = False,
    review_needed_eligible: bool = False,
    tracked: bool = False,
    score: int = 140,
    score_reasons: list[str] | None = None,
    location_status: str | None = None,
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
            job_radar_id=posting.job_radar_id,
            company_name=posting.company_name,
            role_title=posting.title,
            source_url=posting.source_url,
            status="Applied",
            outcome="Pending / In Progress",
        )

    return ScoredPosting(
        posting=posting,
        score=score,
        score_reasons=score_reasons
        or [
            "+30 title:infrastructure",
            "+10 body:linux",
            "+0 location_allowed:remote",
        ],
        location_status=location_status,
        top_match_eligible=top_match_eligible,
        review_needed_eligible=review_needed_eligible,
        application=application,
    )


def make_report() -> ScanReport:
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
    passed = make_scored_posting(title="passed")

    return ScanReport(
        companies_enabled=1,
        jobs_collected=4,
        jobs_new=1,
        jobs_seen=3,
        jobs_changed=0,
        collector_errors=[
            ScanError(
                company_key="example",
                company_name="Example",
                source_type="greenhouse",
                message="Request timed out.",
            )
        ],
        postings=[
            top_match.posting,
            review_needed.posting,
            tracked.posting,
            passed.posting,
        ],
        scored_postings=[top_match, tracked],
        new_scored_postings=[review_needed],
        omitted_scored_postings=[review_needed, passed],
        generated_at="2026-07-15T12:00:00+00:00",
    )


def test_build_report_snapshot_partitions_gui_sections() -> None:
    snapshot = build_report_snapshot(make_report())

    assert snapshot.schema_version == 1
    assert snapshot.summary.generated_at == "2026-07-15T12:00:00+00:00"
    assert snapshot.summary.top_matches == 1
    assert snapshot.summary.review_needed == 1
    assert snapshot.summary.tracked_applications == 1
    assert snapshot.summary.new_jobs == 1
    assert snapshot.summary.collector_errors == 1

    assert [job.title for job in snapshot.top_matches] == ["top-match"]
    assert [job.title for job in snapshot.review_needed] == ["review-needed"]
    assert [job.title for job in snapshot.tracked_applications] == ["tracked"]
    assert [job.title for job in snapshot.new_jobs] == ["review-needed"]
    assert [job.title for job in snapshot.passed_not_recommended] == ["passed"]

    assert snapshot.top_matches[0].company == "Example"
    assert snapshot.top_matches[0].url == "https://example.com/top-match"
    assert snapshot.top_matches[0].recommended_action
    assert snapshot.top_matches[0].why_matched
    assert snapshot.top_matches[0].job_radar_id

    assert snapshot.collector_errors[0].company_key == "example"
    assert snapshot.collector_errors[0].message == "Request timed out."


def test_write_and_load_report_snapshot_round_trip(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "target-scan.json"

    written_path = write_report_snapshot(
        snapshot_path,
        make_report(),
    )
    loaded_snapshot = load_report_snapshot(snapshot_path)

    assert written_path == snapshot_path
    assert loaded_snapshot == build_report_snapshot(make_report())
    assert snapshot_path.read_text(encoding="utf-8").endswith("\n")


def test_build_report_snapshot_exposes_recommendation_quality_and_risks() -> None:
    posting = JobPosting(
        company_key="example",
        company_name="Example AI",
        source_type="greenhouse",
        source_job_id="security-role",
        source_url="https://example.com/security-role",
        title="Senior Software Engineer, Infrastructure Security",
        location="Remote",
        description="Own Kubernetes, GPU, and hardware infrastructure.",
        canonical_key="example:security-role",
        content_hash="security-role",
    )
    scored_posting = ScoredPosting(
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

    snapshot = build_report_snapshot(report)
    job = snapshot.top_matches[0]

    assert job.technical_match == "Strong"
    assert job.hiring_probability == "Medium"
    assert job.recommended_action == "Network First"
    assert job.hiring_risks == (
        "security-domain translation risk; "
        "software-heavy translation risk; "
        "production Kubernetes translation risk; "
        "generic remote competition"
    )


def test_build_report_snapshot_exposes_resume_and_compensation_fields() -> None:
    posting = JobPosting(
        company_key="example",
        company_name="Example AI",
        source_type="greenhouse",
        source_job_id="infra-role",
        source_url="https://example.com/infra-role",
        title="Senior Linux Infrastructure Engineer",
        location="Remote",
        description="Build Linux infrastructure and cluster systems.",
        canonical_key="example:infra-role",
        content_hash="infra-role",
    )
    scored_posting = ScoredPosting(
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
        compensation=CompensationResult(
            label="Meets floor",
            range_label="$180,000 - $220,000",
            min_usd=180000,
            max_usd=220000,
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

    snapshot = build_report_snapshot(report)
    job = snapshot.top_matches[0]

    assert job.resume_match == "Strong"
    assert job.resume_evidence == "Linux infrastructure; cluster systems"
    assert job.resume_gaps == "production Kubernetes ownership"
    assert job.compensation == "$180,000 - $220,000"


def test_build_report_snapshot_orders_passed_jobs_by_review_value() -> None:
    weak_business = make_scored_posting(
        title="Account Executive",
        score=50,
        score_reasons=[
            "-60 title:account executive",
            "+100 location_allowed:remote",
        ],
        location_status="allowed",
    )
    blocked_infrastructure = make_scored_posting(
        title="Senior Infrastructure Engineer APAC",
        score=40,
        score_reasons=[
            "+30 title:infrastructure",
            "+10 body:linux",
            "-100 location_skipped:apac",
        ],
        location_status="skipped",
    )

    report = ScanReport(
        companies_enabled=1,
        jobs_collected=2,
        jobs_new=2,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[
            weak_business.posting,
            blocked_infrastructure.posting,
        ],
        scored_postings=[],
        omitted_scored_postings=[
            weak_business,
            blocked_infrastructure,
        ],
    )

    snapshot = build_report_snapshot(report)

    assert [job.title for job in snapshot.passed_not_recommended] == [
        "Senior Infrastructure Engineer APAC",
        "Account Executive",
    ]


def test_build_report_snapshot_exposes_track_status_action() -> None:
    tracked = make_scored_posting(
        title="Site Reliability Engineer",
        top_match_eligible=True,
        review_needed_eligible=True,
        tracked=True,
    )
    report = ScanReport(
        companies_enabled=1,
        jobs_collected=1,
        jobs_new=1,
        jobs_seen=0,
        jobs_changed=0,
        collector_errors=[],
        postings=[tracked.posting],
        scored_postings=[tracked],
    )

    snapshot = build_report_snapshot(report)

    assert snapshot.top_matches == []
    assert snapshot.review_needed == []
    assert len(snapshot.tracked_applications) == 1
    assert snapshot.tracked_applications[0].recommended_action == "Track Status"
    assert snapshot.tracked_applications[0].action_rationale == (
        "You already applied for this job. "
        "Track the existing application instead of applying again."
    )
