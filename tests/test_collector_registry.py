"""Tests that each company source type is routed to the correct collector."""

from datetime import UTC, datetime

import pytest

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.incremental_cache import (
    CACHE_CONFIG_KEY,
    DETAIL_PLANNER_CONFIG_KEY,
)
from job_radar.detail_retrieval import DetailRetrievalDecision
from job_radar.collectors.registry import (
    _recent_cached_detail,
    collect_jobs_for_company,
)
from job_radar.models import JobPosting
from job_radar.storage import CachedSourcePosting


def test_collect_jobs_for_company_rejects_unimplemented_source_type() -> None:
    company_config = {
        "company_key": "future_company",
        "name": "Future Company",
        "source_type": "future_source",
        "source_url": "https://example.com/careers",
        "enabled": True,
    }

    with pytest.raises(CollectorError, match="No collector implemented"):
        collect_jobs_for_company(company_config)


def test_collect_jobs_for_company_rejects_missing_source_type() -> None:
    company_config = {
        "company_key": "missing_source",
        "name": "Missing Source",
        "enabled": True,
    }

    with pytest.raises(CollectorError, match="No collector implemented"):
        collect_jobs_for_company(company_config)


def test_authoritative_empty_greenhouse_board_does_not_raise_warning(monkeypatch) -> None:
    monkeypatch.setattr(
        "job_radar.collectors.registry.collect_greenhouse_jobs",
        lambda config: [],
    )
    config = {
        "company_key": "synthetic",
        "name": "Synthetic",
        "source_type": "greenhouse",
        "source_slug": "synthetic",
    }

    assert collect_jobs_for_company(config) == []
    assert "_source_collection_warnings" not in config


def test_empty_icims_source_explains_unavailable_listing_index(monkeypatch) -> None:
    monkeypatch.setattr(
        "job_radar.collectors.registry.collect_icims_jobs",
        lambda config: [],
    )
    config = {
        "company_key": "synthetic",
        "name": "Synthetic",
        "source_type": "icims",
        "source_url": "https://example.com/jobs",
    }

    assert collect_jobs_for_company(config) == []
    assert "public listing index may be unavailable" in config[
        "_source_collection_warnings"
    ][0]


def test_authoritative_empty_icims_board_does_not_raise_warning(monkeypatch) -> None:
    def collect_empty(config):
        config["_icims_authoritative_empty_result"] = True
        return []

    monkeypatch.setattr(
        "job_radar.collectors.registry.collect_icims_jobs",
        collect_empty,
    )
    config = {
        "company_key": "synthetic",
        "name": "Synthetic",
        "source_type": "icims",
        "source_url": "https://example.com/jobs",
    }

    assert collect_jobs_for_company(config) == []
    assert "_source_collection_warnings" not in config


def test_collect_jobs_for_company_routes_ukg(monkeypatch) -> None:
    expected = [
        JobPosting(
            company_key="synthetic",
            company_name="Synthetic",
            source_type="ukg",
            source_url="https://example.com/job/1",
            source_job_id="1",
            title="Infrastructure Engineer",
            location="Remote",
            remote_status="Hybrid",
            description="Build and operate reliable infrastructure. " * 10,
        )
    ]
    monkeypatch.setattr(
        "job_radar.collectors.registry.collect_ukg_jobs",
        lambda config: expected,
    )

    result = collect_jobs_for_company(
        {
            "company_key": "synthetic",
            "name": "Synthetic",
            "source_type": "ukg",
            "source_url": (
                "https://recruiting.ultipro.com/TENANT/JobBoard/board/"
            ),
        }
    )

    assert len(result) == 1
    assert result[0].remote_status == "Hybrid"
    assert result[0].normalization_state == "complete"


def test_collect_jobs_for_company_warns_when_description_is_incomplete(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "job_radar.collectors.registry.collect_ukg_jobs",
        lambda config: [
            JobPosting(
                company_key="synthetic",
                company_name="Synthetic",
                source_type="ukg",
                source_url="https://example.com/job/1",
                source_job_id="1",
                title="Infrastructure Engineer",
                location="Remote",
                description="Short listing teaser",
            )
        ],
    )
    config = {
        "company_key": "synthetic",
        "name": "Synthetic",
        "source_type": "ukg",
        "source_url": "https://example.com/jobs",
    }

    result = collect_jobs_for_company(config)

    assert result[0].normalization_state == "incomplete"
    assert result[0].normalization_issues == ("incomplete_description",)
    warning = config["_source_collection_warnings"][0]
    assert "selected for description retrieval" in warning
    assert "plausible" not in warning


def test_clearly_unrelated_incomplete_listing_does_not_raise_source_warning(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "job_radar.collectors.registry.collect_ukg_jobs",
        lambda config: [
            JobPosting(
                company_key="synthetic",
                company_name="Synthetic",
                source_type="ukg",
                source_url="https://example.com/job/1",
                source_job_id="1",
                title="Manufacturing Operator",
                location="Canada",
                description="Short listing teaser",
            )
        ],
    )
    config = {
        "company_key": "synthetic",
        "name": "Synthetic",
        "source_type": "ukg",
        "source_url": "https://example.com/jobs",
        DETAIL_PLANNER_CONFIG_KEY: lambda _title, _location: DetailRetrievalDecision(
            False,
            "The title is clearly unrelated to the selected target work.",
        ),
    }

    result = collect_jobs_for_company(config)

    assert result[0].normalization_state == "skipped_unrelated"
    assert result[0].detail_retrieval_state == "skipped_unrelated"
    assert "_source_collection_warnings" not in config


def test_oracle_hcm_plausible_incomplete_listing_uses_detail_page(monkeypatch) -> None:
    summary = JobPosting(
        company_key="synthetic",
        company_name="Synthetic",
        source_type="oracle_hcm",
        source_url="https://example.com/job/1",
        source_job_id="1",
        title="Linux Infrastructure Engineer",
        location="Remote",
        description="Short listing teaser",
    )
    monkeypatch.setattr(
        "job_radar.collectors.registry.collect_oracle_hcm_jobs",
        lambda config: [summary],
    )
    monkeypatch.setattr(
        "job_radar.collectors.registry.enrich_from_public_detail_page",
        lambda posting, *, source_api_url=None: JobPosting(
            **{
                **posting.__dict__,
                "description": "Operate reliable Linux infrastructure. " * 10,
                "detail_retrieval_state": None,
            }
        ),
    )

    result = collect_jobs_for_company(
        {
            "company_key": "synthetic",
            "name": "Synthetic",
            "source_type": "oracle_hcm",
            "source_url": "https://example.com/jobs",
        }
    )

    assert result[0].normalization_state == "complete"


def test_recent_cached_detail_reuses_unchanged_complete_description() -> None:
    summary = JobPosting(
        company_key="synthetic",
        company_name="Synthetic",
        source_type="icims",
        source_url="https://example.com/job/1",
        source_job_id="1",
        title="Infrastructure Engineer",
        location=None,
        description=None,
    )
    cached = CachedSourcePosting(
        posting=JobPosting(
            **{
                **summary.__dict__,
                "location": "Denver, CO",
                "description": "Operate reliable Linux infrastructure. " * 10,
            }
        ),
        listing_fingerprint="fingerprint",
        detail_verified_at=datetime.now(UTC).isoformat(),
    )

    result = _recent_cached_detail(
        summary,
        {CACHE_CONFIG_KEY: {"1": cached}},
    )

    assert result is not None
    assert result.location == "Denver, CO"
    assert result.detail_retrieval_state == "cached_detail_reuse"
