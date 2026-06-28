from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urlparse

import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


DEFAULT_PAGE_SIZE = 25
DEFAULT_MAX_PAGES = 20

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0"
)


def collect_dayforce_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    company_key = str(company_config["company_key"])
    company_name = str(company_config["name"])
    source_url = str(company_config["source_url"])

    client_namespace, job_board_code = _get_portal_parts(source_url, company_config)
    culture_code = str(company_config.get("culture_code", "en-US"))
    page_size = int(company_config.get("page_size", DEFAULT_PAGE_SIZE))
    max_pages = int(company_config.get("max_pages", DEFAULT_MAX_PAGES))

    session = requests.Session()

    try:
        _load_portal(session, source_url)
        csrf_token = _get_csrf_token(session, source_url)
    except requests.RequestException as exc:
        raise CollectorError(f"Dayforce setup failed for {company_name}: {exc}") from exc

    postings: list[JobPosting] = []
    seen: set[str] = set()
    max_count: int | None = None

    for page_index in range(max_pages):
        pagination_start = page_index * page_size

        try:
            data = _search_jobs(
                session=session,
                portal_url=source_url,
                csrf_token=csrf_token,
                client_namespace=client_namespace,
                job_board_code=job_board_code,
                culture_code=culture_code,
                pagination_start=pagination_start,
            )
        except requests.RequestException as exc:
            raise CollectorError(f"Dayforce search failed for {company_name}: {exc}") from exc

        if max_count is None:
            max_count = _safe_int(data.get("maxCount"))

        jobs = data.get("jobPostings") or []
        if not jobs:
            break

        for job in jobs:
            if not isinstance(job, dict):
                continue

            posting = _build_posting(
                company_key=company_key,
                company_name=company_name,
                source_type="dayforce",
                portal_url=source_url,
                job=job,
            )

            if posting is None:
                continue

            dedupe_key = posting.source_job_id or posting.source_url
            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)
            postings.append(posting)

        if max_count is not None and len(postings) >= max_count:
            break

    return postings


def _load_portal(session: requests.Session, portal_url: str) -> None:
    response = session.get(
        portal_url,
        headers={
            "User-Agent": BROWSER_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
        timeout=30,
    )
    response.raise_for_status()


def _get_csrf_token(session: requests.Session, portal_url: str) -> str:
    parsed = urlparse(portal_url)
    csrf_url = f"{parsed.scheme}://{parsed.netloc}/api/auth/csrf"

    response = session.get(
        csrf_url,
        headers={
            "User-Agent": BROWSER_USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": portal_url,
        },
        timeout=30,
    )
    response.raise_for_status()

    token = response.json().get("csrfToken")
    if not token:
        raise CollectorError("Dayforce CSRF token was missing")

    return str(token)


def _search_jobs(
    *,
    session: requests.Session,
    portal_url: str,
    csrf_token: str,
    client_namespace: str,
    job_board_code: str,
    culture_code: str,
    pagination_start: int,
) -> dict[str, Any]:
    parsed = urlparse(portal_url)
    search_url = (
        f"{parsed.scheme}://{parsed.netloc}"
        f"/api/geo/{client_namespace}/jobposting/search"
    )

    payload = {
        "clientNamespace": client_namespace,
        "jobBoardCode": job_board_code,
        "cultureCode": culture_code,
        "searchText": "",
        "paginationStart": pagination_start,
    }

    response = session.post(
        search_url,
        headers={
            "User-Agent": BROWSER_USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/json",
            "Origin": f"{parsed.scheme}://{parsed.netloc}",
            "Referer": portal_url,
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "X-CSRF-TOKEN": csrf_token,
        },
        json=payload,
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, dict):
        raise CollectorError("Dayforce search returned unexpected response")

    return data


def _build_posting(
    *,
    company_key: str,
    company_name: str,
    source_type: str,
    portal_url: str,
    job: dict[str, Any],
) -> JobPosting | None:
    title = _clean_text(job.get("jobTitle"))
    job_posting_id = _clean_text(job.get("jobPostingId"))

    if not title or not job_posting_id:
        return None

    source_job_id = job_posting_id
    location = _build_location(job)
    description = _clean_description(job.get("jobDescription"))
    source_url = f"{portal_url.rstrip('/')}/jobs/{job_posting_id}"

    posting = JobPosting(
        company_key=company_key,
        company_name=company_name,
        source_type=source_type,
        source_url=source_url,
        title=title,
        location=location,
        description=description,
        source_job_id=source_job_id,
        remote_status=_remote_status(job),
        salary_text=None,
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


def _get_portal_parts(
    source_url: str,
    company_config: dict[str, Any],
) -> tuple[str, str]:
    client_namespace = company_config.get("client_namespace")
    job_board_code = company_config.get("job_board_code")

    if client_namespace and job_board_code:
        return str(client_namespace), str(job_board_code)

    parsed = urlparse(source_url)
    parts = [part for part in parsed.path.split("/") if part]

    if len(parts) < 2:
        raise CollectorError(
            "Dayforce source_url must include client namespace and job board code"
        )

    return parts[0], parts[1]


def _build_location(job: dict[str, Any]) -> str | None:
    locations = job.get("postingLocations") or []
    values: list[str] = []

    if isinstance(locations, list):
        for location in locations:
            if not isinstance(location, dict):
                continue

            value = (
                _clean_text(location.get("formattedAddress"))
                or _clean_text(location.get("displayName"))
                or _clean_text(location.get("name"))
            )

            if value and value not in values:
                values.append(value)

    if values:
        return "; ".join(values)

    if job.get("hasVirtualLocation"):
        return "Remote"

    return None


def _remote_status(job: dict[str, Any]) -> str | None:
    if job.get("hasVirtualLocation"):
        return "remote"

    return None


def _clean_description(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None

    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip() or None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None