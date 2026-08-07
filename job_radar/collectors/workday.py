"""Collect and normalize jobs from Workday recruiting APIs."""

from concurrent.futures import ThreadPoolExecutor
import time
from typing import Any

import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.incremental_cache import (
    DETAIL_PLANNER_CONFIG_KEY,
    get_cached_posting,
    listing_fingerprint,
    record_listing,
)
from job_radar.collectors.pagination import get_max_pages, get_page_size
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


DEFAULT_WORKDAY_LIMIT = 20
DEFAULT_WORKDAY_MAX_PAGES = 100
WORKDAY_DETAIL_NORMALIZATION_VERSION = 4
WORKDAY_SEARCH_ATTEMPTS = 3
WORKDAY_SEARCH_RETRY_SECONDS = 1.0
WORKDAY_DETAIL_ATTEMPTS = 4
WORKDAY_DETAIL_RETRY_SECONDS = 0.5

_PLACEHOLDER_JOB_IDS = {"job", "job posting", "spotlight job"}


WORKDAY_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "junior/0.2",
}


def _build_workday_payload(offset: int, limit: int) -> dict[str, Any]:
    return {
        "appliedFacets": {},
        "limit": limit,
        "offset": offset,
        "searchText": "",
    }


def _get_job_id(job: dict[str, Any]) -> str | None:
    for field_name in ["bulletFields", "jobReqId", "id"]:
        value = job.get(field_name)

        if isinstance(value, list) and value:
            candidate = str(value[0]).strip()
            if candidate.casefold() not in _PLACEHOLDER_JOB_IDS:
                return candidate

        elif value:
            candidate = str(value).strip()
            if candidate.casefold() not in _PLACEHOLDER_JOB_IDS:
                return candidate

    external_path = job.get("externalPath")
    if external_path:
        return str(external_path).strip() or None

    return None


def _get_title(job: dict[str, Any]) -> str | None:
    title = job.get("title")

    if not title:
        return None

    return str(title)


def _get_location(job: dict[str, Any]) -> str | None:
    locations_text = job.get("locationsText")

    if locations_text:
        return str(locations_text)

    locations = job.get("locations")

    if isinstance(locations, list) and locations:
        names = []

        for location in locations:
            if isinstance(location, dict):
                name = location.get("name")

                if name:
                    names.append(str(name))
            elif location:
                names.append(str(location))

        if names:
            return ", ".join(names)

    return None


def _get_description(job: dict[str, Any]) -> str | None:
    description: str | None = None
    for field_name in ["description", "jobDescription", "summary"]:
        value = job.get(field_name)

        if value:
            description = str(value)
            break

    time_type = job.get("timeType")
    if time_type:
        employment_fact = f"Employment type: {time_type}"
        return f"{description}\n{employment_fact}" if description else employment_fact
    return description


def _detail_api_url(source_url: str, external_path: str) -> str | None:
    """Build the Workday detail endpoint that contains the complete posting."""

    marker = "/jobs"
    if marker not in source_url:
        return None

    detail_path = external_path.lstrip("/")
    if detail_path.startswith("job/"):
        detail_path = detail_path[4:]
    # Split at the final search endpoint. Some employers name the Workday site
    # itself "jobs" (for example, /cxs/tenant/jobs/jobs); splitting at the
    # first occurrence drops the site name and makes every detail URL invalid.
    return source_url.rsplit(marker, 1)[0].rstrip("/") + "/job/" + detail_path


def _merge_workday_detail(
    raw_job: dict[str, Any],
    detail_payload: dict[str, Any],
) -> dict[str, Any]:
    """Merge richer detail fields without discarding stable search metadata."""

    merged = dict(raw_job)
    detail = detail_payload.get("jobPostingInfo", detail_payload)
    if not isinstance(detail, dict):
        return merged

    field_map = {
        "title": ("title",),
        "jobDescription": ("jobDescription", "description"),
        "locationsText": ("location", "locationsText"),
        "jobReqId": ("jobReqId",),
        "externalUrl": ("externalUrl",),
        "timeType": ("timeType",),
    }

    for target, candidates in field_map.items():
        for candidate in candidates:
            value = detail.get(candidate)
            if value:
                merged[target] = value
                break

    additional_locations = detail.get("additionalLocations")
    if additional_locations and merged.get("locationsText"):
        merged["locationsText"] = ", ".join(
            [str(merged["locationsText"])]
            + [str(value) for value in additional_locations if value]
        )

    return merged


