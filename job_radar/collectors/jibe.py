from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_USER_AGENT = "JobRadar/0.1 local career-source scanner"
DEFAULT_PAGE_SIZE = 100
MAX_PAGES = 5


def _build_headers(company_config: dict[str, Any]) -> dict[str, str]:
    referer = str(company_config.get("referer_url") or "")

    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": DEFAULT_USER_AGENT,
    }

    if referer:
        headers["Referer"] = referer

    return headers


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _get_job_data(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    data = item.get("data")
    if isinstance(data, dict):
        return data

    return item


def _get_location(data: dict[str, Any]) -> str | None:
    for key in ("full_location", "short_location", "location_name"):
        value = _as_text(data.get(key)).strip()
        if value:
            return value

    parts = []
    for key in ("city", "state", "country"):
        value = _as_text(data.get(key)).strip()
        if value:
            parts.append(value)

    if parts:
        return ", ".join(parts)

    return None


def _get_description(data: dict[str, Any]) -> str:
    parts = []

    for key in ("description", "responsibilities", "qualifications"):
        value = _as_text(data.get(key)).strip()
        if value:
            parts.append(value)

    return "\n\n".join(parts)


def _get_salary_text(data: dict[str, Any]) -> str | None:
    salary_values = []

    for key in ("tags2", "tags3", "tags5", "tags6"):
        value = data.get(key)
        if not isinstance(value, list):
            continue

        for item in value:
            text = _as_text(item).strip()
            if text and text not in salary_values:
                salary_values.append(text)

    if not salary_values:
        return None

    return " | ".join(salary_values)


def _build_source_url(company_config: dict[str, Any], data: dict[str, Any]) -> str:
    job_url_template = company_config.get("job_url_template")
    slug = _as_text(data.get("slug") or data.get("req_id")).strip()

    if job_url_template and slug:
        return str(job_url_template).format(slug=slug)

    apply_url = _as_text(data.get("apply_url")).strip()
    if apply_url:
        return apply_url

    source_url = str(company_config["source_url"])
    return urljoin(source_url.rstrip("/") + "/", slug)


def _parse_jibe_payload(
    company_config: dict[str, Any],
    payload: dict[str, Any],
) -> list[JobPosting]:
    items = payload.get("jobs", [])
    if not isinstance(items, list):
        raise CollectorError("Jibe response jobs field is not a list")

    postings: list[JobPosting] = []

    for item in items:
        data = _get_job_data(item)
        if data is None:
            continue

        title = _as_text(data.get("title")).strip()
        source_job_id = _as_text(data.get("req_id") or data.get("slug")).strip()
        source_url = _build_source_url(company_config, data)
        location = _get_location(data)
        description = _get_description(data)
        salary_text = _get_salary_text(data)

        if not title or not source_job_id or not source_url:
            continue

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
                salary_text=salary_text,
                canonical_key=canonical_key,
                content_hash=content_hash,
            )
        )

    return postings


def _get_positive_int_config(
    company_config: dict[str, Any],
    key: str,
    default: int,
) -> int:
    value = company_config.get(key, default)

    if isinstance(value, bool):
        return default

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    if parsed < 1:
        return default

    return parsed


def _fetch_jibe_page(
    company_config: dict[str, Any],
    page: int,
    limit: int,
) -> dict[str, Any]:
    source_url = str(company_config["source_url"])

    try:
        response = requests.get(
            source_url,
            params={
                "page": page,
                "limit": limit,
            },
            headers=_build_headers(company_config),
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.HTTPError as error:
        response_body = response.text[:500].replace("\n", " ")
        raise CollectorError(
            f"Failed to fetch Jibe postings: {error}; "
            f"response_body={response_body}"
        ) from error
    except requests.RequestException as error:
        raise CollectorError(f"Failed to fetch Jibe postings: {error}") from error

    payload = response.json()
    if not isinstance(payload, dict):
        raise CollectorError("Jibe response is not a JSON object")

    return payload


def collect_jibe_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    page_size = _get_positive_int_config(
        company_config=company_config,
        key="page_size",
        default=DEFAULT_PAGE_SIZE,
    )
    max_pages = _get_positive_int_config(
        company_config=company_config,
        key="max_pages",
        default=MAX_PAGES,
    )

    postings: list[JobPosting] = []
    seen_urls: set[str] = set()

    for page in range(1, max_pages + 1):
        payload = _fetch_jibe_page(
            company_config=company_config,
            page=page,
            limit=page_size,
        )

        page_postings = _parse_jibe_payload(company_config, payload)
        if not page_postings:
            break

        added_count = 0
        for posting in page_postings:
            if posting.source_url in seen_urls:
                continue

            seen_urls.add(posting.source_url)
            postings.append(posting)
            added_count += 1

        if added_count == 0:
            break

        total_count = payload.get("totalCount") or payload.get("count")
        if isinstance(total_count, int) and len(postings) >= total_count:
            break

    return postings