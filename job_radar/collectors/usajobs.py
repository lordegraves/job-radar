from __future__ import annotations

import os
from typing import Any

import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


USAJOBS_SEARCH_URL = "https://data.usajobs.gov/api/Search"
DEFAULT_RESULTS_PER_PAGE = 100
MAX_PAGES = 5


def _get_required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise CollectorError(f"Missing required environment variable: {name}")
    return value


def _build_headers() -> dict[str, str]:
    return {
        "Host": "data.usajobs.gov",
        "User-Agent": _get_required_env("USAJOBS_USER_AGENT"),
        "Authorization-Key": _get_required_env("USAJOBS_AUTHORIZATION_KEY"),
    }


def _build_params(company_config: dict[str, Any], page: int) -> dict[str, str | int]:
    params: dict[str, str | int] = {
        "Page": page,
        "ResultsPerPage": DEFAULT_RESULTS_PER_PAGE,
    }

    extra_params = company_config.get("query_params", {})
    if isinstance(extra_params, dict):
        for key, value in extra_params.items():
            if value is not None and value != "":
                params[str(key)] = str(value)

    return params


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _get_position_location(matched_object_descriptor: dict[str, Any]) -> str:
    locations = matched_object_descriptor.get("PositionLocation") or []
    if not isinstance(locations, list):
        return ""

    names = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        name = location.get("LocationName")
        if name:
            names.append(str(name))

    return "; ".join(names)


def _get_description(matched_object_descriptor: dict[str, Any]) -> str:
    parts = []

    for key in (
        "QualificationSummary",
        "MajorDuties",
        "Requirements",
        "Evaluations",
    ):
        value = matched_object_descriptor.get(key)
        if value:
            parts.append(_as_text(value))

    user_area = matched_object_descriptor.get("UserArea")
    if isinstance(user_area, dict):
        details = user_area.get("Details")
        if isinstance(details, dict):
            for key in (
                "JobSummary",
                "WhoMayApply",
                "LowGrade",
                "HighGrade",
                "PromotionPotential",
                "HiringPath",
                "TotalOpenings",
                "AgencyMarketingStatement",
                "TravelCode",
                "SecurityClearance",
                "DrugTestRequired",
                "PositionSensitivitiy",
            ):
                value = details.get(key)
                if value:
                    parts.append(f"{key}: {_as_text(value)}")

    return "\n\n".join(parts)


def _parse_search_items(
    company_config: dict[str, Any],
    payload: dict[str, Any],
) -> list[JobPosting]:
    search_result = payload.get("SearchResult")
    if not isinstance(search_result, dict):
        raise CollectorError("USAJobs response missing SearchResult")

    items = search_result.get("SearchResultItems") or []
    if not isinstance(items, list):
        raise CollectorError("USAJobs response SearchResultItems is not a list")

    postings: list[JobPosting] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        descriptor = item.get("MatchedObjectDescriptor")
        if not isinstance(descriptor, dict):
            continue

        position_id = _as_text(descriptor.get("PositionID")).strip()
        title = _as_text(descriptor.get("PositionTitle")).strip()
        url = _as_text(descriptor.get("PositionURI")).strip()
        location = _get_position_location(descriptor)
        description = _get_description(descriptor)

        if not position_id or not title or not url:
            continue

        canonical_key = make_canonical_key(
            company_key=str(company_config["company_key"]),
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
                company_key=str(company_config["company_key"]),
                company_name=str(company_config["name"]),
                source_type=str(company_config["source_type"]),
                source_job_id=position_id,
                source_url=url,
                title=title,
                location=location,
                description=description,
                canonical_key=canonical_key,
                content_hash=content_hash,
            )
        )

    return postings


def _get_total_pages(payload: dict[str, Any]) -> int:
    search_result = payload.get("SearchResult")
    if not isinstance(search_result, dict):
        return 1

    user_area = search_result.get("UserArea")
    if not isinstance(user_area, dict):
        return 1

    number_of_pages = user_area.get("NumberOfPages")
    try:
        return int(number_of_pages)
    except (TypeError, ValueError):
        return 1


def collect_usajobs(company_config: dict[str, Any]) -> list[JobPosting]:
    headers = _build_headers()
    postings: list[JobPosting] = []

    for page in range(1, MAX_PAGES + 1):
        params = _build_params(company_config, page)

        try:
            response = requests.get(
                USAJOBS_SEARCH_URL,
                headers=headers,
                params=params,
                timeout=30,
            )
            response.raise_for_status()
        except requests.HTTPError as error:
            response_body = response.text[:500].replace("\n", " ")
            raise CollectorError(
                f"Failed to fetch USAJobs postings: {error}; "
                f"response_body={response_body}"
            ) from error
        except requests.RequestException as error:
            raise CollectorError(f"Failed to fetch USAJobs postings: {error}") from error

        payload = response.json()
        postings.extend(_parse_search_items(company_config, payload))

        if page >= _get_total_pages(payload):
            break

    return postings