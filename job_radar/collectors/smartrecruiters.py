from __future__ import annotations

import re
from typing import Any

import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 10


def collect_smartrecruiters_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    company_key = str(company_config["company_key"])
    company_name = str(company_config["name"])
    source_url = str(company_config["source_url"])
    company_identifier = str(company_config.get("company_identifier", company_key))
    page_size = int(company_config.get("page_size", DEFAULT_PAGE_SIZE))
    max_pages = int(company_config.get("max_pages", DEFAULT_MAX_PAGES))

    postings: list[JobPosting] = []
    seen: set[str] = set()

    for page_index in range(max_pages):
        offset = page_index * page_size

        try:
            payload = _fetch_smartrecruiters_page(
                source_url=source_url,
                limit=page_size,
                offset=offset,
            )
        except requests.RequestException as exc:
            raise CollectorError(
                f"SmartRecruiters request failed for {company_name}: {exc}"
            ) from exc

        jobs = payload.get("content") or []
        if not jobs:
            break

        for job in jobs:
            posting = _build_posting(
                company_key=company_key,
                company_name=company_name,
                source_type="smartrecruiters",
                company_identifier=company_identifier,
                job=job,
            )

            if posting is None:
                continue

            dedupe_key = posting.source_job_id or posting.source_url
            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)
            postings.append(posting)

        total_found = int(payload.get("totalFound") or 0)
        if total_found and offset + page_size >= total_found:
            break

    return postings


def _fetch_smartrecruiters_page(
    *,
    source_url: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    response = requests.get(
        source_url,
        params={
            "limit": limit,
            "offset": offset,
        },
        headers={
            "User-Agent": "JobRadar/0.1 local career-source scanner",
            "Accept": "application/json, text/plain, */*",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _build_posting(
    *,
    company_key: str,
    company_name: str,
    source_type: str,
    company_identifier: str,
    job: dict[str, Any],
) -> JobPosting | None:
    title = _clean_text(job.get("name"))
    if not title:
        return None

    source_job_id = _clean_text(job.get("id"))
    location = _get_location(job)
    description = _build_description(job)
    remote_status = _get_remote_status(job)
    source_url = _build_job_url(
        company_identifier=company_identifier,
        source_job_id=source_job_id,
        title=title,
        fallback_ref=_clean_text(job.get("ref")),
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
        remote_status=remote_status,
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


def _get_location(job: dict[str, Any]) -> str | None:
    location = job.get("location") or {}

    if isinstance(location, dict):
        full_location = _clean_text(location.get("fullLocation"))
        if full_location:
            return full_location

        city = _clean_text(location.get("city"))
        region = _clean_text(location.get("region"))
        country = _clean_text(location.get("country"))

        parts = [part for part in (city, region, country) if part]
        if parts:
            return ", ".join(parts)

    return None


def _get_remote_status(job: dict[str, Any]) -> str | None:
    location = job.get("location") or {}
    if not isinstance(location, dict):
        return None

    if location.get("remote") is True:
        return "Remote"

    if location.get("hybrid") is True:
        return "Hybrid"

    return None


def _build_description(job: dict[str, Any]) -> str | None:
    parts = [
        _clean_text(job.get("refNumber")),
        _nested_label(job, "typeOfEmployment"),
        _nested_label(job, "experienceLevel"),
        _nested_label(job, "industry"),
        _nested_label(job, "function"),
        _custom_fields_text(job),
    ]

    description = "\n\n".join(part for part in parts if part)
    return description or None


def _nested_label(job: dict[str, Any], key: str) -> str | None:
    value = job.get(key)
    if not isinstance(value, dict):
        return None
    return _clean_text(value.get("label"))


def _custom_fields_text(job: dict[str, Any]) -> str | None:
    custom_fields = job.get("customField") or []
    lines: list[str] = []

    for field in custom_fields:
        if not isinstance(field, dict):
            continue

        label = _clean_text(field.get("fieldLabel"))
        value = _clean_text(field.get("valueLabel"))

        if not label or not value:
            continue

        lines.append(f"{label}: {value}")

    return "\n".join(lines) or None


def _build_job_url(
    *,
    company_identifier: str,
    source_job_id: str | None,
    title: str,
    fallback_ref: str | None,
) -> str:
    # The API exposes a machine-readable ref URL, but reports should link to
    # the public SmartRecruiters job page.

    if not source_job_id:
        return f"https://careers.smartrecruiters.com/{company_identifier}"

    slug = _slugify(title)
    return f"https://jobs.smartrecruiters.com/{company_identifier}/{source_job_id}-{slug}"


def _slugify(value: str) -> str:
    slug = value.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None