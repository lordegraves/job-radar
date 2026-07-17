import re
from html import unescape
from typing import Any
from urllib.parse import urlencode

import requests

from job_radar.collectors.collector_http import get_response
from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


SCHOOLSPRING_API_BASE_URL = "https://api.schoolspring.com"


def build_schoolspring_jobs_url(
    domain_name: str,
    page: int = 1,
    page_size: int = 20,
) -> str:
    query = urlencode(
        {
            "domainName": domain_name,
            "keyword": "",
            "location": "",
            "category": "",
            "gradelevel": "",
            "jobtype": "",
            "organization": "",
            "swLat": "",
            "swLon": "",
            "neLat": "",
            "neLon": "",
            "page": page,
            "size": page_size,
            "sortDateAscending": "false",
        }
    )

    return f"{SCHOOLSPRING_API_BASE_URL}/api/Jobs/GetPagedJobsWithSearch?{query}"


def build_schoolspring_job_detail_url(job_id: str | int) -> str:
    return f"{SCHOOLSPRING_API_BASE_URL}/api/Jobs/{job_id}"


def _get_headers(domain_name: str) -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 JobRadar/1.0",
        "Accept": "application/json,text/plain,*/*",
        "Origin": f"https://{domain_name}",
        "Referer": f"https://{domain_name}/",
    }


def _load_json_response(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as error:
        raise CollectorError(f"SchoolSpring response is not valid JSON: {error}") from error

    if not isinstance(payload, dict):
        raise CollectorError("SchoolSpring response JSON must be an object")

    return payload


def _validate_success_payload(payload: dict[str, Any]) -> None:
    if payload.get("success") is not True:
        message = payload.get("message") or "unknown error"
        raise CollectorError(f"SchoolSpring API returned success=false: {message}")


def _get_jobs_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    _validate_success_payload(payload)

    value = payload.get("value")

    if not isinstance(value, dict):
        raise CollectorError("SchoolSpring jobs payload value must be an object")

    jobs_list = value.get("jobsList")

    if not isinstance(jobs_list, list):
        raise CollectorError("SchoolSpring jobs payload does not contain jobsList")

    return [job for job in jobs_list if isinstance(job, dict)]


def _get_detail_value(detail_payload: dict[str, Any] | None) -> dict[str, Any]:
    if detail_payload is None:
        return {}

    _validate_success_payload(detail_payload)

    value = detail_payload.get("value")

    if not isinstance(value, dict):
        return {}

    return value


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = unescape(str(value))
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return None

    return text


def _get_detail_job_info(detail_payload: dict[str, Any] | None) -> dict[str, Any]:
    detail_value = _get_detail_value(detail_payload)
    job_info = detail_value.get("jobInfo")

    if not isinstance(job_info, dict):
        return {}

    return job_info


def _get_detail_location(detail_payload: dict[str, Any] | None) -> str | None:
    detail_value = _get_detail_value(detail_payload)
    job_locations = detail_value.get("jobLocations")

    if not isinstance(job_locations, list):
        return None

    location_names: list[str] = []

    for location in job_locations:
        if not isinstance(location, dict):
            continue

        location_name = _clean_text(location.get("displayLocation"))

        if location_name and location_name not in location_names:
            location_names.append(location_name)

    if not location_names:
        return None

    return "; ".join(location_names)


def _get_detail_categories(detail_payload: dict[str, Any] | None) -> list[str]:
    detail_value = _get_detail_value(detail_payload)
    job_categories = detail_value.get("jobCategories")

    if not isinstance(job_categories, list):
        return []

    category_labels: list[str] = []

    for category in job_categories:
        if not isinstance(category, dict):
            continue

        category_name = _clean_text(category.get("category"))
        subcategory_name = _clean_text(category.get("subCategory"))

        if category_name and subcategory_name:
            label = f"{category_name}: {subcategory_name}"
        else:
            label = category_name or subcategory_name

        if label and label not in category_labels:
            category_labels.append(label)

    return category_labels


def _format_description(
    raw_job: dict[str, Any],
    detail_payload: dict[str, Any] | None,
) -> str | None:
    job_info = _get_detail_job_info(detail_payload)

    description_parts: list[str] = []

    job_description = _clean_text(job_info.get("jobDescription"))

    if job_description:
        description_parts.append(job_description)

    employer = _clean_text(raw_job.get("employer"))

    if employer:
        description_parts.append(f"Employer: {employer}")

    deadline = _clean_text(job_info.get("applicationDeadline"))

    if deadline:
        description_parts.append(f"Application deadline: {deadline}")

    categories = _get_detail_categories(detail_payload)

    if categories:
        description_parts.append(f"Categories: {'; '.join(categories)}")

    if not description_parts:
        return None

    return "\n\n".join(description_parts)


def parse_schoolspring_jobs(
    company_config: dict[str, Any],
    payload: dict[str, Any],
    detail_payloads: dict[str, dict[str, Any]] | None = None,
) -> list[JobPosting]:
    company_key = str(company_config["company_key"])
    company_name = str(company_config["name"])
    source_type = str(company_config["source_type"])
    domain_name = str(company_config.get("domain_name") or company_config.get("source_slug"))

    raw_jobs = _get_jobs_list(payload)
    postings: list[JobPosting] = []

    for raw_job in raw_jobs:
        source_job_id = raw_job.get("jobId")
        title = _clean_text(raw_job.get("title"))

        if source_job_id is None or not title:
            continue

        source_job_id_text = str(source_job_id)
        detail_payload = detail_payloads.get(source_job_id_text) if detail_payloads else None
        job_info = _get_detail_job_info(detail_payload)

        source_url = _clean_text(job_info.get("infoURL"))

        if not source_url:
            source_url = f"https://{domain_name}/?jobId={source_job_id_text}"

        location = _get_detail_location(detail_payload) or _clean_text(raw_job.get("location"))
        description = _format_description(raw_job, detail_payload)

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
                source_job_id=source_job_id_text,
                source_url=source_url,
                title=title,
                location=location,
                description=description,
                canonical_key=canonical_key,
                content_hash=content_hash,
            )
        )

    return postings


