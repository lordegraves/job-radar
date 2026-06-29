from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import urljoin

import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_USER_AGENT = "JobRadar/0.1 local career-source scanner"


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None

    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    text = " ".join(text.split())

    return text or None


def _get_timeout_seconds(company_config: dict[str, Any]) -> int:
    value = company_config.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)

    try:
        timeout = int(value)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS

    if timeout <= 0:
        return DEFAULT_TIMEOUT_SECONDS

    return timeout


def _fetch_careers_page(company_config: dict[str, Any]) -> tuple[str, str]:
    source_url = str(company_config["source_url"])

    try:
        response = requests.get(
            source_url,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "User-Agent": DEFAULT_USER_AGENT,
            },
            timeout=_get_timeout_seconds(company_config),
        )
        response.raise_for_status()
    except requests.HTTPError as error:
        response_body = response.text[:500].replace("\n", " ")
        raise CollectorError(
            f"Failed to fetch WEKA careers page: {error}; "
            f"response_body={response_body}"
        ) from error
    except requests.RequestException as error:
        raise CollectorError(f"Failed to fetch WEKA careers page: {error}") from error

    return response.text, response.url


def _parse_weka_jobs(
    company_config: dict[str, Any],
    html: str,
    source_url: str,
) -> list[JobPosting]:
    card_pattern = re.compile(
        r"<div\b"
        r'(?=[^>]*\bclass=["\'][^"\']*\bmrkto-job\b[^"\']*["\'])'
        r"(?P<attrs>[^>]*)>"
        r"(?P<body>.*?)"
        r'<div class="cta-box">',
        re.IGNORECASE | re.DOTALL,
    )

    postings: list[JobPosting] = []
    seen_ids: set[str] = set()

    for match in card_pattern.finditer(html):
        attrs = match.group("attrs")
        body = match.group("body")

        jid_match = re.search(
            r'href=["\']\?gh_jid=(?P<jid>\d+)["\']',
            body,
            re.IGNORECASE,
        )
        title_match = re.search(
            r"<h3>(?P<title>.*?)</h3>",
            body,
            re.IGNORECASE | re.DOTALL,
        )
        location_match = re.search(
            r'<div class="location">(?P<location>.*?)</div>',
            body,
            re.IGNORECASE | re.DOTALL,
        )
        department_match = re.search(
            r'data-departments=["\'](?P<department>[^"\']+)["\']',
            attrs,
            re.IGNORECASE,
        )

        if not jid_match or not title_match:
            continue

        source_job_id = jid_match.group("jid")
        title = _clean_text(title_match.group("title"))

        if not source_job_id or not title:
            continue

        if source_job_id in seen_ids:
            continue

        seen_ids.add(source_job_id)

        location = None
        if location_match:
            location = _clean_text(location_match.group("location"))

        department = None
        if department_match:
            department = _clean_text(department_match.group("department"))

        description = department
        source_url_for_job = urljoin(source_url, f"?gh_jid={source_job_id}#career-position")

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
                source_job_id=source_job_id,
                source_url=source_url_for_job,
                title=title,
                location=location,
                description=description,
                canonical_key=canonical_key,
                content_hash=content_hash,
            )
        )

    return postings


def collect_weka_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    html, final_url = _fetch_careers_page(company_config)

    return _parse_weka_jobs(
        company_config=company_config,
        html=html,
        source_url=final_url,
    )