"""Collect public jobs from Eightfold PCS career sites."""

from __future__ import annotations

import html
import re
import time
from typing import Any
from urllib.parse import urljoin

import requests

from job_radar.collectors.collector_http import get_response
from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.incremental_cache import (
    get_cached_posting,
    listing_fingerprint,
    record_listing,
)
from job_radar.collectors.pagination import get_max_pages, get_page_size
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


DEFAULT_PAGE_SIZE = 20
DEFAULT_MAX_PAGES = 100
DETAIL_REQUEST_ATTEMPTS = 3
DETAIL_RETRY_DELAY_SECONDS = 1.0
SEARCH_REQUEST_ATTEMPTS = 5
SEARCH_RETRY_DELAY_SECONDS = 2.0
REQUEST_PACING_SECONDS = 0.1


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
    # A source-health check must exercise the detail endpoint used by a real
    # scan, not merely prove that Eightfold's search page can be reached.
    detail_probe_pending = connection_test and max_pages in {1, 2}

    start = 0
    for page_index in range(max_pages):
        request_stage = (
            "initial_search_request"
            if page_index == 0
            else "results_pagination_request"
        )
        response_stage = (
            "initial_search_response"
            if page_index == 0
            else "results_pagination_response"
        )
        response = _fetch_search_page(
            source_url=source_url,
            domain=domain,
            start=start,
            company_name=company_name,
            failure_stage=request_stage,
        )

        try:
            payload = response.json()
        except ValueError as error:
            raise CollectorError(
                f"Eightfold search failed for {company_name}: {error}",
                failure_stage=response_stage,
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
                company_config=company_config,
                fetch_details=not connection_test or detail_probe_pending,
            )
            if posting is None:
                continue
            detail_probe_pending = False
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
        if connection_test and page_index + 1 >= max_pages:
            # Source-health checks deliberately sample a bounded result set.
            # A normal scan retains the configured multi-page behavior.
            break
        # Eightfold may enforce a smaller server-side page size than Junior
        # requests. Advance by what the server actually returned so valid jobs
        # on later pages are not silently skipped.
        start += len(raw_positions)
        if expected_total is None and len(raw_positions) < page_size:
            break
        time.sleep(REQUEST_PACING_SECONDS)

    return postings


def _build_posting(
    *,
    company_key: str,
    company_name: str,
    source_url: str,
    domain: str,
    raw_position: dict[str, Any],
    company_config: dict[str, Any] | None = None,
    fetch_details: bool = True,
) -> JobPosting | None:
    position_id = str(raw_position.get("id") or "").strip()
    listing_identity = str(
        raw_position.get("displayJobId") or position_id
    ).strip()
    title = str(raw_position.get("name") or "").strip()
    position_path = str(raw_position.get("positionUrl") or "").strip()
    if not position_id or not title or not position_path:
        return None

    fingerprint = listing_fingerprint(
        {
            "id": listing_identity,
            "title": title,
            "path": position_path,
            "locations": raw_position.get("locations"),
            "workstyle": raw_position.get(
                "efcustomTextJobRequisitionWorkstyle"
            ),
        }
    )
    cached = (
        get_cached_posting(
            company_config,
            identity=listing_identity,
            fingerprint=fingerprint,
        )
        if company_config is not None and fetch_details
        else None
    )
    detail = (
        _fetch_position_detail(
            source_url=source_url,
            domain=domain,
            position_id=position_id,
            company_name=company_name,
        )
        if fetch_details and cached is None
        else {}
    )
    if company_config is not None:
        record_listing(
            company_config,
            identity=listing_identity,
            fingerprint=fingerprint,
            reused=cached is not None,
        )
    if cached is not None:
        cached_posting = cached.posting
        return JobPosting(
            company_key=company_key,
            company_name=company_name,
            source_type="eightfold",
            source_url=cached_posting.source_url,
            title=title,
            location=cached_posting.location,
            description=cached_posting.description,
            source_job_id=cached_posting.source_job_id,
            remote_status=cached_posting.remote_status,
            salary_text=cached_posting.salary_text,
            canonical_key=make_canonical_key(
                company_name,
                title,
                cached_posting.location,
            ),
            content_hash=make_content_hash(
                title,
                cached_posting.location,
                cached_posting.description,
            ),
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
    # Use the identity advertised by the listing so incremental lookup can
    # decide whether a detail request is needed before making that request.
    source_job_id = listing_identity
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


def _fetch_search_page(
    *,
    source_url: str,
    domain: str,
    start: int,
    company_name: str,
    failure_stage: str,
) -> requests.Response:
    """Honor rate limiting before declaring a paginated scan incomplete."""

    for attempt in range(SEARCH_REQUEST_ATTEMPTS):
        try:
            return get_response(
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
        except requests.RequestException as error:
            status_code = getattr(error.response, "status_code", None)
            retryable = status_code == 429 or (
                isinstance(status_code, int) and status_code >= 500
            )
            if retryable and attempt + 1 < SEARCH_REQUEST_ATTEMPTS:
                retry_after = getattr(error.response, "headers", {}).get(
                    "Retry-After"
                )
                try:
                    delay = float(retry_after)
                except (TypeError, ValueError):
                    delay = SEARCH_RETRY_DELAY_SECONDS * (2**attempt)
                time.sleep(min(max(delay, 0.1), 30.0))
                continue
            raise CollectorError(
                f"Eightfold search failed for {company_name}: {error}",
                failure_stage=failure_stage,
            ) from error
    raise CollectorError(
        f"Eightfold search failed for {company_name}.",
        failure_stage=failure_stage,
    )


def _fetch_position_detail(
    *,
    source_url: str,
    domain: str,
    position_id: str,
    company_name: str,
) -> dict[str, Any]:
    response = None
    for attempt in range(DETAIL_REQUEST_ATTEMPTS):
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
            break
        except requests.RequestException as error:
            status_code = getattr(error.response, "status_code", None)
            temporary_failure = status_code == 429 or (
                isinstance(status_code, int) and status_code >= 500
            )
            if temporary_failure and attempt + 1 < DETAIL_REQUEST_ATTEMPTS:
                time.sleep(DETAIL_RETRY_DELAY_SECONDS)
                continue
            raise CollectorError(
                f"Eightfold position details could not be retrieved for "
                f"{company_name}.",
                failure_stage="position_detail_request",
            ) from error

    if response is None:  # Defensive guard; the loop either returns or raises.
        raise CollectorError(
            f"Eightfold position details could not be retrieved for {company_name}.",
            failure_stage="position_detail_request",
        )

    try:
        payload = response.json()
    except ValueError as error:
        raise CollectorError(
            f"Eightfold position details were not readable for {company_name}.",
            failure_stage="position_detail_response",
        ) from error
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise CollectorError(
            f"Eightfold position details were incomplete for {company_name}.",
            failure_stage="position_detail_response",
        )
    return data


def _plain_text(value: Any) -> str | None:
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", str(value))
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None
