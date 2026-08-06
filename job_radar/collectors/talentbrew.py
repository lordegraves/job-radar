"""Collect all discoverable pages from TalentBrew career searches."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.html import collect_html_jobs_page
from job_radar.collectors.pagination import get_positive_int
from job_radar.models import JobPosting


DEFAULT_MAX_PAGES = 250
ABSOLUTE_TALENTBREW_MAX_PAGES = 250


def collect_talentbrew_jobs(
    company_config: dict[str, Any],
) -> list[JobPosting]:
    """Follow TalentBrew's ``p`` query until listings stop changing."""

    source_url = str(company_config["source_url"])
    max_pages = get_positive_int(
        company_config,
        key="max_pages",
        default=DEFAULT_MAX_PAGES,
        maximum=ABSOLUTE_TALENTBREW_MAX_PAGES,
    )
    postings: list[JobPosting] = []
    seen_jobs: set[str] = set()

    for page_number in range(1, max_pages + 1):
        page_url = _build_page_url(source_url, page_number)
        try:
            page_postings = collect_html_jobs_page(company_config, page_url)
        except CollectorError as error:
            if page_number == 1:
                raise
            raise CollectorError(
                "TalentBrew failed while reading a later results page.",
                failure_stage="results_pagination_request",
            ) from error
        new_postings = 0

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
            new_postings += 1

        # An empty page is the normal end. A page containing only jobs already
        # seen means the site ignored or redirected the page query. Both rules
        # prevent an unbounded crawl without assuming a fixed page size.
        if not page_postings or not new_postings:
            break

    return postings


def _build_page_url(source_url: str, page_number: int) -> str:
    """Preserve configured search filters while setting TalentBrew's page."""

    parsed = urlparse(source_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if page_number > 1:
        query["p"] = str(page_number)
    else:
        query.pop("p", None)
    return urlunparse(parsed._replace(query=urlencode(query)))
