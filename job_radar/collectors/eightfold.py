"""Collect public jobs from Eightfold PCS career sites."""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urljoin

import requests

from job_radar.collectors.collector_http import get_response
from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.pagination import get_max_pages, get_page_size
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


DEFAULT_PAGE_SIZE = 20
DEFAULT_MAX_PAGES = 100


def collect_eightfold_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    """Collect search results and their public descriptions from Eightfold."""

    company_key = str(company_config["company_key"])
    company_name = str(company_config["name"])
    source_url = str(company_config["source_url"]).rstrip("/")
    domain = str(company_config["domain"])
    page_size = get_page_size(company_config, default=DEFAULT_PAGE_SIZE)
    max_pages = get_max_pages(company_config, default=DEFAULT_MAX_PAGES)
    connection_test = company_config.get("connection_test") is True
    postings: list[JobPosting] = []
    seen: set[str] = set()
    seen_pages: set[tuple[str, ...]] = set()
    expected_total: int | None = None

    start = 0
    for _page_index in range(max_pages):
        try:
            response = get_response(
                f"{source_url}/api/pcsx/search",
                params={
                    "domain": domain,
                    "query": "",
                    "location": "",
                    "start": start,
                    "sort_by": "relevance",
                },
                headers={
                    "Accept": "application/json",
                    "User-Agent": "JobRadar/0.1 local career-source scanner",
                },
                timeout=30,
            )
            payload = response.json()
        except (requests.RequestException, ValueError) as error:
            raise CollectorError(
                f"Eightfold search failed for {company_name}: {error}"
            ) from error

        data = payload.get("data") if isinstance(payload, dict) else None
        raw_positions = data.get("positions") if isinstance(data, dict) else None
        if not isinstance(raw_positions, list) or not raw_positions:
            break
        page_identity = tuple(
            str(position.get("id") or position.get("positionUrl") or "")
            for position in raw_positions
            if isinstance(position, dict)
        )
        if page_identity in seen_pages:
            break
        seen_pages.add(page_identity)

        for raw_position in raw_positions:
            if not isinstance(raw_position, dict):
                continue
            posting = _build_posting(
                company_key=company_key,
                company_name=company_name,
                source_url=source_url,
                domain=domain,
                raw_position=raw_position,
                fetch_details=not connection_test,
            )
            if posting is None:
                continue
            dedupe_key = posting.source_job_id or posting.source_url
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            postings.append(posting)

        count = data.get("count") if isinstance(data, dict) else None
        # Some Eightfold tenants report an unstable total on later pages.
        # Retain the largest positive total so a false zero cannot truncate a scan.
        if isinstance(count, int) and count > 0:
            expected_total = max(expected_total or 0, count)
        if expected_total is not None and len(postings) >= expected_total:
            break
        if max_pages == 1:
            # Source-health checks deliberately sample one result page. A
            # normal scan retains the configured multi-page behavior.
            break
        # Eightfold may enforce a smaller server-side page size than Junior
        # requests. Advance by what the server actually returned so valid jobs
        # on later pages are not silently skipped.
        start += len(raw_positions)
        if expected_total is None and len(raw_positions) < page_size:
            break

    return postings


def _build_posting(
    *,
    company_key: str,
    company_name: str,
    source_url: str,
    domain: str,
    raw_position: dict[str, Any],
    fetch_details: bool = True,
) -> JobPosting | None:
    position_id = str(raw_position.get("id") or "").strip()
    title = str(raw_position.get("name") or "").strip()
    position_path = str(raw_position.get("positionUrl") or "").strip()
    if not position_id or not title or not position_path:
        return None

    detail = (
        _fetch_position_detail(
            source_url=source_url,
            domain=domain,
            position_id=position_id,
        )
        if fetch_details
        else {}
    )
    locations = detail.get("locations") or raw_position.get("locations") or []
    location = ", ".join(str(item) for item in locations if item) or None
    description = _plain_text(
        detail.get("jobDescription") or raw_position.get("jobDescription")
    )
    remote_status = str(
        detail.get("efcustomTextJobRequisitionWorkstyle")
        or raw_position.get("efcustomTextJobRequisitionWorkstyle")
        or detail.get("workLocationOption")
        or raw_position.get("workLocationOption")
        or ""
    ).strip() or None
    source_job_id = str(
        detail.get("displayJobId")
        or raw_position.get("displayJobId")
        or position_id
    )
    posting_url = urljoin(f"{source_url}/", position_path)

    return JobPosting(
        company_key=company_key,
        company_name=company_name,
        source_type="eightfold",
        source_url=posting_url,
        title=title,
        location=location,
        description=description,
        source_job_id=source_job_id,
        remote_status=remote_status,
        salary_text=None,
        canonical_key=make_canonical_key(company_name, title, location),
        content_hash=make_content_hash(title, location, description),
    )


def _fetch_position_detail(
    *,
    source_url: str,
    domain: str,
    position_id: str,
) -> dict[str, Any]:
    try:
        response = get_response(
            f"{source_url}/api/pcsx/position_details",
            params={
                "position_id": position_id,
                "domain": domain,
                "hl": "en",
            },
            headers={
                "Accept": "application/json",
                "User-Agent": "JobRadar/0.1 local career-source scanner",
            },
            timeout=30,
        )
        payload = response.json()
    except (requests.RequestException, ValueError):
        return {}
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else {}


def _plain_text(value: Any) -> str | None:
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", str(value))
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None
