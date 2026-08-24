"""Collect public jobs from Avature career-portal RSS feeds."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree

import requests

from job_radar.collectors.collector_http import get_response
from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash

DEFAULT_TIMEOUT_SECONDS = 30


def collect_avature_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    """Read the tenant's official feed without requiring an interactive session."""

    source_url = str(company_config["source_url"])
    try:
        response = get_response(
            source_url,
            timeout=int(company_config.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)),
            headers={
                "Accept": "application/rss+xml, application/xml, text/xml",
                "User-Agent": "JobRadar/0.1 local career-source scanner",
            },
        )
    except requests.RequestException as error:
        raise CollectorError(
            "The public Avature job feed could not be reached.",
            failure_stage="listing_request",
        ) from error

    try:
        root = ElementTree.fromstring(response.content)
    except ElementTree.ParseError as error:
        raise CollectorError(
            "The public Avature job feed returned invalid XML.",
            failure_stage="listing_response",
        ) from error

    postings: list[JobPosting] = []
    seen: set[str] = set()
    for item in root.findall("./channel/item"):
        title = _text(item.findtext("title"))
        posting_url = _text(item.findtext("link")) or _text(item.findtext("guid"))
        if not title or not posting_url or posting_url in seen:
            continue
        seen.add(posting_url)
        source_job_id = _source_job_id(posting_url)
        description = _text(item.findtext("description"))
        postings.append(
            JobPosting(
                company_key=str(company_config["company_key"]),
                company_name=str(company_config["name"]),
                source_type="avature",
                source_url=posting_url,
                title=title,
                location=None,
                description=description,
                source_job_id=source_job_id,
                canonical_key=make_canonical_key(
                    str(company_config["company_key"]), title, None
                ),
                content_hash=make_content_hash(title, None, description),
                detail_retrieval_state="summary_only",
            )
        )
    return postings


def _source_job_id(url: str) -> str | None:
    parts = [part for part in urlparse(url).path.split("/") if part]
    return next((part for part in reversed(parts) if part.isdigit()), None)


def _text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(re.sub(r"<[^>]+>", " ", value).split())
    return cleaned or None
