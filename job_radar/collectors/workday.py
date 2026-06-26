from typing import Any

import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


DEFAULT_WORKDAY_LIMIT = 20


WORKDAY_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "job-radar/0.1",
}


def _build_workday_payload(offset: int, limit: int) -> dict[str, Any]:
    return {
        "appliedFacets": {},
        "limit": limit,
        "offset": offset,
        "searchText": "",
    }


def _get_job_id(job: dict[str, Any]) -> str | None:
    for field_name in ["bulletFields", "jobReqId", "id"]:
        value = job.get(field_name)

        if isinstance(value, list) and value:
            return str(value[0])

        if value:
            return str(value)

    return None


def _get_title(job: dict[str, Any]) -> str | None:
    title = job.get("title")

    if not title:
        return None

    return str(title)


def _get_location(job: dict[str, Any]) -> str | None:
    locations_text = job.get("locationsText")

    if locations_text:
        return str(locations_text)

    locations = job.get("locations")

    if isinstance(locations, list) and locations:
        names = []

        for location in locations:
            if isinstance(location, dict):
                name = location.get("name")

                if name:
                    names.append(str(name))
            elif location:
                names.append(str(location))

        if names:
            return ", ".join(names)

    return None


def _get_description(job: dict[str, Any]) -> str | None:
    for field_name in ["description", "jobDescription", "summary"]:
        description = job.get(field_name)

        if description:
            return str(description)

    return None


def _get_source_url(
    company_config: dict[str, Any],
    job: dict[str, Any],
) -> str | None:
    for field_name in ["externalUrl", "url"]:
        source_url = job.get(field_name)

        if source_url:
            return str(source_url)

    external_path = job.get("externalPath")
    source_base_url = company_config.get("source_base_url")

    if external_path and source_base_url:
        return str(source_base_url).rstrip("/") + "/" + str(external_path).lstrip("/")

    return None


def parse_workday_jobs(
    company_config: dict[str, Any],
    payload: dict[str, Any],
) -> list[JobPosting]:
    company_key = str(company_config["company_key"])
    company_name = str(company_config["name"])
    source_type = str(company_config["source_type"])

    raw_jobs = payload.get("jobPostings")

    if not isinstance(raw_jobs, list):
        raise CollectorError("Workday payload does not contain a jobPostings list")

    postings: list[JobPosting] = []

    for raw_job in raw_jobs:
        if not isinstance(raw_job, dict):
            continue

        title = _get_title(raw_job)
        source_url = _get_source_url(company_config, raw_job)

        if not title or not source_url:
            continue

        location = _get_location(raw_job)
        description = _get_description(raw_job)
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
                canonical_key=canonical_key,
                content_hash=content_hash,
            )
        )

    return postings


def collect_workday_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    source_url = company_config.get("source_url")

    if not source_url:
        raise CollectorError(
            f"Workday company {company_config.get('company_key')} is missing source_url"
        )

    limit = int(company_config.get("page_size", DEFAULT_WORKDAY_LIMIT))
    offset = 0
    postings: list[JobPosting] = []

    while True:
        payload = _build_workday_payload(offset=offset, limit=limit)

        try:
            response = requests.post(
                str(source_url),
                json=payload,
                headers=WORKDAY_HEADERS,
                timeout=30,
            )
            response.raise_for_status()
        except requests.HTTPError as error:
            response_body = response.text[:500].replace("\n", " ")
            raise CollectorError(
                f"Failed to fetch Workday jobs: {error}; "
                f"response_body={response_body}"
            ) from error
        except requests.RequestException as error:
            raise CollectorError(f"Failed to fetch Workday jobs: {error}") from error

        response_payload = response.json()

        if not isinstance(response_payload, dict):
            raise CollectorError("Workday response JSON must be an object")

        page_postings = parse_workday_jobs(company_config, response_payload)
        postings.extend(page_postings)

        total = response_payload.get("total")
        raw_jobs = response_payload.get("jobPostings")

        if not isinstance(raw_jobs, list):
            raise CollectorError("Workday payload does not contain a jobPostings list")

        offset += limit

        if not raw_jobs:
            break

        if isinstance(total, int) and offset >= total:
            break

        if len(raw_jobs) < limit:
            break

    return postings