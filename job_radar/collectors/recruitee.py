"""Collect published jobs from Recruitee's unauthenticated Careers Site API."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from job_radar.collectors.collector_http import get_json
from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


def collect_recruitee_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    """Collect one employer's published Recruitee offers."""

    source_url = str(company_config["source_url"])
    payload = get_json(
        source_url,
        timeout=30,
        error_type=CollectorError,
        request_error_message="Recruitee request failed",
        expected_type=dict,
        response_type_error_message="Recruitee returned an unexpected response",
        invalid_json_error_message="Recruitee returned unreadable job data",
        headers={"Accept": "application/json"},
    )
    offers = payload.get("offers", [])
    if not isinstance(offers, list):
        raise CollectorError("Recruitee returned an unexpected offers list")

    postings: list[JobPosting] = []
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        title = _text(offer.get("title"))
        if not title:
            continue
        source_job_id = _text(offer.get("id"))
        source_job_url = (
            _text(offer.get("careers_url"))
            or _text(offer.get("url"))
            or urljoin(source_url, f"offers/{source_job_id or ''}")
        )
        location = _location(offer)
        description = _text(
            offer.get("description")
            or offer.get("description_html")
            or offer.get("requirements")
        )
        postings.append(
            JobPosting(
                company_key=str(company_config["company_key"]),
                company_name=str(company_config["name"]),
                source_type="recruitee",
                source_job_id=source_job_id,
                source_url=source_job_url,
                title=title,
                location=location,
                description=description,
                canonical_key=make_canonical_key(
                    str(company_config["company_key"]), title, location
                ),
                content_hash=make_content_hash(title, location, description),
            )
        )
    return postings


def _location(offer: dict[str, Any]) -> str | None:
    location = offer.get("location")
    if isinstance(location, str):
        return _text(location)
    if isinstance(location, dict):
        return _text(location.get("name") or location.get("city"))
    locations = offer.get("locations")
    if isinstance(locations, list):
        names = [
            value
            for item in locations
            if isinstance(item, dict)
            if (value := _text(item.get("name") or item.get("city")))
        ]
        return ", ".join(names) or None
    return None


def _text(value: object) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None
