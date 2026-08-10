"""Add bounded platform pagination to older generic HTML configurations."""

from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.html import (
    collect_html_jobs_document,
)
from job_radar.collectors.pagination import get_positive_int
from job_radar.collectors.talentbrew import collect_talentbrew_jobs
from job_radar.models import JobPosting


DEFAULT_MAX_PAGES = 250
ABSOLUTE_HTML_MAX_PAGES = 250


def collect_adaptive_html_jobs(
    company_config: dict[str, Any],
) -> list[JobPosting]:
    """Detect pagination from public page markers without rewriting user data."""

    source_url = str(company_config["source_url"])
    html, first_page = collect_html_jobs_document(company_config, source_url)
    lowered = html.casefold()
    if "talentbrew" in lowered or "tbcdn." in lowered:
        # The TalentBrew parser knows its job-card markup. Generic HTML may
        # detect the platform while finding no jobs, so hand the source to the
        # platform collector before deciding that the page is empty.
        return collect_talentbrew_jobs(company_config)
    if "successfactors" in lowered:
        return _collect_successfactors_pages(
            company_config,
            first_html=html,
            first_page=first_page,
        )
    return _collect_numbered_pages(
        company_config,
        first_html=html,
        first_page=first_page,
    )


def _collect_numbered_pages(
    company_config: dict[str, Any],
    *,
    first_html: str,
    first_page: list[JobPosting],
) -> list[JobPosting]:
    """Follow explicit same-site page links on generic career sites."""

    source_url = str(company_config["source_url"])
    max_pages = get_positive_int(
        company_config,
        key="max_pages",
        default=DEFAULT_MAX_PAGES,
        maximum=ABSOLUTE_HTML_MAX_PAGES,
    )
    postings: list[JobPosting] = []
    seen_jobs: set[str] = set()
    seen_pages = {source_url}
    current_url = source_url
    current_html = first_html
    page_postings = first_page

    for page_number in range(1, max_pages + 1):
        new_postings = _append_new(postings, seen_jobs, page_postings)
        if not page_postings or not new_postings or page_number >= max_pages:
            break
        next_url = _next_numbered_page_url(current_html, current_url, seen_pages)
        if next_url is None:
            break
        seen_pages.add(next_url)
        try:
            current_html, page_postings = collect_html_jobs_document(
                company_config,
                next_url,
            )
        except CollectorError as error:
            raise CollectorError(
                "The public career site failed while reading a later results page.",
                failure_stage="results_pagination_request",
            ) from error
        current_url = next_url

    return postings


def _next_numbered_page_url(
    html: str,
    current_url: str,
    seen_pages: set[str],
) -> str | None:
    """Return the lowest later page number advertised on the current page."""

    parsed_current = urlparse(current_url)
    current_values = parse_qs(parsed_current.query).get("page", ["1"])
    try:
        current_page = int(current_values[0])
    except (TypeError, ValueError):
        current_page = 1

    candidates: list[tuple[int, str]] = []
    for href in re.findall(r"href\s*=\s*['\"]([^'\"]+)['\"]", html, re.IGNORECASE):
        absolute = urljoin(current_url, unescape(href))
        parsed = urlparse(absolute)
        if parsed.netloc.casefold() != parsed_current.netloc.casefold():
            continue
        values = parse_qs(parsed.query).get("page")
        if not values:
            continue
        try:
            page = int(values[0])
        except (TypeError, ValueError):
            continue
        normalized = parsed._replace(fragment="").geturl()
        if page > current_page and normalized not in seen_pages:
            candidates.append((page, normalized))
    return min(candidates, default=(0, None), key=lambda item: item[0])[1]


def _collect_successfactors_pages(
    company_config: dict[str, Any],
    *,
    first_html: str,
    first_page: list[JobPosting],
) -> list[JobPosting]:
    """Follow the page links supplied by each SuccessFactors tenant.

    SuccessFactors sites do not share one page size. Following the employer's
    own next offset avoids skipping jobs or rereading the first page.
    """

    source_url = str(company_config["source_url"])
    max_pages = get_positive_int(
        company_config,
        key="max_pages",
        default=DEFAULT_MAX_PAGES,
        maximum=ABSOLUTE_HTML_MAX_PAGES,
    )
    postings: list[JobPosting] = []
    seen_jobs: set[str] = set()
    current_url = source_url
    current_html = first_html
    page_postings = first_page

    for page_number in range(1, max_pages + 1):
        new_postings = _append_new(postings, seen_jobs, page_postings)
        if not page_postings or not new_postings or page_number >= max_pages:
            break

        next_url = _next_successfactors_url(current_html, current_url)
        if next_url is None:
            break
        try:
            current_html, page_postings = collect_html_jobs_document(
                company_config,
                next_url,
            )
        except CollectorError as error:
            raise CollectorError(
                "The public career site failed while reading a later results page.",
                failure_stage="results_pagination_request",
            ) from error
        current_url = next_url

    return postings


def _next_successfactors_url(html: str, current_url: str) -> str | None:
    current_values = parse_qs(urlparse(current_url).query).get("startrow", ["0"])
    try:
        current_offset = int(current_values[0])
    except (TypeError, ValueError):
        current_offset = 0

    candidates: list[tuple[int, str]] = []
    for href in re.findall(r"href\s*=\s*['\"]([^'\"]+)['\"]", html, re.IGNORECASE):
        decoded = unescape(href)
        absolute = urljoin(current_url, decoded)
        values = parse_qs(urlparse(absolute).query).get("startrow")
        if not values:
            continue
        try:
            offset = int(values[0])
        except (TypeError, ValueError):
            continue
        if offset > current_offset:
            candidates.append((offset, absolute))

    return min(candidates, default=(0, None), key=lambda item: item[0])[1]


def _append_new(
    postings: list[JobPosting],
    seen_jobs: set[str],
    page_postings: list[JobPosting],
) -> int:
    added = 0
    for posting in page_postings:
        identity = (
            posting.source_job_id
            or posting.source_url
            or posting.canonical_key
            or posting.job_radar_id
        )
        if identity in seen_jobs:
            continue
        seen_jobs.add(identity)
        postings.append(posting)
        added += 1
    return added
