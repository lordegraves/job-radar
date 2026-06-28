from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlencode

import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


DEFAULT_PAGE_SIZE = 10
DEFAULT_MAX_PAGES = 25


def collect_phenom_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    company_key = str(company_config["company_key"])
    company_name = str(company_config["name"])
    source_url = str(company_config["source_url"])
    job_base_url = str(company_config.get("job_base_url", source_url))
    page_size = int(company_config.get("page_size", DEFAULT_PAGE_SIZE))
    max_pages = int(company_config.get("max_pages", DEFAULT_MAX_PAGES))

    postings: list[JobPosting] = []
    seen: set[str] = set()
    total_hits: int | None = None

    for page_index in range(max_pages):
        offset = page_index * page_size

        try:
            html = _fetch_phenom_page(source_url=source_url, offset=offset)
        except requests.RequestException as exc:
            raise CollectorError(f"Phenom request failed for {company_name}: {exc}") from exc

        search_data = _extract_eager_load_refine_search(html)
        if not search_data:
            break

        if total_hits is None:
            total_hits = _safe_int(search_data.get("totalHits"))

        jobs_data = search_data.get("data") or {}
        jobs = jobs_data.get("jobs") or []

        if not jobs:
            break

        for job in jobs:
            if not isinstance(job, dict):
                continue

            posting = _build_posting(
                company_key=company_key,
                company_name=company_name,
                source_type="phenom",
                job_base_url=job_base_url,
                job=job,
            )

            if posting is None:
                continue

            dedupe_key = posting.source_job_id or posting.source_url
            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)
            postings.append(posting)

        if total_hits is not None and len(postings) >= total_hits:
            break

    return postings


def _fetch_phenom_page(*, source_url: str, offset: int) -> str:
    separator = "&" if "?" in source_url else "?"
    url = f"{source_url}{separator}{urlencode({'from': offset, 's': 1})}"

    response = requests.get(
        url,
        headers={
            "User-Agent": "JobRadar/0.1 local career-source scanner",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.text


def _extract_eager_load_refine_search(html: str) -> dict[str, Any] | None:
    ddo = _extract_phapp_ddo(html)
    if not ddo:
        return None

    search_data = ddo.get("eagerLoadRefineSearch")
    if not isinstance(search_data, dict):
        return None

    return search_data


def _extract_phapp_ddo(html: str) -> dict[str, Any] | None:
    marker = "phApp.ddo = "
    start = html.find(marker)
    if start == -1:
        return None

    start += len(marker)
    raw = _extract_json_object(html, start)

    if not raw:
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    return data


def _extract_json_object(text: str, start: int) -> str | None:
    depth = 0
    in_string = False
    escape = False
    object_start: int | None = None

    for index in range(start, len(text)):
        char = text[index]

        if object_start is None:
            if char.isspace():
                continue

            if char != "{":
                return None

            object_start = index
            depth = 1
            continue

        if escape:
            escape = False
            continue

        if char == "\\":
            escape = True
            continue

        if char == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == "{":
            depth += 1
            continue

        if char == "}":
            depth -= 1
            if depth == 0:
                return text[object_start : index + 1]

    return None


def _build_posting(
    *,
    company_key: str,
    company_name: str,
    source_type: str,
    job_base_url: str,
    job: dict[str, Any],
) -> JobPosting | None:
    title = _clean_text(job.get("title"))
    job_seq_no = _clean_text(job.get("jobSeqNo"))

    if not title or not job_seq_no:
        return None

    source_job_id = _clean_text(job.get("reqId")) or _clean_text(job.get("jobId")) or job_seq_no
    location = _clean_text(job.get("location")) or _clean_text(job.get("cityStateCountry"))
    description = _build_description(job)
    source_url = _build_job_url(
        job_base_url=job_base_url,
        job_seq_no=job_seq_no,
        title=title,
    )

    posting = JobPosting(
        company_key=company_key,
        company_name=company_name,
        source_type=source_type,
        source_url=source_url,
        title=title,
        location=location,
        description=description,
        source_job_id=source_job_id,
        remote_status=_clean_text(job.get("isremote")),
        salary_text=None,
        canonical_key=None,
        content_hash=None,
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


def _build_description(job: dict[str, Any]) -> str | None:
    parts = [
        _clean_text(job.get("descriptionTeaser")),
        _format_label("Category", job.get("category")),
        _format_label("Subcategory", job.get("subCategory")),
        _format_label("Type", job.get("type")),
        _format_label("Posted Date", job.get("postedDate")),
        _format_label("Job Seq No", job.get("jobSeqNo")),
    ]

    description = "\n\n".join(part for part in parts if part)
    return description or None


def _build_job_url(*, job_base_url: str, job_seq_no: str, title: str) -> str:
    base = job_base_url.rstrip("/")
    slug = _slugify(title)
    return f"{base}/job/{job_seq_no}/{slug}"


def _slugify(value: str) -> str:
    slug = value.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _format_label(label: str, value: Any) -> str | None:
    clean_value = _clean_text(value)
    if not clean_value:
        return None
    return f"{label}: {clean_value}"


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None