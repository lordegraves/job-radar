from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import urlencode, urljoin

import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_PAGE_SIZE = 25
DEFAULT_MAX_PAGES = 25
DEFAULT_USER_AGENT = "JobRadar/0.1 local career-source scanner"


def _build_headers(referer_url: str) -> dict[str, str]:
    return {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": referer_url,
        "User-Agent": DEFAULT_USER_AGENT,
        "X-Requested-With": "XMLHttpRequest",
    }


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = " ".join(text.split())

    return text or None


def _slugify_title(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")

    return slug or "job"


def _get_timeout_seconds(company_config: dict[str, Any]) -> int:
    value = company_config.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)

    try:
        timeout = int(value)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS

    if timeout <= 0:
        return DEFAULT_TIMEOUT_SECONDS

    return timeout


def _get_page_size(company_config: dict[str, Any]) -> int:
    value = company_config.get("page_size", DEFAULT_PAGE_SIZE)

    try:
        page_size = int(value)
    except (TypeError, ValueError):
        return DEFAULT_PAGE_SIZE

    if page_size <= 0:
        return DEFAULT_PAGE_SIZE

    return page_size


def _get_max_pages(company_config: dict[str, Any]) -> int:
    value = company_config.get("max_pages", DEFAULT_MAX_PAGES)

    try:
        max_pages = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_PAGES

    if max_pages <= 0:
        return DEFAULT_MAX_PAGES

    return max_pages


def _build_job_url(base_url: str, title: str, source_job_id: str) -> str:
    slug = _slugify_title(title)
    return urljoin(base_url, f"/search/jobdetails/{slug}/{source_job_id}")


def _extract_title(record: dict[str, Any]) -> str | None:
    tracking_object = record.get("TrackingObject") or {}
    return _clean_text(tracking_object.get("TitleJson")) or _clean_text(record.get("Title"))


def _extract_reference_number(record: dict[str, Any]) -> str | None:
    tracking_object = record.get("TrackingObject") or {}

    return _clean_text(tracking_object.get("ReferenceNumberJson")) or _clean_text(
        record.get("ReferenceNumber")
    )


def _extract_location(record: dict[str, Any]) -> str | None:
    tracking_object = record.get("TrackingObject") or {}

    locations = tracking_object.get("LocationNamesJson")
    if isinstance(locations, list) and locations:
        return _clean_text(locations[0])

    abbreviated_locations = tracking_object.get("CityStatesDataAbbrevJson")
    if isinstance(abbreviated_locations, list) and abbreviated_locations:
        return _clean_text(abbreviated_locations[0])

    return _clean_text(record.get("CityStateDataAbbrev")) or _clean_text(
        record.get("LocationName")
    )


def _build_description(record: dict[str, Any]) -> str | None:
    tracking_object = record.get("TrackingObject") or {}

    parts = [
        _extract_reference_number(record),
        _clean_text(tracking_object.get("DepartmentNameJson"))
        or _clean_text(record.get("DepartmentName")),
        _clean_text(tracking_object.get("PostedDateJson"))
        or _clean_text(record.get("PostedDate")),
    ]

    categories = tracking_object.get("AtsCategoryNamesJson") or tracking_object.get(
        "ActivateCategoryNamesJson"
    )
    if isinstance(categories, list):
        parts.extend(_clean_text(category) for category in categories)

    cleaned_parts = [part for part in parts if part]
    if not cleaned_parts:
        return None

    return " | ".join(cleaned_parts)


def _fetch_page(
    company_config: dict[str, Any],
    start_index: int,
    page_size: int,
) -> dict[str, Any]:
    source_url = str(company_config["source_url"])
    referer_url = str(company_config.get("referer_url", source_url))

    params = {
        "jtStartIndex": start_index,
        "jtPageSize": page_size,
    }

    try:
        response = requests.get(
            source_url,
            params=params,
            headers=_build_headers(referer_url),
            timeout=_get_timeout_seconds(company_config),
        )
        response.raise_for_status()
    except requests.HTTPError as error:
        response_body = response.text[:500].replace("\n", " ")
        raise CollectorError(
            f"Failed to fetch Activate postings: {error}; "
            f"response_body={response_body}"
        ) from error
    except requests.RequestException as error:
        raise CollectorError(f"Failed to fetch Activate postings: {error}") from error

    try:
        data = response.json()
    except ValueError as error:
        response_body = response.text[:500].replace("\n", " ")
        raise CollectorError(
            f"Failed to parse Activate postings JSON: {error}; "
            f"response_body={response_body}"
        ) from error

    if not isinstance(data, dict):
        raise CollectorError("Activate postings response was not a JSON object")

    return data


def collect_activate_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    source_base_url = str(company_config["source_base_url"])
    page_size = _get_page_size(company_config)
    max_pages = _get_max_pages(company_config)

    postings: list[JobPosting] = []
    seen_ids: set[str] = set()

    for page_number in range(max_pages):
        start_index = page_number * page_size
        data = _fetch_page(
            company_config=company_config,
            start_index=start_index,
            page_size=page_size,
        )

        records = data.get("Records") or []
        if not isinstance(records, list) or not records:
            break

        for record in records:
            if not isinstance(record, dict):
                continue

            source_job_id = _clean_text(record.get("ID"))
            title = _extract_title(record)

            if not source_job_id or not title:
                continue

            if source_job_id in seen_ids:
                continue

            seen_ids.add(source_job_id)

            location = _extract_location(record)
            description = _build_description(record)
            source_url = _build_job_url(source_base_url, title, source_job_id)

            canonical_key = make_canonical_key(
                company_key=str(company_config["company_key"]),
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
                    company_key=str(company_config["company_key"]),
                    company_name=str(company_config["name"]),
                    source_type=str(company_config["source_type"]),
                    source_job_id=source_job_id,
                    source_url=source_url,
                    title=title,
                    location=location,
                    description=description,
                    canonical_key=canonical_key,
                    content_hash=content_hash,
                )
            )

        total_record_count = data.get("TotalRecordCount")
        if isinstance(total_record_count, int) and len(postings) >= total_record_count:
            break

        if len(records) < page_size:
            break

    return postings