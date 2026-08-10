"""Collect jobs from career pages that expose ordinary HTML links."""

from __future__ import annotations

import re
import json

from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

from job_radar.collectors.collector_http import get_response
from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_USER_AGENT = "JobRadar/0.1 local career-source scanner"


def _get_timeout_seconds(company_config: dict[str, Any]) -> int:
    value = company_config.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)

    try:
        timeout = int(value)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS

    if timeout <= 0:
        return DEFAULT_TIMEOUT_SECONDS

    return timeout


class HTMLJobLinkParser(HTMLParser):
    def __init__(
        self,
        base_url: str,
        *,
        job_link_patterns: tuple[str, ...] = (),
    ) -> None:
        super().__init__()
        self.base_url = base_url
        self.job_link_patterns = job_link_patterns
        self._current_href: str | None = None
        self._current_text_parts: list[str] = []
        self._current_title_parts: list[str] = []
        self._title_depth = 0
        self.job_links: list[tuple[str, str]] = []
        self.structured_jobs: list[dict[str, Any]] = []
        self._in_job_json = False
        self._json_parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() == "script":
            attrs_dict = dict(attrs)
            if (attrs_dict.get("type") or "").casefold() == "application/ld+json":
                self._in_job_json = True
                self._json_parts = []
            return
        if tag.lower() in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            if self._current_href is not None:
                self._title_depth += 1
            return
        if tag.lower() != "a":
            return

        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if not href:
            return

        class_value = attrs_dict.get("class") or ""
        classes = set(class_value.split())
        element_id = attrs_dict.get("id") or ""

        supported_link_classes = {
            "js-view-job",
            "jobTitle-link",
            "results-list__item-title--link",
            "list-item__link",
        }

        has_supported_class = not classes.isdisjoint(supported_link_classes)
        has_supported_id = element_id.startswith("link_job_title_")
        has_job_identifier = bool(attrs_dict.get("data-job-id"))

        supported_path_parts = {
            "/job/",
            "/job-opening/",
            "/jobs/",
        }

        has_supported_pattern = any(
            pattern and pattern in href for pattern in self.job_link_patterns
        )
        if (
            not has_supported_class
            and not has_supported_id
            and not has_job_identifier
            and not has_supported_pattern
        ):
            return
        if not has_supported_pattern and not any(
            path_part in href for path_part in supported_path_parts
        ):
            return

        self._current_href = href
        self._current_text_parts = []
        self._current_title_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_job_json:
            self._json_parts.append(data)
            return
        if self._current_href is None:
            return

        text = data.strip()
        if text:
            self._current_text_parts.append(text)
            if self._title_depth:
                self._current_title_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._in_job_json:
            self._in_job_json = False
            try:
                payload = json.loads("".join(self._json_parts))
            except (TypeError, json.JSONDecodeError):
                return
            self.structured_jobs.extend(_find_job_postings(payload))
            return
        if tag.lower() in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            if self._title_depth:
                self._title_depth -= 1
            return
        if tag.lower() != "a":
            return

        if self._current_href is None:
            return

        title = " ".join(
            self._current_title_parts or self._current_text_parts
        ).strip()
        href = self._current_href

        self._current_href = None
        self._current_text_parts = []
        self._current_title_parts = []
        self._title_depth = 0

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
    query = parse_qs(parsed.query)
    query_job_id = query.get("job_id", [None])[0]
    if query_job_id and str(query_job_id).isdigit():
        return str(query_job_id)
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


def _clean_title_for_url(title: str, posting_url: str) -> str:
    normalized_title = " ".join(title.split())

    if "/job-opening/" not in posting_url:
        return normalized_title

    title_parts = re.split(
        r"\s+(?:MBARI|The|Located|Reporting|This|Applicants)\b",
        normalized_title,
        maxsplit=1,
    )

    cleaned_title = title_parts[0].strip()
    if cleaned_title:
        return cleaned_title

    return normalized_title


