"""Tests that source-data quality gates recommendation eligibility."""

from datetime import UTC, datetime, timedelta

from job_radar.collectors.incremental_cache import (
    CACHE_CONFIG_KEY,
    DETAIL_PLANNER_CONFIG_KEY,
)
from job_radar.detail_retrieval import DetailRetrievalDecision
from job_radar.models import JobPosting
from job_radar.scan_service import (
    _apply_normalization_quality_gate,
    _fresh_cached_fallback_postings,
)
from job_radar.storage import CachedSourcePosting


def _posting(state: str) -> JobPosting:
    return JobPosting(
        company_key="example",
        company_name="Example",
        source_type="html",
        source_url="https://example.com/job/1",
        title="Infrastructure Engineer",
        location="Remote",
        description=None,
        normalization_state=state,
    )


def test_incomplete_posting_is_downgraded_to_needs_review() -> None:
    result = _apply_normalization_quality_gate(
        _posting("incomplete"),
        top_match_eligible=True,
        review_needed_eligible=True,
        potential_top_match_eligible=True,
    )

    assert result == (False, True, False)


def test_proven_unrelated_title_remains_excluded() -> None:
    result = _apply_normalization_quality_gate(
        _posting("skipped_unrelated"),
        top_match_eligible=False,
        review_needed_eligible=True,
        potential_top_match_eligible=False,
    )

    assert result == (False, False, False)


def test_complete_posting_preserves_evaluation_results() -> None:
    result = _apply_normalization_quality_gate(
        _posting("complete"),
        top_match_eligible=True,
        review_needed_eligible=False,
        potential_top_match_eligible=True,
    )

    assert result == (True, False, True)


def test_recent_source_cache_can_be_used_as_explicit_fallback() -> None:
    cached = CachedSourcePosting(
        posting=JobPosting(
            company_key="example",
            company_name="Example",
            source_type="workday",
            source_url="https://example.com/job/1",
            title="Infrastructure Engineer",
            location="Remote",
            description="Operate reliable Linux infrastructure. " * 10,
            source_job_id="1",
        ),
        listing_fingerprint="fingerprint",
        detail_verified_at=datetime.now(UTC).isoformat(),
    )

    result = _fresh_cached_fallback_postings(
        {CACHE_CONFIG_KEY: {"1": cached}}
    )

    assert len(result) == 1
    assert result[0].detail_retrieval_state == "cached_source_fallback"
    assert "source_cache_fallback" in result[0].normalization_issues


def test_expired_source_cache_is_not_used_as_fallback() -> None:
    cached = CachedSourcePosting(
        posting=_posting("complete"),
        listing_fingerprint="fingerprint",
        detail_verified_at=(datetime.now(UTC) - timedelta(days=8)).isoformat(),
    )

    assert _fresh_cached_fallback_postings(
        {CACHE_CONFIG_KEY: {"1": cached}}
    ) == []


def test_unrelated_incomplete_fallback_is_marked_skipped_not_verified() -> None:
    cached = CachedSourcePosting(
        posting=JobPosting(
            company_key="example",
            company_name="Example",
            source_type="eightfold",
            source_url="https://example.com/job/2",
            title="Retail Sales Manager",
            location="Remote",
            description=None,
            source_job_id="2",
        ),
        listing_fingerprint="fingerprint",
        detail_verified_at=datetime.now(UTC).isoformat(),
    )
    result = _fresh_cached_fallback_postings(
        {
            CACHE_CONFIG_KEY: {"2": cached},
            DETAIL_PLANNER_CONFIG_KEY: lambda _title, _location: (
                DetailRetrievalDecision(False, "Clearly unrelated title.")
            ),
        }
    )

    assert result[0].normalization_state == "skipped_unrelated"
    assert result[0].detail_retrieval_state == "skipped_unrelated"


def test_fallback_detail_recovery_stops_after_three_failures(monkeypatch) -> None:
    calls = []

    def unavailable(posting, config):
        calls.append(posting.source_job_id)
        return JobPosting(
            **{**posting.__dict__, "detail_retrieval_state": "unavailable"}
        )

    monkeypatch.setattr(
        "job_radar.scan_service.enrich_cached_eightfold_posting",
        unavailable,
    )
    cache = {}
    for number in range(8):
        posting = JobPosting(
            company_key="example",
            company_name="Example",
            source_type="eightfold",
            source_url=f"https://example.com/job/{number}",
            title=f"Infrastructure Engineer {number}",
            location="Remote",
            description=None,
            source_job_id=str(number),
        )
        cache[str(number)] = CachedSourcePosting(
            posting=posting,
            listing_fingerprint=f"fingerprint-{number}",
            detail_verified_at=datetime.now(UTC).isoformat(),
        )

    result = _fresh_cached_fallback_postings(
        {
            "source_url": "https://example.com/careers",
            "domain": "example.com",
            "name": "Example",
            CACHE_CONFIG_KEY: cache,
            DETAIL_PLANNER_CONFIG_KEY: lambda _title, _location: (
                DetailRetrievalDecision(True, "Plausible title.")
            ),
        }
    )

    assert len(result) == 8
    assert calls == ["0", "1", "2"]
    assert all(posting.normalization_state == "incomplete" for posting in result)
