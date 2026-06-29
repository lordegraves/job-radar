from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


DEFAULT_PAGE_SIZE = 20
DEFAULT_MAX_PAGES = 10
DEFAULT_LOCALE = "en_US"

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0"
)


def collect_adp_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    company_key = str(company_config["company_key"])
    company_name = str(company_config["name"])
    source_url = str(company_config["source_url"])

    cid = _config_or_query_value(company_config, source_url, "cid")
    cc_id = _config_or_query_value(company_config, source_url, "ccId")
    client = str(company_config.get("client", ""))
    locale = str(company_config.get("locale", DEFAULT_LOCALE))
    page_size = int(company_config.get("page_size", DEFAULT_PAGE_SIZE))
    max_pages = int(company_config.get("max_pages", DEFAULT_MAX_PAGES))

    if not cid:
        raise CollectorError(f"ADP cid missing for {company_name}")

    if not cc_id:
        raise CollectorError(f"ADP ccId missing for {company_name}")

    postings: list[JobPosting] = []
    seen: set[str] = set()

    for page_index in range(max_pages):
        skip = page_index * page_size

        try:
            data = _fetch_adp_page(
                source_url=source_url,
                cid=cid,
                cc_id=cc_id,
                client=client,
                locale=locale,
                skip=skip,
                top=page_size,
            )
        except requests.RequestException as exc:
            raise CollectorError(f"ADP request failed for {company_name}: {exc}") from exc

        jobs = data.get("jobRequisitions") or []
        if not jobs:
            break

        for job in jobs:
            if not isinstance(job, dict):
                continue

            posting = _build_posting(
                company_key=company_key,
                company_name=company_name,
                source_type="adp",
                source_url=source_url,
                job=job,
            )

            if posting is None:
                continue

            dedupe_key = posting.source_job_id or posting.source_url
            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)
            postings.append(posting)

        if len(jobs) < page_size:
            break

    return postings


