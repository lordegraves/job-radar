"""Collect every Walmart-family job inside one profile's declared search scope."""

from __future__ import annotations

import re
from html import unescape
from typing import Any
from uuid import uuid4

import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.incremental_cache import report_progress
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash
from job_radar.profile_models import ProfilePreferences


SEARCH_QUERY_ID = "b0467c1f-f578-4261-9280-0ea4614f251c"
DETAIL_QUERY_ID = "db54b06d-3bde-432b-a303-cf94499f261a"
DEFAULT_SOURCE_URL = "https://careers.walmart.com/api/graphql"
DEFAULT_PAGE_SIZE = 10
DEFAULT_MAX_PAGES = 500
MAX_SCOPE_VALUES = 12


def walmart_scope_config(
    preferences: ProfilePreferences | None,
) -> dict[str, list[str]]:
    """Translate public profile preferences into an in-memory collector scope."""

    if preferences is None:
        return {"walmart_target_roles": [], "walmart_locations": []}
    return {
        "walmart_target_roles": list(preferences.target_roles),
        "walmart_locations": list(preferences.preferred_locations),
    }


def collect_walmart_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    """Exhaust Walmart's public results for the active profile's bounded scope."""

    roles = _scope_values(company_config.get("walmart_target_roles"))
    locations = _scope_values(company_config.get("walmart_locations"))
    if not roles:
        raise CollectorError(
            "Walmart requires at least one target role in the active profile.",
            failure_stage="source_configuration",
        )

    source_url = str(company_config.get("source_url") or DEFAULT_SOURCE_URL)
    company_key = str(company_config["company_key"])
    company_name = str(company_config["name"])
    max_pages = int(company_config.get("max_pages", DEFAULT_MAX_PAGES))
    query = _search_text(roles, locations)
    thread_id = f"S-{uuid4()}"
    refined_query: str | None = None
    filter_string: str | None = None
    expected_total: int | None = None
    bounded_health_check = (
        company_config.get("connection_test") is True and "max_pages" in company_config
    )
    postings: list[JobPosting] = []
    seen: set[str] = set()

    for page in range(max_pages):
        report_progress(company_config, f"Reading scoped Walmart page {page + 1}")
        artifact, returned_thread_id = _fetch_search_page(
            source_url=source_url,
            query=query,
            page=page,
            thread_id=thread_id,
            refined_query=refined_query,
            filter_string=filter_string,
        )
        thread_id = returned_thread_id or thread_id
        jobs = artifact.get("jobs")
        total = artifact.get("total_jobs")
        if isinstance(total, int) and total >= 0:
            expected_total = max(expected_total or 0, total)
        if not isinstance(jobs, list):
            raise CollectorError(
                "Walmart returned an invalid scoped job list.",
                failure_stage="initial_search_response" if page == 0 else "results_pagination_response",
            )
        if not jobs:
            break
        refined = artifact.get("refined_query")
        if isinstance(refined, str) and refined.strip():
            refined_query = refined
        returned_filter = artifact.get("filters")
        if isinstance(returned_filter, str) and returned_filter.strip():
            filter_string = returned_filter

        raw_jobs = [job for job in jobs if isinstance(job, dict)]
        details = _fetch_details(
            source_url=source_url,
            job_ids=[str(job.get("job_id") or "") for job in raw_jobs],
        )
        details_by_id = {
            str(item.get("jobId")): item
            for item in details
            if isinstance(item, dict) and item.get("jobId")
        }
        new_count = 0
        for raw_job in raw_jobs:
            job_id = str(raw_job.get("job_id") or "").strip()
            posting = _build_posting(
                company_key=company_key,
                company_name=company_name,
                raw_job=raw_job,
                detail=details_by_id.get(job_id, {}),
            )
            if posting is None or posting.source_job_id in seen:
                continue
            seen.add(str(posting.source_job_id))
            postings.append(posting)
            new_count += 1

        if expected_total is not None and len(postings) >= expected_total:
            break
        if bounded_health_check and page + 1 >= max_pages:
            break
        if not new_count:
            raise CollectorError(
                "Walmart repeated a scoped results page before collection was complete.",
                failure_stage="results_pagination_response",
            )
        if len(raw_jobs) < DEFAULT_PAGE_SIZE:
            break
    else:
        raise CollectorError(
            "Walmart's scoped result set exceeded Junior's safe page limit.",
            failure_stage="results_pagination_response",
        )

    if (
        not bounded_health_check
        and expected_total is not None
        and len(postings) < expected_total
    ):
        raise CollectorError(
            "Walmart ended its scoped results before every reported job was collected.",
            failure_stage="results_pagination_response",
        )
    return postings


