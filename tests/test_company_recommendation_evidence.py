"""Verify recommendation evidence uses bounded jobs from the owning profile."""

from pathlib import Path

from job_radar.company_recommendation_evidence import (
    aggregate_employer_job_evidence,
    format_job_evidence,
)
from job_radar.database import connect_database
from job_radar.models import JobPosting
from job_radar.profile_models import ManagedProfile, ProfilePreferences
from job_radar.profile_storage import create_profile
from job_radar.storage import start_scan_run, upsert_job_posting


def _profile(profile_id: str) -> ManagedProfile:
    return ManagedProfile(
        profile_id=profile_id,
        display_name="Synthetic Profile",
        preferences=ProfilePreferences(
            target_roles=("Platform Engineer",),
            work_arrangements=("Remote",),
        ),
    )


def _posting(
    job_id: str,
    title: str,
    remote_status: str = "Remote",
    salary_text: str | None = None,
) -> JobPosting:
    return JobPosting(
        company_key="example_compute",
        company_name="Example Compute",
        source_type="html",
        source_job_id=job_id,
        source_url=f"https://example.invalid/jobs/{job_id}",
        title=title,
        location="United States",
        remote_status=remote_status,
        salary_text=salary_text,
        description="Fictional description.",
        canonical_key=f"example-{job_id}",
        content_hash=f"hash-{job_id}",
    )


def test_evidence_counts_only_recent_jobs_from_the_named_profile(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    first = _profile("profile_aaaaaaaa")
    second = _profile("profile_bbbbbbbb")
    create_profile(database_path, first)
    create_profile(database_path, second)
    first_scan = start_scan_run(
        database_path,
        requested_at="2026-07-23T12:00:00+00:00",
        companies_requested=1,
        companies_enabled=1,
        profile_id=first.profile_id,
    )
    second_scan = start_scan_run(
        database_path,
        requested_at="2026-07-23T12:00:00+00:00",
        companies_requested=1,
        companies_enabled=1,
        profile_id=second.profile_id,
    )
    upsert_job_posting(
        database_path,
        _posting("1", "Senior Platform Engineer"),
        scan_run_id=first_scan,
    )
    upsert_job_posting(
        database_path,
        _posting("2", "Platform Support Engineer"),
        scan_run_id=first_scan,
    )
    upsert_job_posting(
        database_path,
        _posting("3", "Platform Engineer"),
        scan_run_id=second_scan,
    )

    evidence = aggregate_employer_job_evidence(
        database_path,
        profile=first,
        employer_id="example_compute",
    )
    score, reasons = format_job_evidence(evidence)

    assert evidence.relevant_jobs == 2
    assert evidence.strong_matches == 2
    assert evidence.remote_compatible_jobs == 2
    assert score > 0
    assert "2 recent jobs" in reasons[0]
    assert "2 were strong title matches" in reasons[1]


def test_old_and_unowned_scan_evidence_is_ignored(tmp_path: Path) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = _profile("profile_aaaaaaaa")
    create_profile(database_path, profile)
    owned_scan = start_scan_run(
        database_path,
        requested_at="2026-07-23T12:00:00+00:00",
        companies_requested=1,
        companies_enabled=1,
        profile_id=profile.profile_id,
    )
    legacy_scan = start_scan_run(
        database_path,
        requested_at="2026-07-23T12:00:00+00:00",
        companies_requested=1,
        companies_enabled=1,
    )
    upsert_job_posting(
        database_path,
        _posting("owned", "Platform Engineer"),
        scan_run_id=owned_scan,
    )
    upsert_job_posting(
        database_path,
        _posting("legacy", "Platform Engineer"),
        scan_run_id=legacy_scan,
    )
    with connect_database(database_path) as connection:
        connection.execute(
            """
            UPDATE job_seen_events
            SET created_at = '2000-01-01 00:00:00'
            WHERE scan_run_id = ?
            """,
            (owned_scan,),
        )

    evidence = aggregate_employer_job_evidence(
        database_path,
        profile=profile,
        employer_id="example_compute",
        recency_days=90,
    )
    assert evidence.relevant_jobs == 0


def test_evidence_query_honors_the_posting_limit(tmp_path: Path) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = _profile("profile_aaaaaaaa")
    create_profile(database_path, profile)
    scan_id = start_scan_run(
        database_path,
        requested_at="2026-07-23T12:00:00+00:00",
        companies_requested=1,
        companies_enabled=1,
        profile_id=profile.profile_id,
    )
    for index in range(5):
        upsert_job_posting(
            database_path,
            _posting(str(index), "Platform Engineer"),
            scan_run_id=scan_id,
        )

    evidence = aggregate_employer_job_evidence(
        database_path,
        profile=profile,
        employer_id="example_compute",
        max_postings=3,
    )
    assert evidence.relevant_jobs == 3


def test_reliable_compensation_and_workplace_conflicts_are_explained(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Synthetic Profile",
        preferences=ProfilePreferences(
            target_roles=("Platform Engineer",),
            work_arrangements=("Remote",),
            compensation_floor_usd=100000,
        ),
    )
    create_profile(database_path, profile)
    scan_id = start_scan_run(
        database_path,
        requested_at="2026-07-23T12:00:00+00:00",
        companies_requested=1,
        companies_enabled=1,
        profile_id=profile.profile_id,
    )
    upsert_job_posting(
        database_path,
        _posting(
            "1",
            "Platform Engineer",
            remote_status="On-site",
            salary_text="$70,000 - $80,000",
        ),
        scan_run_id=scan_id,
    )
    upsert_job_posting(
        database_path,
        _posting(
            "2",
            "Platform Engineer",
            salary_text="$120,000 - $140,000",
        ),
        scan_run_id=scan_id,
    )

    evidence = aggregate_employer_job_evidence(
        database_path,
        profile=profile,
        employer_id="example_compute",
    )
    score, reasons = format_job_evidence(evidence)

    assert evidence.location_conflicts == 1
    assert evidence.compensation_known == 2
    assert evidence.compensation_below_floor == 1
    assert score > 0
    assert any("workplace or location conflict" in reason for reason in reasons)
    assert any("below this profile's minimum" in reason for reason in reasons)