def _fetch_adp_page(
    *,
    source_url: str,
    cid: str,
    cc_id: str,
    client: str,
    locale: str,
    skip: int,
    top: int,
) -> dict[str, Any]:
    parsed = urlparse(source_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    api_url = (
        f"{base_url}/mascsr/default/careercenter/public/events/staffing"
        "/v1/job-requisitions"
    )

    response = requests.get(
        api_url,
        params={
            "cid": cid,
            "client": client,
            "timeStamp": _timestamp_millis(),
            "ccId": cc_id,
            "lang": locale,
            "locale": locale,
            "$skip": skip,
            "$top": top,
            "userQuery": "",
        },
        headers={
            "User-Agent": BROWSER_USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": locale,
            "locale": locale,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/json",
            "x-forwarded-host": parsed.netloc,
            "Referer": source_url,
        },
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, dict):
        raise CollectorError("ADP search returned unexpected response")

    return data


def _build_posting(
    *,
    company_key: str,
    company_name: str,
    source_type: str,
    source_url: str,
    job: dict[str, Any],
) -> JobPosting | None:
    title = _clean_text(job.get("requisitionTitle"))
    source_job_id = _clean_text(job.get("itemID"))

    if not title or not source_job_id:
        return None

    location = _build_location(job)
    salary_text = _salary_text(job) or _pay_grade_salary_text(job)
    description = _build_description(job)
    public_url = _build_job_url(source_url, source_job_id)

    posting = JobPosting(
        company_key=company_key,
        company_name=company_name,
        source_type=source_type,
        source_url=public_url,
        title=title,
        location=location,
        description=description,
        source_job_id=source_job_id,
        remote_status=_remote_status(location),
        salary_text=salary_text,
        canonical_key=None,
        content_hash=None,
    )

    return JobPosting(
        company_key=posting.company_key,
        company_name=posting.company_name,
        source_type=posting.source_type,
        source_url=posting.source_url,
        title=posting.title,
        location=posting.location,
        description=posting.description,
        source_job_id=posting.source_job_id,
        remote_status=posting.remote_status,
        salary_text=posting.salary_text,
        canonical_key=make_canonical_key(
            posting.company_name,
            posting.title,
            posting.location,
        ),
        content_hash=make_content_hash(
            posting.title,
            posting.location,
            posting.description,
        ),
    )


def _build_location(job: dict[str, Any]) -> str | None:
    locations = job.get("requisitionLocations") or []
    values: list[str] = []

    if isinstance(locations, list):
        for location in locations:
            if not isinstance(location, dict):
                continue

            name_code = location.get("nameCode") or {}
            value = None

            if isinstance(name_code, dict):
                value = _clean_text(name_code.get("shortName"))

            if not value:
                address = location.get("address") or {}
                if isinstance(address, dict):
                    city = _clean_text(address.get("cityName"))
                    region = _nested_code_value(address, "countrySubdivisionLevel1")
                    postal = _clean_text(address.get("postalCode"))
                    parts = [part for part in (city, region, postal) if part]
                    value = ", ".join(parts) if parts else None

            if value and value not in values:
                values.append(value)

    return "; ".join(values) or None


def _build_description(job: dict[str, Any]) -> str | None:
    parts = [
        _clean_text(job.get("clientRequisitionID")),
        _clean_text(job.get("postDate")),
        _nested_short_name(job, "workLevelCode"),
        _custom_fields_text(job),
    ]

    description = "\n\n".join(part for part in parts if part)
    return description or None


def _custom_fields_text(job: dict[str, Any]) -> str | None:
    custom_field_group = job.get("customFieldGroup") or {}
    if not isinstance(custom_field_group, dict):
        return None

    lines: list[str] = []

    for field_group_name in ("stringFields", "codeFields"):
        fields = custom_field_group.get(field_group_name) or []
        if not isinstance(fields, list):
            continue

        for field in fields:
            if not isinstance(field, dict):
                continue

            name_code = field.get("nameCode") or {}
            if not isinstance(name_code, dict):
                continue

            label = _clean_text(name_code.get("codeValue"))
            value = _clean_text(field.get("stringValue")) or _clean_text(
                field.get("shortName")
            )

            if label and value:
                lines.append(f"{label}: {value}")

    return "\n".join(lines) or None


def _salary_text(job: dict[str, Any]) -> str | None:
    custom_field_group = job.get("customFieldGroup") or {}
    if not isinstance(custom_field_group, dict):
        return None

    fields = custom_field_group.get("stringFields") or []
    if not isinstance(fields, list):
        return None

    for field in fields:
        if not isinstance(field, dict):
            continue

        name_code = field.get("nameCode") or {}
        if not isinstance(name_code, dict):
            continue

        if name_code.get("codeValue") == "SalaryRange":
            return _clean_text(field.get("stringValue"))

    return None


def _pay_grade_salary_text(job: dict[str, Any]) -> str | None:
    pay_grade_range = job.get("payGradeRange") or {}
    if not isinstance(pay_grade_range, dict):
        return None

    minimum_rate = pay_grade_range.get("minimumRate") or {}
    maximum_rate = pay_grade_range.get("maximumRate") or {}

    if not isinstance(minimum_rate, dict) or not isinstance(maximum_rate, dict):
        return None

    minimum = minimum_rate.get("amountValue")
    maximum = maximum_rate.get("amountValue")
    currency = _clean_text(minimum_rate.get("currencyCode")) or _clean_text(
        maximum_rate.get("currencyCode")
    )

    if minimum is None or maximum is None:
        return None

    suffix = f" {currency}" if currency else ""
    return f"{minimum} - {maximum}{suffix}"


def _nested_short_name(job: dict[str, Any], key: str) -> str | None:
    value = job.get(key)
    if not isinstance(value, dict):
        return None

    return _clean_text(value.get("shortName"))


def _nested_code_value(job: dict[str, Any], key: str) -> str | None:
    value = job.get(key)
    if not isinstance(value, dict):
        return None

    return _clean_text(value.get("codeValue"))


def _remote_status(location: str | None) -> str | None:
    if location and "remote" in location.lower():
        return "Remote"

    return None


def _build_job_url(source_url: str, source_job_id: str) -> str:
    parsed = urlparse(source_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["jobId"] = [source_job_id]
    query["selectedMenuKey"] = ["CurrentOpenings"]

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query, doseq=True),
            parsed.fragment,
        )
    )


def _config_or_query_value(
    company_config: dict[str, Any],
    source_url: str,
    key: str,
) -> str | None:
    config_value = company_config.get(key)
    if config_value:
        return str(config_value)

    parsed = urlparse(source_url)
    values = parse_qs(parsed.query).get(key)
    if not values:
        return None

    return str(values[0])


def _timestamp_millis() -> int:
    import time

    return int(time.time() * 1000)


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)

    return text or None