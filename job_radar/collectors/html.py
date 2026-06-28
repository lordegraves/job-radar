from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_USER_AGENT = "JobRadar/0.1 local career-source scanner"


class HTMLJobLinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self._current_href: str | None = None
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

        class_value = attrs_dict.get("class") or ""
        classes = set(class_value.split())

        if "jobTitle-link" not in classes:
            return

        if "/job/" not in href:
            return

        self._current_href = href
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

        title = " ".join(self._current_text_parts).strip()
        href = self._current_href

        self._current_href = None
        self._current_text_parts = []

        if not title:
            return

        source_url = urljoin(self.base_url, href)
        self.job_links.append((unescape(title), source_url))


def _build_headers() -> dict[str, str]:
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "User-Agent": DEFAULT_USER_AGENT,
    }


def _extract_source_job_id(source_url: str) -> str | None:
    parsed = urlparse(source_url)
    parts = [part for part in parsed.path.split("/") if part]

    for part in reversed(parts):
        if part.isdigit():
            return part

    return None


def _extract_location_from_url(source_url: str) -> str | None:
    parsed = urlparse(source_url)
    parts = [part for part in parsed.path.split("/") if part]

    if len(parts) < 2:
        return None

    slug = parts[-2]
    slug_parts = [part for part in slug.split("-") if part]

    if len(slug_parts) < 4:
        return None

    state = slug_parts[-2]
    postal_code = slug_parts[-1]

    if not state.isalpha() or not postal_code.isdigit():
        return None

    # ORNL's SuccessFactors URLs begin with the city:
    # Oak-Ridge-IAM-Linux-Engineer-TN-37830
    if len(slug_parts) >= 2 and slug_parts[0:2] == ["Oak", "Ridge"]:
        return f"Oak Ridge, {state}"

    return None


def _dedupe_links(links: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen_urls: set[str] = set()
    deduped: list[tuple[str, str]] = []

    for title, source_url in links:
        if source_url in seen_urls:
            continue

        seen_urls.add(source_url)
        deduped.append((title, source_url))

    return deduped


def _parse_html_jobs(
    company_config: dict[str, Any],
    html: str,
    source_url: str,
) -> list[JobPosting]:
    parser = HTMLJobLinkParser(base_url=source_url)
    parser.feed(html)

    postings: list[JobPosting] = []

    for title, posting_url in _dedupe_links(parser.job_links):
        source_job_id = _extract_source_job_id(posting_url)
        location = _extract_location_from_url(posting_url)
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
                source_url=posting_url,
                title=title,
                location=location,
                description=description,
                canonical_key=canonical_key,
                content_hash=content_hash,
            )
        )

    return postings


def collect_html_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    source_url = str(company_config["source_url"])

    try:
        response = requests.get(
            source_url,
            headers=_build_headers(),
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.HTTPError as error:
        response_body = response.text[:500].replace("\n", " ")
        raise CollectorError(
            f"Failed to fetch HTML postings: {error}; "
            f"response_body={response_body}"
        ) from error
    except requests.RequestException as error:
        raise CollectorError(f"Failed to fetch HTML postings: {error}") from error

    return _parse_html_jobs(
        company_config=company_config,
        html=response.text,
        source_url=source_url,
    )