def _parse_html_jobs(
    company_config: dict[str, Any],
    html: str,
    source_url: str,
) -> list[JobPosting]:
    configured_patterns = company_config.get("job_link_patterns", ())
    patterns = (
        tuple(str(item) for item in configured_patterns if str(item))
        if isinstance(configured_patterns, (list, tuple))
        else ()
    )
    parser = HTMLJobLinkParser(
        base_url=source_url,
        job_link_patterns=patterns,
    )
    parser.feed(html)

    postings: list[JobPosting] = [
        posting
        for item in parser.structured_jobs
        if (posting := _structured_posting(company_config, item, source_url))
        is not None
    ]

    for title, posting_url in _dedupe_links(parser.job_links):
        source_job_id = _extract_source_job_id(posting_url)
        location = _extract_location_from_url(posting_url)
        title = _clean_title_for_url(title, posting_url)
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


def _find_job_postings(value: object) -> list[dict[str, Any]]:
    """Find schema.org JobPosting objects inside JSON-LD graphs and lists."""

    found: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            found.extend(_find_job_postings(item))
    elif isinstance(value, dict):
        item_type = value.get("@type")
        types = item_type if isinstance(item_type, list) else [item_type]
        if any(str(candidate).casefold() == "jobposting" for candidate in types):
            found.append(value)
        for key, item in value.items():
            if key != "@type":
                found.extend(_find_job_postings(item))
    return found


def _structured_posting(
    company_config: dict[str, Any],
    item: dict[str, Any],
    page_url: str,
) -> JobPosting | None:
    title = _plain_text(item.get("title"))
    if not title:
        return None
    posting_url = _plain_text(item.get("url")) or page_url
    identifier = item.get("identifier")
    source_job_id = (
        _plain_text(identifier.get("value"))
        if isinstance(identifier, dict)
        else _plain_text(identifier)
    )
    location = _structured_location(item.get("jobLocation"))
    description = _plain_text(item.get("description"))
    return JobPosting(
        company_key=str(company_config["company_key"]),
        company_name=str(company_config["name"]),
        source_type=str(company_config["source_type"]),
        source_job_id=source_job_id,
        source_url=urljoin(page_url, posting_url),
        title=title,
        location=location,
        description=description,
        canonical_key=make_canonical_key(
            str(company_config["company_key"]), title, location
        ),
        content_hash=make_content_hash(title, location, description),
    )


def _structured_location(value: object) -> str | None:
    locations = value if isinstance(value, list) else [value]
    labels: list[str] = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        address = location.get("address")
        if isinstance(address, str):
            label = _plain_text(address)
        elif isinstance(address, dict):
            label = ", ".join(
                part
                for key in (
                    "addressLocality",
                    "addressRegion",
                    "postalCode",
                    "addressCountry",
                )
                if (part := _plain_text(address.get(key)))
            )
        else:
            label = _plain_text(location.get("name"))
        if label and label not in labels:
            labels.append(label)
    return "; ".join(labels) or None


def _plain_text(value: object) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"<[^>]+>", " ", unescape(str(value)))
    collapsed = " ".join(cleaned.split())
    return collapsed or None


def collect_html_jobs_page(
    company_config: dict[str, Any],
    source_url: str,
) -> list[JobPosting]:
    """Fetch and parse one public HTML results page."""

    _html, postings = collect_html_jobs_document(company_config, source_url)
    return postings


def collect_html_jobs_document(
    company_config: dict[str, Any],
    source_url: str,
) -> tuple[str, list[JobPosting]]:
    """Fetch one page and retain its public platform markers for routing."""

    response = get_response(
        source_url,
        headers=_build_headers(),
        timeout=_get_timeout_seconds(company_config),
        error_type=CollectorError,
        request_error_message="Failed to fetch HTML postings",
        include_response_body=True,
    )

    return response.text, _parse_html_jobs(
        company_config=company_config,
        html=response.text,
        source_url=source_url,
    )


def collect_html_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    """Collect one results page for a generic public HTML source."""

    return collect_html_jobs_page(
        company_config,
        str(company_config["source_url"]),
    )
