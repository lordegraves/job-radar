"""Collect and normalize jobs from Rippling applicant-tracking pages."""

import json
import re
from html import unescape
from typing import Any

from job_radar.collectors.collector_http import get_response
from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.pagination import get_max_pages
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


RIPPLING_BASE_URL = "https://ats.rippling.com"
DEFAULT_MAX_PAGES = 25
NEXT_DATA_PATTERN = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)


def build_rippling_jobs_url(board_slug: str, page: int = 0) -> str:
    return f"{RIPPLING_BASE_URL}/{board_slug}/jobs?page={page}"


def extract_rippling_next_data(html: str) -> dict[str, Any]:
    match = NEXT_DATA_PATTERN.search(html)

    if not match:
        raise CollectorError("Rippling page does not contain __NEXT_DATA__ JSON")

    try:
        payload = json.loads(unescape(match.group(1)))
    except json.JSONDecodeError as error:
        raise CollectorError(f"Failed to parse Rippling __NEXT_DATA__ JSON: {error}") from error

    if not isinstance(payload, dict):
        raise CollectorError("Rippling __NEXT_DATA__ JSON must be an object")

    return payload


def _get_dehydrated_queries(payload: dict[str, Any]) -> list[Any]:
    queries = (
        payload.get("props", {})
        .get("pageProps", {})
        .get("dehydratedState", {})
        .get("queries")
    )

    if not isinstance(queries, list):
        raise CollectorError("Rippling payload does not contain dehydrated queries")

    return queries


def _get_job_posts_state_data(payload: dict[str, Any]) -> dict[str, Any]:
    for query in _get_dehydrated_queries(payload):
        if not isinstance(query, dict):
            continue

        query_key = query.get("queryKey")

        if (
            not isinstance(query_key, list)
            or len(query_key) < 3
            or query_key[2] != "job-posts"
        ):
            continue

        state_data = query.get("state", {}).get("data")

        if not isinstance(state_data, dict):
            continue

        items = state_data.get("items")

        if not isinstance(items, list):
            continue

        return state_data

    raise CollectorError("Rippling payload does not contain job-posts items")


def get_rippling_total_pages(payload: dict[str, Any]) -> int:
    state_data = _get_job_posts_state_data(payload)
    total_pages = state_data.get("totalPages")

    if isinstance(total_pages, int) and total_pages > 0:
        return total_pages

    return 1


def _get_department_name(raw_job: dict[str, Any]) -> str | None:
    department = raw_job.get("department")

    if not isinstance(department, dict):
        return None

    name = department.get("name")

    if not name:
        return None

    return str(name)


def _get_location_names(raw_job: dict[str, Any]) -> list[str]:
    locations = raw_job.get("locations")

    if not isinstance(locations, list):
        return []

    location_names: list[str] = []

    for location in locations:
        if not isinstance(location, dict):
            continue

        name = location.get("name")

        if not name:
            continue

        location_name = str(name)

        if location_name not in location_names:
            location_names.append(location_name)

    return location_names


def _format_location(raw_job: dict[str, Any]) -> str | None:
    location_names = _get_location_names(raw_job)

    if not location_names:
        return None

    return "; ".join(location_names)


def _format_description(raw_job: dict[str, Any]) -> str | None:
    department_name = _get_department_name(raw_job)

    if not department_name:
        return None

    return f"Department: {department_name}"


def _merge_location_text(existing_location: str | None, new_location: str | None) -> str | None:
    location_names: list[str] = []

    for location_text in [existing_location, new_location]:
        if not location_text:
            continue

        for location_name in location_text.split(";"):
            cleaned_location_name = location_name.strip()

            if cleaned_location_name and cleaned_location_name not in location_names:
                location_names.append(cleaned_location_name)

    if not location_names:
        return None

    return "; ".join(location_names)


def _merge_postings(existing: JobPosting, new_posting: JobPosting) -> JobPosting:
    merged_location = _merge_location_text(existing.location, new_posting.location)
    description = existing.description or new_posting.description

    canonical_key = make_canonical_key(
        company_key=existing.company_key,
        title=existing.title,
        location=merged_location,
    )

    content_hash = make_content_hash(
        title=existing.title,
        location=merged_location,
        description=description,
    )

    return JobPosting(
        company_key=existing.company_key,
        company_name=existing.company_name,
        source_type=existing.source_type,
        source_job_id=existing.source_job_id,
        source_url=existing.source_url,
        title=existing.title,
        location=merged_location,
        description=description,
        canonical_key=canonical_key,
        content_hash=content_hash,
    )


def parse_rippling_jobs(
    company_config: dict[str, Any],
    payload: dict[str, Any],
) -> list[JobPosting]:
    company_key = str(company_config["company_key"])
    company_name = str(company_config["name"])
    source_type = str(company_config["source_type"])

    state_data = _get_job_posts_state_data(payload)
    raw_jobs = state_data["items"]

    postings_by_id: dict[str, JobPosting] = {}

    for raw_job in raw_jobs:
        if not isinstance(raw_job, dict):
            continue

        title = raw_job.get("name")
        source_url = raw_job.get("url")
        source_job_id = raw_job.get("id")

        if not title or not source_url:
            continue

        location = _format_location(raw_job)
        description = _format_description(raw_job)

        canonical_key = make_canonical_key(
            company_key=company_key,
            title=str(title),
            location=location,
        )

        content_hash = make_content_hash(
            title=str(title),
            location=location,
            description=description,
        )

        posting = JobPosting(
            company_key=company_key,
            company_name=company_name,
            source_type=source_type,
            source_job_id=str(source_job_id) if source_job_id else None,
            source_url=str(source_url),
            title=str(title),
            location=location,
            description=description,
            canonical_key=canonical_key,
            content_hash=content_hash,
        )

        dedupe_key = posting.source_job_id or posting.source_url

        if dedupe_key in postings_by_id:
            postings_by_id[dedupe_key] = _merge_postings(
                postings_by_id[dedupe_key],
                posting,
            )
        else:
            postings_by_id[dedupe_key] = posting

    return list(postings_by_id.values())


def _fetch_rippling_payload(url: str) -> dict[str, Any]:
    response = get_response(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 JobRadar/1.0",
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "application/json;q=0.8,*/*;q=0.7"
            ),
        },
        timeout=30,
        error_type=CollectorError,
        request_error_message="Failed to fetch Rippling jobs",
    )

    return extract_rippling_next_data(response.text)


def collect_rippling_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    board_slug = company_config.get("source_slug")

    if not board_slug:
        raise CollectorError(
            f"Rippling company {company_config.get('company_key')} is missing source_slug"
        )

    first_payload = _fetch_rippling_payload(
        build_rippling_jobs_url(str(board_slug), page=0)
    )
    reported_total_pages = get_rippling_total_pages(first_payload)
    max_pages = get_max_pages(
        company_config,
        default=DEFAULT_MAX_PAGES,
    )
    total_pages = min(reported_total_pages, max_pages)

    all_postings = parse_rippling_jobs(company_config, first_payload)

    for page in range(1, total_pages):
        payload = _fetch_rippling_payload(
            build_rippling_jobs_url(str(board_slug), page=page)
        )
        all_postings.extend(parse_rippling_jobs(company_config, payload))

    merged_postings: dict[str, JobPosting] = {}

    for posting in all_postings:
        dedupe_key = posting.source_job_id or posting.source_url

        if dedupe_key in merged_postings:
            merged_postings[dedupe_key] = _merge_postings(
                merged_postings[dedupe_key],
                posting,
            )
        else:
            merged_postings[dedupe_key] = posting

    return list(merged_postings.values())
