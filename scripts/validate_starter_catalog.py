"""Run a bounded live check of the starter catalog's custom collectors."""

from job_radar.collectors.registry import collect_jobs_for_company
from job_radar.starter_catalog_service import starter_catalog_entries


for entry in starter_catalog_entries():
    if entry["source_type"] == "greenhouse":
        continue
    config = {
        "company_key": entry["employer_id"],
        "name": entry["name"],
        "source_type": entry["source_type"],
        **entry["source_config"],
        "connection_test": True,
        "max_pages": 2,
    }
    if entry["source_type"] == "walmart":
        config.update(
            walmart_target_roles=["software engineer"],
            walmart_locations=["United States", "Remote"],
        )
    jobs = collect_jobs_for_company(config)
    print(
        entry["name"],
        len(jobs),
        len({job.source_job_id for job in jobs}),
        sum(bool((job.description or "").strip()) for job in jobs),
    )
