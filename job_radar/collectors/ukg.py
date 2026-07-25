"""Collect public jobs from UKG Pro Recruiting (formerly UltiPro) boards."""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin

import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_PAGE_SIZE = 50
DEFAULT_MAX_PAGES = 20
USER_AGENT = "JobRadar/0.1 local career-source scanner"
TOKEN_PATTERN = re.compile(
    r'name="__RequestVerificationToken"[^>]*value="([^"]+)"'
)
DETAIL_MARKER = "new US.Opportunity.CandidateOpportunityDetail("


def collect_ukg_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    """Use UKG's anonymous job-board requests and public detail pages."""

    board_url = str(company_config["source_url"]).rstrip("/") + "/"
    company_key = str(company_config["company_key"])
    company_name = str(company_config["name"])
    timeout = int(company_config.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    page_size = int(company_config.get("page_size", DEFAULT_PAGE_SIZE))
    max_pages = int(company_config.get("max_pages", DEFAULT_MAX_PAGES))
    session = requests.Session()
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/json",
        "User-Agent": USER_AGENT,
    }

    try:
        board_response = session.get(board_url, headers=headers, timeout=timeout)
        board_response.raise_for_status()
    except requests.RequestException as error:
        raise CollectorError(
            f"UKG job board request failed for {company_name}"
        ) from error

    token_match = TOKEN_PATTERN.search(board_response.text)
    if token_match is None:
        raise CollectorError(
            f"UKG job board did not provide its public request token for {company_name}"
        )

    endpoint = urljoin(board_url, "JobBoardView/LoadSearchResults")
    token = unescape(token_match.group(1))
    summaries: list[dict[str, Any]] = []

    for page_index in range(max_pages):
        payload = {
            "opportunitySearch": {
                "Top": page_size,
                "Skip": page_index * page_size,
                "QueryString": "",
                "OrderBy": [
                    {
                        "Value": "postedDateDesc",
                        "PropertyName": "PostedDate",
                        "Ascending": False,
                    }
                ],
                "Filters": [],
            }
        }
        try:
            response = session.post(
                endpoint,
                json=payload,
                headers={
                    **headers,
                    "X-RequestVerificationToken": token,
                },
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as error:
            raise CollectorError(
                f"UKG job list request failed for {company_name}"
            ) from error

        if not isinstance(data, dict):
            raise CollectorError(
                f"UKG returned an invalid public job list for {company_name}"
            )
        opportunities = data.get("opportunities")
        if not isinstance(opportunities, list):
            raise CollectorError(
                f"UKG returned an invalid public job list for {company_name}"
            )
        summaries.extend(
            item for item in opportunities if isinstance(item, dict)
        )
        total_count = _safe_int(data.get("totalCount"))
        if not opportunities or (
            total_count is not None and len(summaries) >= total_count
        ):
            break

    postings: list[JobPosting] = []
    seen_ids: set[str] = set()
    for summary in summaries:
        source_job_id = _clean_text(summary.get("Id"))
        if not source_job_id or source_job_id in seen_ids:
            continue
        seen_ids.add(source_job_id)
        source_url = urljoin(
            board_url,
            f"OpportunityDetail?opportunityId={source_job_id}",
        )
        detail = _load_detail(
            session,
            source_url=source_url,
            company_name=company_name,
            headers=headers,
            timeout=timeout,
        )
        title = _clean_text(detail.get("Title")) or _clean_text(
            summary.get("Title")
        )
        if not title:
            continue
        location = _format_locations(
            detail.get("Locations") or summary.get("Locations")
        )
        description = _plain_text(detail.get("Description")) or _clean_text(
            summary.get("BriefDescription")
        )
        remote_status = _clean_text(summary.get("JobLocationType"))
        salary_text = _format_pay_range(detail)
        postings.append(
            JobPosting(
                company_key=company_key,
                company_name=company_name,
                source_type="ukg",
                source_url=source_url,
                title=title,
                location=location,
                description=description,
                source_job_id=source_job_id,
                remote_status=remote_status,
                salary_text=salary_text,
                canonical_key=make_canonical_key(
                    company_key,
                    title,
                    location,
                ),
                content_hash=make_content_hash(
                    title,
                    location,
                    description,
                ),
            )
        )

    return postings


def _load_detail(
    session: requests.Session,
    *,
    source_url: str,
    company_name: str,
    headers: dict[str, str],
    timeout: int,
) -> dict[str, Any]:
    try:
        response = session.get(source_url, headers=headers, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as error:
        raise CollectorError(
            f"UKG job detail request failed for {company_name}"
        ) from error

    marker_index = response.text.find(DETAIL_MARKER)
    if marker_index < 0:
        raise CollectorError(
            f"UKG job detail was not readable for {company_name}"
        )
    json_start = marker_index + len(DETAIL_MARKER)
    try:
        detail, _ = json.JSONDecoder().raw_decode(response.text[json_start:])
    except json.JSONDecodeError as error:
        raise CollectorError(
            f"UKG job detail was not readable for {company_name}"
        ) from error
    if not isinstance(detail, dict):
        raise CollectorError(
            f"UKG job detail was not readable for {company_name}"
        )
    return detail


def _format_locations(value: Any) -> str | None:
    if not isinstance(value, list):
        return None
    labels: list[str] = []
    for location in value:
        if not isinstance(location, dict):
            continue
        address = location.get("Address")
        parts: list[str] = []
        if isinstance(address, dict):
            for field in ("City", "State", "Country"):
                item = address.get(field)
                if isinstance(item, dict):
                    item = item.get("Code") or item.get("Name")
                text = _clean_text(item)
                if text and text not in parts:
                    parts.append(text)
        label = ", ".join(parts) or _clean_text(
            location.get("LocalizedDescription")
        )
        if label and label not in labels:
            labels.append(label)
    return "; ".join(labels) or None


def _format_pay_range(detail: dict[str, Any]) -> str | None:
    pay_range = detail.get("PayRange")
    if not isinstance(pay_range, dict):
        return None
    minimum = pay_range.get("PayRangeMinimum")
    maximum = pay_range.get("PayRangeMaximum")
    if minimum is None and maximum is None:
        return None
    currency = _clean_text(detail.get("PayRangeCurrencyCode")) or "USD"
    if minimum is not None and maximum is not None:
        return f"{minimum} - {maximum} {currency}"
    value = minimum if minimum is not None else maximum
    return f"{value} {currency}"


def _plain_text(value: Any) -> str | None:
    text = _clean_text(value)
    if text is None:
        return None
    return " ".join(re.sub(r"<[^>]+>", " ", unescape(text)).split()) or None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
