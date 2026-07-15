from pathlib import Path

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
        score=140,
        score_reasons=[
            "+30 title:infrastructure",
            "+10 body:linux",
            "+0 location_allowed:remote",
        ],
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
