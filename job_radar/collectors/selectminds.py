from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.models import JobPosting
from job_radar.normalize import make_canonical_key, make_content_hash


class SelectMindsJobParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.jobs: list[dict[str, str | None]] = []

        self._current_job: dict[str, str | None] | None = None
        self._capture_title = False
        self._capture_description = False
        self._capture_field_value = False
        self._pending_field_value: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        class_names = set((attrs_dict.get("class") or "").split())

        if tag == "a" and "job_link" in class_names:
            href = attrs_dict.get("href")
            self._current_job = {
                "title": "",
                "source_url": urljoin(self.base_url, href or ""),
                "description": None,
                "source_job_id": None,
                "post_date": None,
            }
            self.jobs.append(self._current_job)
            self._capture_title = True
            return

        if tag == "p" and "jlr_description" in class_names and self._current_job:
            self._capture_description = True
            self._current_job["description"] = ""
            return

        if tag == "span" and "field_value" in class_names and self._current_job:
            self._capture_field_value = True
            self._pending_field_value = ""
            return

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._capture_title = False

        if tag == "p":
            self._capture_description = False

        if tag == "span" and self._capture_field_value:
            self._capture_field_value = False

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return

        if self._capture_title and self._current_job:
            self._current_job["title"] = _append_text(self._current_job.get("title"), text)
            return

        if self._capture_description and self._current_job:
            self._current_job["description"] = _append_text(
                self._current_job.get("description"),
                text,
            )
            return

        if self._capture_field_value:
            self._pending_field_value = _append_text(self._pending_field_value, text)
            return

        if self._pending_field_value and self._current_job:
            if text == "Requisition #":
                self._current_job["source_job_id"] = self._pending_field_value
                self._pending_field_value = None
                return

            if text == "Post Date":
                self._current_job["post_date"] = self._pending_field_value
                self._pending_field_value = None
                return


def collect_selectminds_jobs(company_config: dict[str, Any]) -> list[JobPosting]:
    company_key = str(company_config["company_key"])
    company_name = str(company_config["name"])
    source_url = str(company_config["source_url"])

    try:
        html = _fetch_selectminds_page(source_url)
    except requests.RequestException as exc:
        raise CollectorError(f"SelectMinds request failed for {company_name}: {exc}") from exc

    parser = SelectMindsJobParser(source_url)
    parser.feed(html)

    postings: list[JobPosting] = []
    seen: set[str] = set()

    for job in parser.jobs:
        posting = _build_posting(
            company_key=company_key,
            company_name=company_name,
            source_type="selectminds",
            job=job,
        )

        if posting is None:
            continue

        dedupe_key = posting.source_job_id or posting.source_url
        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)
        postings.append(posting)

    return postings


def _fetch_selectminds_page(source_url: str) -> str:
    response = requests.get(
        source_url,
        headers={
            "User-Agent": "JobRadar/0.1 local career-source scanner",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.text


def _build_posting(
    *,
    company_key: str,
    company_name: str,
    source_type: str,
    job: dict[str, str | None],
) -> JobPosting | None:
    title = _clean_text(job.get("title"))
    source_url = _clean_text(job.get("source_url"))

    if not title or not source_url:
        return None

    source_job_id = _clean_text(job.get("source_job_id")) or _job_id_from_url(source_url)
    description = _build_description(job)

    posting = JobPosting(
        company_key=company_key,
        company_name=company_name,
        source_type=source_type,
        source_url=source_url,
        title=title,
        location=None,
        description=description,
        source_job_id=source_job_id,
        remote_status=None,
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


def _build_description(job: dict[str, str | None]) -> str | None:
    parts = [
        _clean_text(job.get("description")),
        _format_label("Post Date", job.get("post_date")),
    ]

    description = "\n\n".join(part for part in parts if part)
    return description or None


def _format_label(label: str, value: str | None) -> str | None:
    clean_value = _clean_text(value)
    if not clean_value:
        return None
    return f"{label}: {clean_value}"


def _job_id_from_url(source_url: str) -> str | None:
    last_part = source_url.rstrip("/").split("/")[-1]
    if "-" not in last_part:
        return None

    candidate = last_part.rsplit("-", 1)[-1]
    if candidate.isdigit():
        return candidate

    return None


def _append_text(existing: str | None, text: str) -> str:
    if not existing:
        return text
    return f"{existing} {text}"


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None