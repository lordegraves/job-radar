import pytest

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.registry import collect_jobs_for_company


def test_collect_jobs_for_company_rejects_unimplemented_source_type() -> None:
    company_config = {
        "company_key": "future_company",
        "name": "Future Company",
        "source_type": "workday",
        "source_url": "https://example.wd1.myworkdayjobs.com/External",
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