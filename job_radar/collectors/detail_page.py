"""Enrich plausible summary-only listings from their public detail pages."""

from __future__ import annotations

from dataclasses import replace
from html.parser import HTMLParser
import json
import re
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

from job_radar.collectors.collector_http import get_response
from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import clean_human_text


DETAIL_PAGE_SOURCE_TYPES = {
    "activate",
    "adp",
    "html",
    "icims",
    "oracle_hcm",
    "rippling",
    "talentbrew",
    "weka",
}


class _DetailPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._ignored_depth = 0
        self._json_ld_depth = 0
        self._json_parts: list[str] = []
        self._text_parts: list[str] = []
        self.json_documents: list[object] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        lowered = tag.casefold()
        if lowered in {"script", "style", "svg", "noscript"}:
            if lowered == "script" and "ld+json" in (
                dict(attrs).get("type") or ""
            ).casefold():
                self._json_ld_depth += 1
            else:
                self._ignored_depth += 1
            return
        if lowered in {"br", "div", "h1", "h2", "h3", "li", "p", "section"}:
            self._text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered == "script" and self._json_ld_depth:
            self._json_ld_depth -= 1
            raw = "".join(self._json_parts).strip()
            self._json_parts = []
            if raw:
                try:
                    self.json_documents.append(json.loads(raw))
                except json.JSONDecodeError:
                    pass
        elif lowered in {"script", "style", "svg", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._json_ld_depth:
            self._json_parts.append(data)
        elif not self._ignored_depth:
            self._text_parts.append(data)

    @property
    def visible_text(self) -> str | None:
        return clean_human_text("".join(self._text_parts)) or None


class _ExactTitleLinkParser(HTMLParser):
    """Find same-host detail links whose visible text is one exact job title."""

    def __init__(self, *, base_url: str, title: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.expected_title = _normalized_title(title)
        self._href: str | None = None
        self._parts: list[str] = []
        self.matches: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.casefold() != "a":
            return
        self._href = dict(attrs).get("href")
        self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "a" or self._href is None:
            return
        candidate = urljoin(self.base_url, self._href)
        base = urlparse(self.base_url)
        parsed = urlparse(candidate)
        if (
            parsed.scheme in {"http", "https"}
            and parsed.netloc.casefold() == base.netloc.casefold()
            and _normalized_title(" ".join(self._parts)) == self.expected_title
            and candidate not in self.matches
        ):
            self.matches.append(candidate)
        self._href = None
        self._parts = []


def enrich_from_public_detail_page(
    posting: JobPosting,
    *,
    source_api_url: str | None = None,
) -> JobPosting:
    """Return a richer posting without failing the company's whole listing."""

    if posting.source_type == "oracle_hcm":
        # Oracle's public page is a JavaScript shell. Retrying that HTML after
        # the structured endpoint fails adds delay without adding job content.
        return _enrich_from_oracle_detail(
            posting,
            source_api_url=source_api_url,
        )
    if posting.source_type == "adp":
        return _enrich_from_adp_detail(posting)

    response = _fetch_public_detail_response(
        posting,
        source_index_url=source_api_url,
    )
    if response is None:
        return replace(posting, detail_retrieval_state="unavailable")

    parser = _DetailPageParser()
    parser.feed(response.text)
    structured = next(
        (
            item
            for document in parser.json_documents
            for item in _find_job_postings(document)
        ),
        None,
    )
    description = None
    location = posting.location
    remote_status = posting.remote_status
    salary_text = posting.salary_text
    if structured is not None:
        description = clean_human_text(str(structured.get("description") or "")) or None
        location = _structured_location(structured.get("jobLocation")) or location
        remote_status = (
            clean_human_text(str(structured.get("jobLocationType") or ""))
            or remote_status
        )
        salary_text = _structured_salary(structured.get("baseSalary")) or salary_text
    description = description or parser.visible_text
    return replace(
        posting,
        location=location,
        description=description,
        remote_status=remote_status,
        salary_text=salary_text,
        detail_retrieval_state=(
            None if description and len(description) >= 200 else "unavailable"
        ),
    )


def _fetch_public_detail_response(
    posting: JobPosting,
    *,
    source_index_url: str | None,
) -> Any | None:
    headers = {
        "Accept": "text/html,application/xhtml+xml",
        "User-Agent": "JobRadar/0.1 local career-source scanner",
    }
    try:
        return get_response(
            posting.source_url,
            headers=headers,
            timeout=20,
            error_type=CollectorError,
            request_error_message="Failed to fetch public job detail",
            include_response_body=True,
        )
    except CollectorError:
        pass
    if not source_index_url:
        return None
    try:
        index_response = get_response(
            source_index_url,
            headers=headers,
            timeout=15,
            error_type=CollectorError,
            request_error_message="Failed to refresh public job index",
            include_response_body=True,
        )
    except CollectorError:
        return None
    parser = _ExactTitleLinkParser(
        base_url=source_index_url,
        title=posting.title,
    )
    parser.feed(index_response.text)
    replacement_urls = [
        url for url in parser.matches if url != posting.source_url
    ]
    if len(replacement_urls) != 1:
        # Ambiguous duplicate titles are safer to leave incomplete than to join
        # the wrong description to a listing.
        return None
    try:
        return get_response(
            replacement_urls[0],
            headers=headers,
            timeout=20,
            error_type=CollectorError,
            request_error_message="Failed to fetch refreshed public job detail",
            include_response_body=True,
        )
    except CollectorError:
        return None


def _normalized_title(value: str) -> str:
    return clean_human_text(re.sub(r"\s+", " ", value)).casefold()


def _enrich_from_oracle_detail(
    posting: JobPosting,
    *,
    source_api_url: str | None = None,
) -> JobPosting:
    """Use Oracle's structured Candidate Experience detail resource."""

    if not posting.source_job_id:
        return replace(posting, detail_retrieval_state="unavailable")
    parsed = urlparse(source_api_url or posting.source_url)
    if not parsed.scheme or not parsed.netloc:
        return replace(posting, detail_retrieval_state="unavailable")
    detail_url = (
        f"{parsed.scheme}://{parsed.netloc}/hcmRestApi/resources/latest/"
        f"recruitingCEJobRequisitionDetails/{posting.source_job_id}"
    )
    try:
        response = get_response(
            detail_url,
            params={
                "onlyData": "true",
                "expand": (
                    "workLocation,otherWorkLocations,secondaryLocations,"
                    "requisitionFlexFields,skills"
                ),
            },
            headers={
                "Accept": "application/json, text/plain, */*",
                "Referer": posting.source_url,
                "User-Agent": "JobRadar/0.1 local career-source scanner",
            },
            timeout=30,
            error_type=CollectorError,
            request_error_message="Failed to fetch Oracle job detail",
        )
        payload = response.json()
    except (CollectorError, ValueError):
        return replace(posting, detail_retrieval_state="unavailable")
    if not isinstance(payload, dict):
        return replace(posting, detail_retrieval_state="unavailable")
    detail = payload
    items = payload.get("items")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        detail = items[0]
    description_parts = [
        clean_human_text(str(detail.get(field) or ""))
        for field in (
            "ShortDescriptionStr",
            "ExternalShortDescriptionStr",
            "ExternalDescriptionStr",
            "ExternalResponsibilitiesStr",
            "ExternalQualificationsStr",
            "CorporateDescriptionStr",
            "OrganizationDescriptionStr",
        )
    ]
    description = "\n\n".join(part for part in description_parts if part)
    employment_facts = [
        clean_human_text(str(detail.get(field) or ""))
        for field in ("JobType", "JobSchedule", "WorkerType", "ContractType")
    ]
    employment_facts = [part for part in employment_facts if part]
    if employment_facts:
        description = "\n\n".join(
            part
            for part in (
                description,
                "Employment details: "
                + "; ".join(part for part in employment_facts if part),
            )
            if part
        )
    location = _oracle_location(detail) or posting.location
    remote_status = (
        clean_human_text(str(detail.get("WorkplaceType") or ""))
        or posting.remote_status
    )
    if len(description) < 200:
        return replace(
            posting,
            location=location,
            remote_status=remote_status,
            detail_retrieval_state="unavailable",
        )
    return replace(
        posting,
        description=description,
        location=location,
        remote_status=remote_status,
        detail_retrieval_state=None,
    )


def _oracle_location(detail: dict[str, Any]) -> str | None:
    labels: list[str] = []
    primary = clean_human_text(str(detail.get("PrimaryLocation") or ""))
    if primary:
        labels.append(primary)
    for field in ("workLocation", "otherWorkLocations", "secondaryLocations"):
        values = detail.get(field)
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, dict):
                continue
            label = clean_human_text(
                str(value.get("Name") or value.get("LocationName") or "")
            )
            if label and label not in labels:
                labels.append(label)
    return "; ".join(labels) or None


def _enrich_from_adp_detail(posting: JobPosting) -> JobPosting:
    """Read the public ADP requisition resource used by its career UI."""

    if not posting.source_job_id:
        return replace(posting, detail_retrieval_state="unavailable")
    parsed = urlparse(posting.source_url)
    query = parse_qs(parsed.query)
    cid = _first_query_value(query, "cid")
    cc_id = _first_query_value(query, "ccId")
    locale = _first_query_value(query, "lang") or "en_US"
    if not parsed.scheme or not parsed.netloc or not cid or not cc_id:
        return replace(posting, detail_retrieval_state="unavailable")
    detail_url = (
        f"{parsed.scheme}://{parsed.netloc}/mascsr/default/careercenter/public/"
        f"events/staffing/v1/job-requisitions/{posting.source_job_id}"
    )
    try:
        response = get_response(
            detail_url,
            params={
                "cid": cid,
                "ccId": cc_id,
                "lang": locale,
                "locale": locale,
            },
            headers={
                "Accept": "application/json, text/plain, */*",
                "Referer": posting.source_url,
                "User-Agent": "JobRadar/0.1 local career-source scanner",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=30,
            error_type=CollectorError,
            request_error_message="Failed to fetch ADP job detail",
        )
        payload = response.json()
    except (CollectorError, ValueError):
        return replace(posting, detail_retrieval_state="unavailable")
    if not isinstance(payload, dict):
        return replace(posting, detail_retrieval_state="unavailable")
    description = clean_human_text(
        str(payload.get("requisitionDescription") or "")
    )
    if not description or len(description) < 200:
        return replace(posting, detail_retrieval_state="unavailable")
    return replace(
        posting,
        description=description,
        detail_retrieval_state=None,
    )


def _first_query_value(query: dict[str, list[str]], name: str) -> str | None:
    values = query.get(name)
    return values[0] if values else None


def _find_job_postings(value: object) -> list[dict[str, Any]]:
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


def _structured_location(value: object) -> str | None:
    values = value if isinstance(value, list) else [value]
    labels: list[str] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        address = item.get("address")
        if isinstance(address, dict):
            label = ", ".join(
                clean_human_text(str(address.get(key) or ""))
                for key in (
                    "addressLocality",
                    "addressRegion",
                    "addressCountry",
                )
                if address.get(key)
            )
        else:
            label = clean_human_text(str(address or item.get("name") or ""))
        if label and label not in labels:
            labels.append(label)
    return "; ".join(labels) or None


def _structured_salary(value: object) -> str | None:
    if not isinstance(value, dict):
        return clean_human_text(str(value or "")) or None
    currency = clean_human_text(str(value.get("currency") or ""))
    amount = value.get("value")
    if isinstance(amount, dict):
        minimum = amount.get("minValue")
        maximum = amount.get("maxValue")
        unit = amount.get("unitText")
        if minimum is not None and maximum is not None:
            return clean_human_text(
                f"{currency} {minimum} - {maximum} {unit or ''}"
            )
    return None
