from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_USER_AGENT = "JobRadar/0.1 local career-source scanner"

def _clean_title(value: str) -> str:
    title = " ".join(value.split()).strip()

    # iCIMS link titles often look like:
    # "168148 - Data Science, Advisor"
    if " - " in title:
        prefix, suffix = title.split(" - ", 1)
        if prefix.strip().isdigit() and suffix.strip():
            return suffix.strip()

    return title


class ICIMSJobLinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self._current_href: str | None = None
        self._current_title_attr: str | None = None
        self._current_text_parts: list[str] = []
        self.job_links: list[tuple[str, str]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() != "a":
            return

        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if not href:
            return

        if "/jobs/" not in href:
            return

        # iCIMS has non-job links under /jobs/intro, /jobs/search, and /jobs/login.
        if (
            "/jobs/intro" in href
            or "/jobs/search" in href
            or "/jobs/login" in href
        ):
            return

        self._current_href = href
        self._current_title_attr = attrs_dict.get("title")
        self._current_text_parts = []

    def handle_data(self, data: str) -> None:
        if self._current_href is None:
            return

        text = data.strip()
        if text:
            self._current_text_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a":
            return

        if self._current_href is None:
            return

        raw_title = self._current_title_attr or " ".join(self._current_text_parts)
        title = _clean_title(raw_title)
        href = self._current_href

        self._current_href = None
        self._current_title_attr = None
        self._current_text_parts = []

        if not title:
            return

        absolute_url = urljoin(self.base_url, href)
        self.job_links.append((title, absolute_url))


def _build_search_url(source_url: str) -> str:
    parsed = urlparse(source_url)

    if "/jobs/search" in parsed.path:
        search_url = source_url
    else:
        base = source_url.rstrip("/")
        if base.endswith("/jobs"):
            search_url = f"{base}/search?ss=1&searchRelation=keyword_all"
        else:
            search_url = f"{base}/jobs/search?ss=1&searchRelation=keyword_all"

    parsed_search_url = urlparse(search_url)
    query_params = dict(parse_qsl(parsed_search_url.query, keep_blank_values=True))
    query_params["in_iframe"] = "1"

    return urlunparse(
        (
            parsed_search_url.scheme,
            parsed_search_url.netloc,
            parsed_search_url.path,
            parsed_search_url.params,
            urlencode(query_params),
            parsed_search_url.fragment,
        )
    )


def _build_headers() -> dict[str, str]:
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "User-Agent": DEFAULT_USER_AGENT,
    }


def _extract_source_job_id(source_url: str) -> str | None:
    parsed = urlparse(source_url)
    parts = [part for part in parsed.path.split("/") if part]

    try:
        jobs_index = parts.index("jobs")
    except ValueError:
        return None

    if jobs_index + 1 >= len(parts):
        return None

    candidate = parts[jobs_index + 1].strip()
    return candidate or None


def _dedupe_links(links: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    deduped: list[tuple[str, str]] = []

    for title, url in links:
        if url in seen:
            continue
        seen.add(url)
        deduped.append((title, url))

    return deduped


def _parse_icims_html(
    company_config: dict[str, Any],
    html: str,
    search_url: str,
) -> list[JobPosting]:
    parser = ICIMSJobLinkParser(base_url=search_url)
    parser.feed(html)

    postings: list[JobPosting] = []

    for title, source_url in _dedupe_links(parser.job_links):
        source_job_id = _extract_source_job_id(source_url)
        location = None
        description = None

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
                source_url=source_url,
                title=title,
                location=location,
                description=description,
                canonical_key=canonical_key,
                content_hash=content_hash,
            )
        )

    return postings


def collect_icims_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    source_url = str(company_config["source_url"])
    search_url = _build_search_url(source_url)

    try:
        response = requests.get(
            search_url,
            headers=_build_headers(),
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.HTTPError as error:
        response_body = response.text[:500].replace("\n", " ")
        raise CollectorError(
            f"Failed to fetch iCIMS postings: {error}; "
            f"response_body={response_body}"
        ) from error
    except requests.RequestException as error:
        raise CollectorError(f"Failed to fetch iCIMS postings: {error}") from error

    return _parse_icims_html(company_config, response.text, search_url)