from typing import Any

import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


LEVER_BASE_URL = "https://api.lever.co/v0/postings"


def build_lever_jobs_url(source_slug: str) -> str:
    return f"{LEVER_BASE_URL}/{source_slug}?mode=json"


def _get_job_id(job: dict[str, Any]) -> str | None:
    job_id = job.get("id")

    if job_id is None:
        return None

    return str(job_id)


def _get_location(job: dict[str, Any]) -> str | None:
    categories = job.get("categories")

    if not isinstance(categories, dict):
        return None

    location = categories.get("location")

    if not location:
        return None

    return str(location)


def _get_salary_text(job: dict[str, Any]) -> str | None:
    salary_range = job.get("salaryRange")

    if not isinstance(salary_range, dict):
        return None

    min_salary = salary_range.get("min")
    max_salary = salary_range.get("max")
    currency = salary_range.get("currency")

    if min_salary is None and max_salary is None:
        return None

    parts = []

    if currency:
        parts.append(str(currency))

    if min_salary is not None and max_salary is not None:
        parts.append(f"{min_salary} - {max_salary}")
    elif min_salary is not None:
        parts.append(f"{min_salary}+")
    elif max_salary is not None:
        parts.append(f"up to {max_salary}")

    return " ".join(parts)


def _get_description(job: dict[str, Any]) -> str | None:
    description = job.get("descriptionPlain")

    if description:
        return str(description)

    description_html = job.get("description")

    if description_html:
        return str(description_html)

    return None


def parse_lever_jobs(
    company_config: dict[str, Any],
    payload: list[Any],
) -> list[JobPosting]:
    company_key = str(company_config["company_key"])
    company_name = str(company_config["name"])
    source_type = str(company_config["source_type"])

    if not isinstance(payload, list):
        raise CollectorError("Lever payload must be a list")

    postings: list[JobPosting] = []

    for raw_job in payload:
        if not isinstance(raw_job, dict):
            continue

        title = raw_job.get("text")
        source_url = raw_job.get("hostedUrl")

        if not title or not source_url:
            continue

        location = _get_location(raw_job)
        description = _get_description(raw_job)
        salary_text = _get_salary_text(raw_job)
        source_job_id = _get_job_id(raw_job)

        canonical_key = make_canonical_key(
            company_key=company_key,
            title=str(title),
            location=location,
        )

        content_hash = make_content_hash(
            title=str(title),
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
                source_url=str(source_url),
                title=str(title),
                location=location,
                description=description,
                salary_text=salary_text,
                canonical_key=canonical_key,
                content_hash=content_hash,
            )
        )

    return postings


def collect_lever_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    source_slug = company_config.get("source_slug")

    if not source_slug:
        raise CollectorError(
            f"Lever company {company_config.get('company_key')} is missing source_slug"
        )

    url = build_lever_jobs_url(str(source_slug))

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as error:
        raise CollectorError(f"Failed to fetch Lever jobs: {error}") from error

    payload = response.json()

    if not isinstance(payload, list):
        raise CollectorError("Lever response JSON must be a list")

    return parse_lever_jobs(company_config, payload)