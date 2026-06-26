from typing import Any

import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


ASHBY_BASE_URL = "https://api.ashbyhq.com/posting-api/job-board"


def build_ashby_jobs_url(source_slug: str) -> str:
    return f"{ASHBY_BASE_URL}/{source_slug}?includeCompensation=true"


def _get_job_id(job: dict[str, Any]) -> str | None:
    job_id = job.get("id")

    if job_id is None:
        return None

    return str(job_id)


def _get_title(job: dict[str, Any]) -> str | None:
    title = job.get("title")

    if not title:
        return None

    return str(title)


def _get_source_url(job: dict[str, Any]) -> str | None:
    for field_name in ["jobUrl", "applyUrl", "url"]:
        source_url = job.get(field_name)

        if source_url:
            return str(source_url)

    return None


def _get_location(job: dict[str, Any]) -> str | None:
    location_name = job.get("locationName")

    if location_name:
        return str(location_name)

    location = job.get("location")

    if isinstance(location, dict):
        name = location.get("name")

        if name:
            return str(name)

    if isinstance(location, str) and location:
        return location

    return None


def _get_description(job: dict[str, Any]) -> str | None:
    for field_name in ["descriptionPlain", "descriptionHtml", "description"]:
        description = job.get(field_name)

        if description:
            return str(description)

    return None


def _get_salary_text(job: dict[str, Any]) -> str | None:
    compensation = job.get("compensation")

    if not isinstance(compensation, dict):
        return None

    compensation_tier_summary = compensation.get("compensationTierSummary")

    if compensation_tier_summary:
        return str(compensation_tier_summary)

    summary_components = compensation.get("summaryComponents")

    if isinstance(summary_components, list) and summary_components:
        parts = [str(component) for component in summary_components if component]

        if parts:
            return ", ".join(parts)

    return None


def parse_ashby_jobs(
    company_config: dict[str, Any],
    payload: dict[str, Any],
) -> list[JobPosting]:
    company_key = str(company_config["company_key"])
    company_name = str(company_config["name"])
    source_type = str(company_config["source_type"])

    raw_jobs = payload.get("jobs")

    if not isinstance(raw_jobs, list):
        raise CollectorError("Ashby payload does not contain a jobs list")

    postings: list[JobPosting] = []

    for raw_job in raw_jobs:
        if not isinstance(raw_job, dict):
            continue

        title = _get_title(raw_job)
        source_url = _get_source_url(raw_job)

        if not title or not source_url:
            continue

        location = _get_location(raw_job)
        description = _get_description(raw_job)
        salary_text = _get_salary_text(raw_job)
        source_job_id = _get_job_id(raw_job)

        canonical_key = make_canonical_key(
            company_key=company_key,
            title=title,
            location=location,
        )

        content_hash = make_content_hash(
            title=title,
            location=location,
            description=description,
            salary_text=salary_text,
        )

        postings.append(
            JobPosting(
                company_key=company_key,
                company_name=company_name,
                source_type=source_type,
                source_job_id=source_job_id,
                source_url=source_url,
                title=title,
                location=location,
                description=description,
                salary_text=salary_text,
                canonical_key=canonical_key,
                content_hash=content_hash,
            )
        )

    return postings


def collect_ashby_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    source_slug = company_config.get("source_slug")

    if not source_slug:
        raise CollectorError(
            f"Ashby company {company_config.get('company_key')} is missing source_slug"
        )

    url = build_ashby_jobs_url(str(source_slug))

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as error:
        raise CollectorError(f"Failed to fetch Ashby jobs: {error}") from error

    payload = response.json()

    if not isinstance(payload, dict):
        raise CollectorError("Ashby response JSON must be an object")

    return parse_ashby_jobs(company_config, payload)