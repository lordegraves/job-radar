"""Verify outside-catalog discoveries are bounded, isolated, and reviewed."""

from pathlib import Path

from job_radar.database import connect_database
from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import upsert_employer_source
from job_radar.external_company_discovery_service import (
    MATCHED_EXISTING,
    NEEDS_ADMIN_REVIEW,
    UNSUPPORTED,
    build_external_company_candidates,
    send_external_candidate_to_review,
)
from job_radar.models import JobPosting
from job_radar.profile_models import ManagedProfile, ProfilePreferences
from job_radar.profile_storage import create_profile, set_active_profile
from job_radar.storage import start_scan_run, upsert_job_posting


def _profile(profile_id: str) -> ManagedProfile:
    return ManagedProfile(
        profile_id=profile_id,
        display_name="Synthetic Profile",
        preferences=ProfilePreferences(target_roles=("Baker",)),
    )


def _discover(
    database_path: Path,
    *,
    profile_id: str,
    company_key: str,
    company_name: str,
    source_type: str = "html",
    title: str = "Baker",
) -> int:
    scan_id = start_scan_run(
        database_path,
        requested_at="2026-07-23T12:00:00+00:00",
        companies_requested=1,
        companies_enabled=1,
        profile_id=profile_id,
    )
    upsert_job_posting(
        database_path,
        JobPosting(
            company_key=company_key,
            company_name=company_name,
            source_type=source_type,
            source_job_id=f"{company_key}-1",
            source_url=f"https://jobs.invalid/{company_key}/1",
            title=title,
            location="Remote",
            description="Fictional job.",
            canonical_key=f"{company_key}-1",
            content_hash=f"hash-{company_key}-1",
        ),
        scan_run_id=scan_id,
    )
    return scan_id


def test_candidate_generation_and_profile_isolation(tmp_path: Path) -> None:
    database_path = tmp_path / "junior.sqlite3"
    first = _profile("profile_aaaaaaaa")
    second = _profile("profile_bbbbbbbb")
    create_profile(database_path, first)
    create_profile(database_path, second)
    _discover(
        database_path,
        profile_id=first.profile_id,
        company_key="outside_bakery",
        company_name="Outside Bakery",
    )

    set_active_profile(database_path, first.profile_id)
    first_candidates = build_external_company_candidates(database_path)
    set_active_profile(database_path, second.profile_id)
    second_candidates = build_external_company_candidates(database_path)

    assert len(first_candidates) == 1
    assert first_candidates[0].proposed_name == "Outside Bakery"
    assert first_candidates[0].readiness_state == NEEDS_ADMIN_REVIEW
    assert "1 recent job" in first_candidates[0].evidence[0]
    assert second_candidates == ()


def test_existing_match_unsupported_source_and_stale_evidence(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = _profile("profile_aaaaaaaa")
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    upsert_employer_source(
        database_path,
        EmployerSource(
            employer_id="known_bakery",
            name="Known Bakery",
            source_type="html",
            source_config={"source_url": "https://known.invalid/jobs"},
        ),
    )
    _discover(
        database_path,
        profile_id=profile.profile_id,
        company_key="legacy_known",
        company_name="Known Bakery",
    )
    _discover(
        database_path,
        profile_id=profile.profile_id,
        company_key="unsupported_bakery",
        company_name="Unsupported Bakery",
        source_type="unsupported_fixture",
    )
    stale_scan = _discover(
        database_path,
        profile_id=profile.profile_id,
        company_key="stale_bakery",
        company_name="Stale Bakery",
    )
    with connect_database(database_path) as connection:
        connection.execute(
            """
            UPDATE job_seen_events
            SET created_at = '2000-01-01 00:00:00'
            WHERE scan_run_id = ?
            """,
            (stale_scan,),
        )

    candidates = {
        item.candidate_key: item
        for item in build_external_company_candidates(database_path)
    }
    assert candidates["legacy_known"].readiness_state == MATCHED_EXISTING
    assert candidates["legacy_known"].potential_existing_match == "known_bakery"
    assert candidates["unsupported_bakery"].readiness_state == UNSUPPORTED
    assert "stale_bakery" not in candidates


def test_external_candidate_flows_to_existing_review_queue(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    profile = _profile("profile_aaaaaaaa")
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)
    _discover(
        database_path,
        profile_id=profile.profile_id,
        company_key="outside_bakery",
        company_name="Outside Bakery",
    )
    build_external_company_candidates(database_path)

    result = send_external_candidate_to_review(
        database_path,
        profile_id=profile.profile_id,
        candidate_key="outside_bakery",
    )

    assert result.status == "PENDING_REVIEW"
    assert result.review_request_id
    with connect_database(database_path) as connection:
        review = connection.execute(
            """
            SELECT requesting_profile_id, submitted_company_name
            FROM employer_review_requests
            WHERE request_id = ?
            """,
            (result.review_request_id,),
        ).fetchone()
    assert review == (profile.profile_id, "Outside Bakery")
