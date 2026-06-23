from typing import Any

import requests

from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


GREENHOUSE_BASE_URL = "https://boards-api.greenhouse.io/v1/boards"


class CollectorError(Exception):
    """Raised when a collector cannot fetch or parse jobs."""


def build_greenhouse_jobs_url(board_token: str) -> str:
    return f"{GREENHOUSE_BASE_URL}/{board_token}/jobs?content=true"


def _get_location_name(job: dict[str, Any]) -> str | None:
    location = job.get("location")

    if not isinstance(location, dict):
        return None

    name = location.get("name")

    if not name:
        return None

    return str(name)


def _get_job_id(job: dict[str, Any]) -> str | None:
    job_id = job.get("id")

    if job_id is None:
        return None

    return str(job_id)


def parse_greenhouse_jobs(
    company_config: dict[str, Any],
    payload: dict[str, Any],
) -> list[JobPosting]:
    company_key = str(company_config["company_key"])
    company_name = str(company_config["name"])
    source_type = str(company_config["source_type"])

    raw_jobs = payload.get("jobs")

    if not isinstance(raw_jobs, list):
        raise CollectorError("Greenhouse payload does not contain a jobs list")

    postings: list[JobPosting] = []

    for raw_job in raw_jobs:
        if not isinstance(raw_job, dict):
            continue

        title = raw_job.get("title")
        source_url = raw_job.get("absolute_url")

        if not title or not source_url:
            continue

        location = _get_location_name(raw_job)
        description = raw_job.get("content")
        source_job_id = _get_job_id(raw_job)

        canonical_key = make_canonical_key(
            company_key=company_key,
            title=str(title),
            location=location,
        )

        content_hash = make_content_hash(
            title=str(title),
            location=location,
            description=str(description) if description is not None else None,
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
                description=str(description) if description is not None else None,
                canonical_key=canonical_key,
                content_hash=content_hash,
            )
        )

    return postings


def collect_greenhouse_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    board_token = company_config.get("source_slug")

    if not board_token:
        raise CollectorError(
            f"Greenhouse company {company_config.get('company_key')} is missing source_slug"
        )

    url = build_greenhouse_jobs_url(str(board_token))

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as error:
        raise CollectorError(f"Failed to fetch Greenhouse jobs: {error}") from error

    payload = response.json()

    if not isinstance(payload, dict):
        raise CollectorError("Greenhouse response JSON must be an object")

    return parse_greenhouse_jobs(company_config, payload)