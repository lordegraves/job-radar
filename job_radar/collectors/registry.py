from typing import Any

from job_radar.collectors.ashby import collect_ashby_jobs
from job_radar.collectors.greenhouse import CollectorError, collect_greenhouse_jobs
from job_radar.collectors.html import collect_html_jobs
from job_radar.collectors.icims import collect_icims_jobs
from job_radar.collectors.jibe import collect_jibe_jobs
from job_radar.collectors.lever import collect_lever_jobs
from job_radar.collectors.usajobs import collect_usajobs
from job_radar.collectors.workday import collect_workday_jobs
from job_radar.collectors.jobsyn import collect_jobsyn_jobs
from job_radar.collectors.oracle_hcm import collect_oracle_hcm_jobs
from job_radar.collectors.smartrecruiters import collect_smartrecruiters_jobs
from job_radar.collectors.selectminds import collect_selectminds_jobs
from job_radar.collectors.phenom import collect_phenom_jobs
from job_radar.collectors.dayforce import collect_dayforce_jobs
from job_radar.collectors.adp import collect_adp_jobs
from job_radar.collectors.activate import collect_activate_jobs
from job_radar.collectors.weka import collect_weka_jobs
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

    if source_type == "html":
        return collect_html_jobs(company_config)
    
    if source_type == "jobsyn":
        return collect_jobsyn_jobs(company_config)
    
    if source_type == "oracle_hcm":
        return collect_oracle_hcm_jobs(company_config)
    
    if source_type == "smartrecruiters":
        return collect_smartrecruiters_jobs(company_config)
    
    if source_type == "selectminds":
        return collect_selectminds_jobs(company_config)
    
    if source_type == "phenom":
        return collect_phenom_jobs(company_config)

    if source_type == "dayforce":
        return collect_dayforce_jobs(company_config)
    
    if source_type == "adp":
        return collect_adp_jobs(company_config)

    if source_type == "activate":
        return collect_activate_jobs(company_config)

    if source_type == "weka":
        return collect_weka_jobs(company_config)

    raise CollectorError(
        f"No collector implemented for source_type={source_type} "
        f"company={company_config.get('company_key')}"
    )