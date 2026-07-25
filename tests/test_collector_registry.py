"""Tests that each company source type is routed to the correct collector."""

import pytest

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.registry import collect_jobs_for_company


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


def test_collect_jobs_for_company_routes_ukg(monkeypatch) -> None:
    expected = [object()]
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

    assert result is expected