def _fetch_search_page(
    *,
    source_url: str,
    query: str,
    page: int,
    thread_id: str,
    refined_query: str | None,
    filter_string: str | None,
) -> tuple[dict[str, Any], str | None]:
    context: dict[str, Any] = {
        "sort": "relevance",
        "active_tab": "jobs",
        "management_levels": [],
        "content_page": 0,
        "future_roles_page": 0,
        "job_page": page,
        "locale": "en_US",
        "direct_search": True,
    }
    if refined_query:
        context["refined_query"] = refined_query
    if filter_string:
        # Walmart returns the exact server-side role/location constraint used
        # for page one. Carry it forward so pagination cannot broaden into the
        # employer's entire 45,000-job catalog.
        context["filters"] = filter_string
    request = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": query if page == 0 else f"Show me page number {page + 1}",
                    }
                ],
            }
        ],
        "thread_id": thread_id,
        "channel": "job_search",
        "context": {"job_search_context": context},
    }
    payload = _post_graphql(
        source_url,
        query_id=SEARCH_QUERY_ID,
        variables={"chatRequest": request},
        failure_stage="initial_search_request" if page == 0 else "results_pagination_request",
    )
    assistant = payload.get("data", {}).get("jobSearchAssistant")
    if not isinstance(assistant, dict):
        raise CollectorError(
            "Walmart did not provide its scoped search response.",
            failure_stage="initial_search_response" if page == 0 else "results_pagination_response",
        )
    messages = assistant.get("tool_messages")
    artifact = messages[0].get("artifact") if isinstance(messages, list) and messages else None
    if not isinstance(artifact, dict) or artifact.get("status") != "success":
        raise CollectorError(
            "Walmart did not provide a successful scoped job result.",
            failure_stage="initial_search_response" if page == 0 else "results_pagination_response",
        )
    returned_thread = assistant.get("thread_id")
    return artifact, returned_thread if isinstance(returned_thread, str) else None


def _fetch_details(*, source_url: str, job_ids: list[str]) -> list[dict[str, Any]]:
    identifiers = [value for value in job_ids if value]
    if not identifiers:
        return []
    payload = _post_graphql(
        source_url,
        query_id=DETAIL_QUERY_ID,
        variables={"jobIds": ",".join(identifiers), "languageCode": "en_US"},
        failure_stage="position_detail_request",
    )
    details = payload.get("data", {}).get("bulkUnifiedJobDetails")
    if not isinstance(details, list):
        raise CollectorError(
            "Walmart did not provide complete public job details.",
            failure_stage="position_detail_response",
        )
    return details


def _post_graphql(
    source_url: str,
    *,
    query_id: str,
    variables: dict[str, Any],
    failure_stage: str,
) -> dict[str, Any]:
    try:
        response = requests.post(
            source_url,
            json={"queryId": query_id, "variables": variables, "headers": {}},
            headers={
                "User-Agent": "Junior/0.2 public Walmart careers collector",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": "https://careers.walmart.com/us/en/results",
            },
            timeout=90,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        raise CollectorError(
            "Walmart's public careers service could not be read.",
            failure_stage=failure_stage,
        ) from error
    if not isinstance(payload, dict) or payload.get("errors"):
        raise CollectorError(
            "Walmart's public careers service returned an invalid response.",
            failure_stage=failure_stage.replace("request", "response"),
        )
    return payload


def _build_posting(
    *,
    company_key: str,
    company_name: str,
    raw_job: dict[str, Any],
    detail: dict[str, Any],
) -> JobPosting | None:
    job_id = str(raw_job.get("job_id") or detail.get("jobId") or "").strip()
    title = _text(detail.get("jobPostingTitle") or raw_job.get("jobPostingTitle") or raw_job.get("title"))
    if not job_id or not title:
        return None
    city = _text(raw_job.get("city"))
    state = _text(raw_job.get("state"))
    country = _text(raw_job.get("country"))
    location = ", ".join(value for value in (city, state, country) if value) or None
    description = _html_text(detail.get("description"))
    min_pay = raw_job.get("minPay")
    max_pay = raw_job.get("maxPay")
    frequency = _text(raw_job.get("payFrequency"))
    salary = None
    if isinstance(min_pay, (int, float)) and isinstance(max_pay, (int, float)):
        salary = f"${min_pay:,.0f}–${max_pay:,.0f}" + (f" {frequency}" if frequency else "")
    source_url = f"https://careers.walmart.com/us/en/jobs/{job_id}"
    return JobPosting(
        company_key=company_key,
        company_name=company_name,
        source_type="walmart",
        source_url=source_url,
        title=title,
        location=location,
        description=description,
        source_job_id=job_id,
        remote_status="Remote" if location and "remote" in location.casefold() else None,
        salary_text=salary,
        canonical_key=make_canonical_key(company_name, title, location),
        content_hash=make_content_hash(title, location, description),
    )


def _scope_values(raw: Any) -> list[str]:
    if not isinstance(raw, (list, tuple)):
        return []
    values: list[str] = []
    seen: set[str] = set()
    for item in raw:
        value = " ".join(str(item).split())
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            values.append(value)
        if len(values) >= MAX_SCOPE_VALUES:
            break
    return values


def _search_text(roles: list[str], locations: list[str]) -> str:
    role_text = " or ".join(roles)
    if not locations:
        return f"{role_text} jobs"
    return f"{role_text} jobs in {' or '.join(locations)}"


def _html_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"<[^>]+>", " ", unescape(str(value)))
    return " ".join(text.split()) or None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    return " ".join(str(value).split()) or None
