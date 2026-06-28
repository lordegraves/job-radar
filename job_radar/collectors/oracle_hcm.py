from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


DEFAULT_PAGE_SIZE = 25
DEFAULT_MAX_PAGES = 40

EXPAND_FIELDS = (
    "requisitionList.workLocation,"
    "requisitionList.otherWorkLocations,"
    "requisitionList.secondaryLocations,"
    "flexFieldsFacet.values,"
    "requisitionList.requisitionFlexFields"
)


def collect_oracle_hcm_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    company_key = str(company_config["company_key"])
    company_name = str(company_config["name"])
    source_url = str(company_config["source_url"])
    site_number = str(company_config.get("site_number", "CX"))
    referer_url = str(company_config.get("referer_url", ""))

    page_size = int(company_config.get("page_size", DEFAULT_PAGE_SIZE))
    max_pages = int(company_config.get("max_pages", DEFAULT_MAX_PAGES))

    postings: list[JobPosting] = []
    seen: set[str] = set()

    for page_index in range(max_pages):
        offset = page_index * page_size

        try:
            payload = _fetch_oracle_hcm_page(
                source_url=source_url,
                site_number=site_number,
                limit=page_size,
                offset=offset,
                referer_url=referer_url,
            )
        except requests.RequestException as exc:
            raise CollectorError(f"Oracle HCM request failed for {company_name}: {exc}") from exc

        search_item = _get_search_item(payload)
        requisitions = search_item.get("requisitionList") or []

        if not requisitions:
            break

        for requisition in requisitions:
            posting = _build_posting(
                company_key=company_key,
                company_name=company_name,
                source_type="oracle_hcm",
                source_url=source_url,
                site_number=site_number,
                referer_url=referer_url,
                requisition=requisition,
            )

            if posting is None:
                continue

            dedupe_key = posting.source_job_id or posting.source_url
            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)
            postings.append(posting)

        total_jobs_count = int(search_item.get("TotalJobsCount") or 0)
        if total_jobs_count and offset + page_size >= total_jobs_count:
            break

    return postings


def _fetch_oracle_hcm_page(
    *,
    source_url: str,
    site_number: str,
    limit: int,
    offset: int,
    referer_url: str,
) -> dict[str, Any]:
    params = {
        "onlyData": "true",
        "expand": EXPAND_FIELDS,
        "finder": f"findReqs;siteNumber={site_number},limit={limit},offset={offset}",
    }

    headers = {
        "User-Agent": "JobRadar/0.1 local career-source scanner",
        "Accept": "application/json, text/plain, */*",
    }

    if referer_url:
        headers["Referer"] = referer_url

    response = requests.get(source_url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def _get_search_item(payload: dict[str, Any]) -> dict[str, Any]:
    items = payload.get("items") or []
    if not items:
        return {}
    first_item = items[0]
    if not isinstance(first_item, dict):
        return {}
    return first_item


def _build_posting(
    *,
    company_key: str,
    company_name: str,
    source_type: str,
    source_url: str,
    site_number: str,
    referer_url: str,
    requisition: dict[str, Any],
) -> JobPosting | None:
    title = _clean_text(requisition.get("Title"))
    if not title:
        return None

    source_job_id = _clean_text(requisition.get("Id"))
    location = _clean_text(requisition.get("PrimaryLocation"))

    posting_url = _build_job_url(
        source_url=source_url,
        referer_url=referer_url,
        site_number=site_number,
        source_job_id=source_job_id,
    )

    description = _build_description(requisition)

    posting = JobPosting(
        company_key=company_key,
        company_name=company_name,
        source_type=source_type,
        source_url=posting_url,
        title=title,
        location=location,
        description=description,
        source_job_id=source_job_id,
        remote_status=_clean_text(requisition.get("WorkplaceType")),
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


def _build_description(requisition: dict[str, Any]) -> str | None:
    parts = [
        _clean_text(requisition.get("ShortDescriptionStr")),
        _clean_text(requisition.get("ExternalResponsibilitiesStr")),
        _clean_text(requisition.get("ExternalQualificationsStr")),
    ]

    description = "\n\n".join(part for part in parts if part)
    return description or None


def _build_job_url(
    *,
    source_url: str,
    referer_url: str,
    site_number: str,
    source_job_id: str | None,
) -> str:
    if not source_job_id:
        return referer_url or source_url

    if referer_url:
        base = referer_url.rstrip("/")
        if "/sites/" in base:
            return f"{base}/job/{source_job_id}"

    parsed = urlparse(source_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return f"{origin}/hcmUI/CandidateExperience/en/sites/{site_number}/job/{source_job_id}"


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None