def _fetch_workday_page(
    source_url: str,
    *,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Retry a transient page without exposing response bodies or raw errors."""

    for attempt in range(WORKDAY_SEARCH_ATTEMPTS):
        try:
            response = requests.post(
                source_url,
                json=payload,
                headers=WORKDAY_HEADERS,
                timeout=30,
            )
            response.raise_for_status()
            response_payload = response.json()
        except (requests.RequestException, ValueError) as error:
            if attempt + 1 < WORKDAY_SEARCH_ATTEMPTS:
                time.sleep(WORKDAY_SEARCH_RETRY_SECONDS * (attempt + 1))
                continue
            raise CollectorError(
                "Workday did not return a readable job-results page after "
                f"{WORKDAY_SEARCH_ATTEMPTS} attempts.",
                failure_stage="results_pagination_request",
            ) from error
        if not isinstance(response_payload, dict):
            raise CollectorError(
                "Workday returned an unreadable job-results page.",
                failure_stage="results_pagination_response",
            )
        return response_payload

    raise CollectorError(
        "Workday did not return a job-results page.",
        failure_stage="results_pagination_request",
    )


def _fetch_workday_detail(
    source_url: str,
    raw_job: dict[str, Any],
    company_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    external_path = raw_job.get("externalPath")
    has_description = any(
        raw_job.get(field_name)
        for field_name in ("description", "jobDescription", "summary")
    )
    if not external_path or has_description:
        return raw_job

    detail_url = _detail_api_url(source_url, str(external_path))
    if detail_url is None:
        return raw_job

    identity = _get_job_id(raw_job) or str(external_path)
    planner = (
        company_config.get(DETAIL_PLANNER_CONFIG_KEY)
        if company_config is not None
        else None
    )
    if callable(planner):
        decision = planner(_get_title(raw_job) or "", _get_location(raw_job))
        if not decision.retrieve:
            skipped = dict(raw_job)
            skipped["_junior_detail_retrieval_reason"] = decision.reason
            return skipped
    fingerprint = listing_fingerprint(
        {
            "identity": identity,
            "title": _get_title(raw_job),
            "location": _get_location(raw_job),
            "external_path": external_path,
            # A parser upgrade must refresh unchanged cached detail once so
            # newly normalized facts are not delayed for the cache lifetime.
            "normalization_version": WORKDAY_DETAIL_NORMALIZATION_VERSION,
        }
    )
    if company_config is not None:
        cached = get_cached_posting(
            company_config,
            identity=identity,
            fingerprint=fingerprint,
        )
        if cached is not None:
            posting = cached.posting
            record_listing(
                company_config,
                identity=identity,
                fingerprint=fingerprint,
                reused=True,
            )
            merged = dict(raw_job)
            merged["jobDescription"] = posting.description
            merged["locationsText"] = posting.location
            merged["externalUrl"] = posting.source_url
            merged["jobReqId"] = posting.source_job_id
            return merged
        record_listing(
            company_config,
            identity=identity,
            fingerprint=fingerprint,
            reused=False,
        )

    detail_payload: object | None = None
    for attempt in range(WORKDAY_DETAIL_ATTEMPTS):
        try:
            response = requests.get(
                detail_url,
                headers=WORKDAY_HEADERS,
                timeout=30,
            )
            response.raise_for_status()
            detail_payload = response.json()
            break
        except (requests.RequestException, ValueError):
            # Workday detail edges can fail briefly while their search API is
            # still healthy. Retry each independent listing with a small
            # backoff, then preserve it as incomplete rather than inventing
            # qualification evidence.
            if attempt + 1 < WORKDAY_DETAIL_ATTEMPTS:
                time.sleep(WORKDAY_DETAIL_RETRY_SECONDS * (2**attempt))
            continue

    if not isinstance(detail_payload, dict):
        return raw_job
    return _merge_workday_detail(raw_job, detail_payload)


def _get_source_url(
    company_config: dict[str, Any],
    job: dict[str, Any],
) -> str | None:
    for field_name in ["externalUrl", "url"]:
        source_url = job.get(field_name)

        if source_url:
            return str(source_url)

    external_path = job.get("externalPath")
    source_base_url = company_config.get("source_base_url")

    if external_path and source_base_url:
        return str(source_base_url).rstrip("/") + "/" + str(external_path).lstrip("/")

    return None


def parse_workday_jobs(
    company_config: dict[str, Any],
    payload: dict[str, Any],
) -> list[JobPosting]:
    company_key = str(company_config["company_key"])
    company_name = str(company_config["name"])
    source_type = str(company_config["source_type"])

    raw_jobs = payload.get("jobPostings")

    if not isinstance(raw_jobs, list):
        raise CollectorError("Workday payload does not contain a jobPostings list")

    postings: list[JobPosting] = []

    for raw_job in raw_jobs:
        if not isinstance(raw_job, dict):
            continue

        title = _get_title(raw_job)
        source_url = _get_source_url(company_config, raw_job)

        if not title or not source_url:
            continue

        location = _get_location(raw_job)
        description = _get_description(raw_job)
        source_job_id = _get_job_id(raw_job)

        canonical_key = make_canonical_key(
            company_key=company_key,
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
                company_key=company_key,
                company_name=company_name,
                source_type=source_type,
                source_job_id=source_job_id,
                source_url=source_url,
                title=title,
                location=location,
                description=description,
                canonical_key=canonical_key,
                content_hash=content_hash,
                detail_retrieval_reason=raw_job.get(
                    "_junior_detail_retrieval_reason"
                ),
                detail_retrieval_state=(
                    "skipped_unrelated"
                    if raw_job.get("_junior_detail_retrieval_reason")
                    else None
                ),
            )
        )

    return postings


def collect_workday_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    source_url = company_config.get("source_url")

    if not source_url:
        raise CollectorError(
            f"Workday company {company_config.get('company_key')} is missing source_url"
        )

    limit = get_page_size(
        company_config,
        default=DEFAULT_WORKDAY_LIMIT,
    )
    max_pages = get_max_pages(
        company_config,
        default=DEFAULT_WORKDAY_MAX_PAGES,
    )
    offset = 0
    expected_total: int | None = None
    seen_page_job_ids: set[tuple[str | None, str]] = set()
    postings: list[JobPosting] = []

    for _page_index in range(max_pages):
        payload = _build_workday_payload(offset=offset, limit=limit)
        response_payload = _fetch_workday_page(
            str(source_url),
            payload=payload,
        )

        total = response_payload.get("total")
        raw_jobs = response_payload.get("jobPostings")

        if not isinstance(raw_jobs, list):
            raise CollectorError("Workday payload does not contain a jobPostings list")

        raw_job_dicts = [job for job in raw_jobs if isinstance(job, dict)]
        # Four workers substantially reduce large Workday feeds without
        # creating an unbounded burst against an employer's public service.
        with ThreadPoolExecutor(
            max_workers=min(4, max(1, len(raw_job_dicts)))
        ) as executor:
            enriched_dicts = list(
                executor.map(
                    lambda job: _fetch_workday_detail(
                        str(source_url),
                        job,
                        company_config,
                    ),
                    raw_job_dicts,
                )
            )
        enriched_jobs = iter(enriched_dicts)
        enriched_jobs = [
            next(enriched_jobs) if isinstance(raw_job, dict) else raw_job
            for raw_job in raw_jobs
        ]
        enriched_payload = dict(response_payload)
        enriched_payload["jobPostings"] = enriched_jobs
        page_postings = parse_workday_jobs(company_config, enriched_payload)
        page_identity = {
            (posting.source_job_id, posting.source_url) for posting in page_postings
        }

        # Some Workday tenants report the correct total only on the first page
        # and then return zero on later pages. Preserve the largest credible
        # positive total instead of treating a later zero as end-of-results.
        if isinstance(total, int) and total > 0:
            expected_total = max(expected_total or 0, total)

        # A misbehaving endpoint can ignore the requested offset and repeat the
        # same page forever. Stop safely rather than duplicating jobs until the
        # configured page limit is reached.
        if page_identity and page_identity.issubset(seen_page_job_ids):
            break

        postings.extend(page_postings)
        seen_page_job_ids.update(page_identity)
        offset += limit

        if not raw_jobs:
            break

        if expected_total is not None and offset >= expected_total:
            break

        if len(raw_jobs) < limit:
            break

    return postings
