import pytest

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.registry import collect_jobs_for_company


def test_collect_jobs_for_company_rejects_unimplemented_source_type() -> None:
    company_config = {
        "company_key": "research_labs",
        "name": "Research Labs",
        "source_type": "lever",
        "source_slug": "researchlabs",
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