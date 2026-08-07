"""Collect complete public listings from Google Careers result pages."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import math
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from job_radar.collectors.collector_http import get_response
from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import clean_human_text, make_canonical_key, make_content_hash


DEFAULT_SOURCE_URL = "https://www.google.com/about/careers/applications/jobs/results"
DEFAULT_MAX_PAGES = 250
MAX_WORKERS = 6
_CALLBACK_KEY = "key: 'ds:1'"


def collect_google_careers_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    """Read Google's complete embedded job records with bounded page concurrency."""

    source_url = str(company_config.get("source_url") or DEFAULT_SOURCE_URL)
    first_jobs, total_jobs, page_size = _fetch_page(company_config, source_url, 1)
    if not first_jobs or total_jobs <= len(first_jobs):
        return first_jobs

    configured_limit = company_config.get("max_pages", DEFAULT_MAX_PAGES)
    try:
        max_pages = max(1, min(int(configured_limit), DEFAULT_MAX_PAGES))
    except (TypeError, ValueError):
        max_pages = DEFAULT_MAX_PAGES
    page_count = min(max_pages, math.ceil(total_jobs / max(1, page_size)))
    if page_count <= 1:
        return first_jobs

    def fetch(page_number: int) -> list[JobPosting]:
        jobs, _total, _width = _fetch_page(
            company_config,
            source_url,
            page_number,
        )
        return jobs

    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, page_count - 1)) as executor:
        later_pages = executor.map(fetch, range(2, page_count + 1))

    postings = list(first_jobs)
    for page in later_pages:
        postings.extend(page)
    return _deduplicate(postings)


def _fetch_page(
    company_config: dict[str, Any],
    source_url: str,
    page_number: int,
) -> tuple[list[JobPosting], int, int]:
    response = get_response(
        _page_url(source_url, page_number),
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "Junior/0.2 public Google Careers collector",
        },
        timeout=30,
        error_type=CollectorError,
        request_error_message="Failed to fetch Google Careers listings",
        include_response_body=True,
    )
    payload = _extract_jobs_payload(response.text)
    raw_jobs = payload[0]
    if raw_jobs is None:
        return [], int(payload[2] or 0), int(payload[3] or 20)
    if not isinstance(raw_jobs, list):
        raise CollectorError("Google Careers returned an invalid public job list")
    postings = [
        posting
        for raw_job in raw_jobs
        if (posting := _parse_job(company_config, raw_job)) is not None
    ]
    return postings, int(payload[2] or len(postings)), int(payload[3] or 20)


def _extract_jobs_payload(html: str) -> list[Any]:
    marker = html.find(_CALLBACK_KEY)
    data_marker = html.find("data:", marker)
    if marker < 0 or data_marker < 0:
        raise CollectorError("Google Careers did not provide its public job data")
    start = data_marker + len("data:")
    while start < len(html) and html[start].isspace():
        start += 1
    if start >= len(html) or html[start] != "[":
        raise CollectorError("Google Careers returned an invalid public job payload")
    end = _balanced_array_end(html, start)
    try:
        payload = json.loads(html[start:end])
    except (TypeError, json.JSONDecodeError) as exc:
        raise CollectorError("Google Careers returned unreadable public job data") from exc
    if not isinstance(payload, list) or len(payload) < 4:
        raise CollectorError("Google Careers returned incomplete public job data")
    return payload


def _balanced_array_end(text: str, start: int) -> int:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        character = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
            if depth == 0:
                return index + 1
    raise CollectorError("Google Careers returned a truncated public job payload")


def _parse_job(
    company_config: dict[str, Any],
    raw_job: object,
) -> JobPosting | None:
    if not isinstance(raw_job, list) or len(raw_job) < 20:
        return None
    source_job_id = _text(raw_job[0])
    title = _text(raw_job[1])
    if not source_job_id or not title:
        return None
    locations = _locations(raw_job[9])
    location = "; ".join(locations) or None
    description = clean_human_text(
        "\n".join(
            part
            for part in (
                _nested_text(raw_job[4]),
                _nested_text(raw_job[10]),
                _nested_text(raw_job[3]),
            )
            if part
        )
    ) or None
    source_url = (
        f"{DEFAULT_SOURCE_URL}/{source_job_id}-{_title_slug(title)}"
    )
    remote_status = (
        "Remote"
        if any("remote" in item.casefold() for item in locations)
        else None
    )
    return JobPosting(
        company_key=str(company_config["company_key"]),
        company_name=str(company_config["name"]),
        source_type="google_careers",
        source_job_id=source_job_id,
        source_url=source_url,
        title=title,
        location=location,
        remote_status=remote_status,
        description=description,
        canonical_key=make_canonical_key(
            str(company_config["company_key"]), title, location
        ),
        content_hash=make_content_hash(title, location, description),
    )


def _locations(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    found: list[str] = []
    for item in value:
        if not isinstance(item, list) or not item:
            continue
        label = _text(item[0])
        if label and label not in found:
            found.append(label)
    return found


def _nested_text(value: object) -> str:
    if isinstance(value, list) and len(value) > 1:
        return _text(value[1])
    return ""


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _title_slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")


def _page_url(source_url: str, page_number: int) -> str:
    parsed = urlsplit(source_url)
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.casefold() != "page"
    ]
    if page_number > 1:
        query.append(("page", str(page_number)))
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), "")
    )


def _deduplicate(postings: list[JobPosting]) -> list[JobPosting]:
    seen: set[str] = set()
    result: list[JobPosting] = []
    for posting in postings:
        identity = posting.source_job_id or posting.source_url
        if identity in seen:
            continue
        seen.add(identity)
        result.append(posting)
    return result