def _fetch_schoolspring_payload(url: str, domain_name: str) -> dict[str, Any]:
    response = get_response(
        url,
        headers=_get_headers(domain_name),
        timeout=30,
        error_type=CollectorError,
        request_error_message="Failed to fetch SchoolSpring jobs",
    )

    return _load_json_response(response)


def collect_schoolspring_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    domain_name = company_config.get("domain_name") or company_config.get("source_slug")

    if not domain_name:
        raise CollectorError(
            f"SchoolSpring company {company_config.get('company_key')} is missing domain_name"
        )

    page_size = int(company_config.get("page_size", 20))
    max_pages = int(company_config.get("max_pages", 25))

    all_postings: list[JobPosting] = []

    for page in range(1, max_pages + 1):
        list_url = build_schoolspring_jobs_url(
            domain_name=str(domain_name),
            page=page,
            page_size=page_size,
        )

        list_payload = _fetch_schoolspring_payload(list_url, str(domain_name))
        raw_jobs = _get_jobs_list(list_payload)

        if not raw_jobs:
            break

        detail_payloads: dict[str, dict[str, Any]] = {}

        for raw_job in raw_jobs:
            source_job_id = raw_job.get("jobId")

            if source_job_id is None:
                continue

            source_job_id_text = str(source_job_id)
            detail_url = build_schoolspring_job_detail_url(source_job_id_text)

            try:
                detail_payloads[source_job_id_text] = _fetch_schoolspring_payload(
                    detail_url,
                    str(domain_name),
                )
            except CollectorError:
                continue

        all_postings.extend(
            parse_schoolspring_jobs(
                company_config,
                list_payload,
                detail_payloads=detail_payloads,
            )
        )

        if len(raw_jobs) < page_size:
            break

    return all_postings