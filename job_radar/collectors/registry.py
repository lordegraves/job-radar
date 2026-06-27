from typing import Any

from job_radar.collectors.ashby import collect_ashby_jobs
from job_radar.collectors.greenhouse import CollectorError, collect_greenhouse_jobs
from job_radar.collectors.icims import collect_icims_jobs
from job_radar.collectors.jibe import collect_jibe_jobs
from job_radar.collectors.lever import collect_lever_jobs
from job_radar.collectors.usajobs import collect_usajobs
from job_radar.collectors.workday import collect_workday_jobs
from job_radar.models import JobPosting


def collect_jobs_for_company(company_config: dict[str, Any]) -> list[JobPosting]:
    source_type = company_config.get("source_type")

    if source_type == "greenhouse":
        return collect_greenhouse_jobs(company_config)

    if source_type == "lever":
        return collect_lever_jobs(company_config)

    if source_type == "ashby":
        return collect_ashby_jobs(company_config)

    if source_type == "workday":
        return collect_workday_jobs(company_config)

    if source_type == "usajobs":
        return collect_usajobs(company_config)

    if source_type == "icims":
        return collect_icims_jobs(company_config)

    if source_type == "jibe":
        return collect_jibe_jobs(company_config)

    raise CollectorError(
        f"No collector implemented for source_type={source_type} "
        f"company={company_config.get('company_key')}"
    )