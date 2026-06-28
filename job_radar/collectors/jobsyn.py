from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_PAGE_SIZE = 40
DEFAULT_MAX_PAGES = 5


def collect_jobsyn_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    source_url = company_config["source_url"]
    page_size = int(company_config.get("page_size", DEFAULT_PAGE_SIZE))
    max_pages = int(company_config.get("max_pages", DEFAULT_MAX_PAGES))

    postings: list[JobPosting] = []
    seen_keys: set[str] = set()

    for page in range(1, max_pages + 1):
        payload = _fetch_jobsyn_page(company_config, source_url, page, page_size)

        raw_jobs = []
        raw_jobs.extend(payload.get("featured_jobs") or [])
        raw_jobs.extend(payload.get("jobs") or [])

        for raw_job in raw_jobs:
            posting = _build_posting(company_config, raw_job)
            if posting is None:
                continue

            dedupe_key = posting.source_job_id or posting.source_url
            if dedupe_key in seen_keys:
                continue

            seen_keys.add(dedupe_key)
            postings.append(posting)

        pagination = payload.get("pagination") or {}
        has_more_pages = bool(pagination.get("has_more_pages"))
        total_pages = pagination.get("total_pages")

        if not has_more_pages:
            break

        if isinstance(total_pages, int) and page >= total_pages:
            break

    return postings


def _fetch_jobsyn_page(
    company_config: dict[str, Any],
    source_url: str,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    params = {
        "page": page,
        "num_items": page_size,
    }

    headers = {
        "User-Agent": "JobRadar/0.1 local career-source scanner",
        "Accept": "application/json, text/plain, */*",
        "X-Origin": company_config.get("x_origin", ""),
    }

    referer_url = company_config.get("referer_url")
    if referer_url:
        headers["Referer"] = referer_url

    origin_url = company_config.get("origin_url")
    if origin_url:
        headers["Origin"] = origin_url

    try:
        response = requests.get(
            source_url,
            params=params,
            headers=headers,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as error:
        raise CollectorError(f"Jobsyn request failed for {source_url}: {error}") from error
    except ValueError as error:
        raise CollectorError(f"Jobsyn response was not valid JSON for {source_url}") from error

    if not isinstance(payload, dict):
        raise CollectorError(f"Jobsyn response was not a JSON object for {source_url}")

    return payload


def _build_posting(
    company_config: dict[str, Any],
    raw_job: dict[str, Any],
) -> JobPosting | None:
    title = raw_job.get("title_exact") or raw_job.get("title")
    if not title:
        return None

    source_job_id = _string_or_none(raw_job.get("reqid") or raw_job.get("guid") or raw_job.get("id"))
    source_url = _build_source_url(company_config, raw_job, source_job_id)
    location = _build_location(raw_job)
    description = raw_job.get("description")

    posting = JobPosting(
        company_key=company_config["company_key"],
        company_name=company_config["name"],
        source_type=company_config["source_type"],
        source_url=source_url,
        title=str(title),
        location=location,
        description=str(description) if description else None,
        source_job_id=source_job_id,
        remote_status=None,
        salary_text=None,
    )

    return JobPosting(
        company_key=posting.company_key,
        company_name=posting.company_name,
        source_type=posting.source_type,
        source_url=posting.source_url,
        title=posting.title,
        location=posting.location,
        description=posting.description,
        source_job_id=posting.source_job_id,
        remote_status=posting.remote_status,
        salary_text=posting.salary_text,
        canonical_key=make_canonical_key(
            posting.company_name,
            posting.title,
            posting.location,
        ),
        content_hash=make_content_hash(
            posting.title,
            posting.location,
            posting.description,
        ),
    )


def _build_location(raw_job: dict[str, Any]) -> str | None:
    location = raw_job.get("location_exact")
    if location:
        return str(location)

    city = raw_job.get("city_exact")
    state = raw_job.get("state_short_exact") or raw_job.get("state_short")

    if city and state:
        return f"{city}, {state}"

    if city:
        return str(city)

    return None


def _build_source_url(
    company_config: dict[str, Any],
    raw_job: dict[str, Any],
    source_job_id: str | None,
) -> str:
    for field_name in ("job_url", "url", "apply_url"):
        value = raw_job.get(field_name)
        if value:
            return str(value)

    job_url_template = company_config.get("job_url_template")
    if job_url_template:
        return job_url_template.format(
            reqid=source_job_id or "",
            guid=raw_job.get("guid") or "",
            title_slug=raw_job.get("title_slug") or "",
        )

    referer_url = company_config.get("referer_url") or "https://sandia.jobs/jobs/"
    if source_job_id:
        return f"{referer_url}?{urlencode({'q': source_job_id})}"

    return referer_url


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None

    return str(value)