from __future__ import annotations

from typing import Any

import pytest
import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.icims import (
    _build_search_url,
    _extract_next_page_url,
    _extract_source_job_id,
    _parse_icims_html,
    collect_icims_jobs,
)


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def _company_config() -> dict[str, Any]:
    return {
        "company_key": "peraton",
        "name": "Peraton",
        "source_type": "icims",
        "source_url": "https://careers-peraton.icims.com/jobs",
    }


def test_build_search_url_from_jobs_base() -> None:
    assert (
        _build_search_url("https://careers-peraton.icims.com/jobs")
        == "https://careers-peraton.icims.com/jobs/search?ss=1&searchRelation=keyword_all&in_iframe=1"
    )


def test_build_search_url_keeps_existing_search_url_and_adds_iframe() -> None:
    source_url = "https://careers-peraton.icims.com/jobs/search?ss=1&searchRelation=keyword_all"

    assert (
        _build_search_url(source_url)
        == "https://careers-peraton.icims.com/jobs/search?ss=1&searchRelation=keyword_all&in_iframe=1"
    )


def test_extract_next_page_url_adds_iframe() -> None:
    html = """
    <html>
      <head>
        <link rel="next" href="https://careers-peraton.icims.com/jobs/search?pr=1&amp;searchRelation=keyword_all" />
      </head>
    </html>
    """

    assert _extract_next_page_url(
        html,
        "https://careers-peraton.icims.com/jobs/search?ss=1&searchRelation=keyword_all&in_iframe=1",
    ) == (
        "https://careers-peraton.icims.com/jobs/search?pr=1&searchRelation=keyword_all&in_iframe=1"
    )


def test_extract_source_job_id_from_icims_url() -> None:
    assert (
        _extract_source_job_id(
            "https://careers-peraton.icims.com/jobs/160000/linux-systems-engineer/job"
        )
        == "160000"
    )


def test_parse_icims_html_returns_job_postings() -> None:
    html = """
    <html>
      <body>
        <a href="/jobs/login?loginOnly=1&redirect=search">Log back in!</a>
        <a href="/jobs/160000/senior-linux-systems-engineer/job">
          Senior Linux Systems Engineer
        </a>
        <a href="/jobs/search?ss=1">Search Jobs</a>
        <a href="/jobs/intro">Intro</a>
      </body>
    </html>
    """

    postings = _parse_icims_html(
        company_config=_company_config(),
        html=html,
        search_url="https://careers-peraton.icims.com/jobs/search?ss=1",
    )

    assert len(postings) == 1
    assert postings[0].company_key == "peraton"
    assert postings[0].company_name == "Peraton"
    assert postings[0].source_type == "icims"
    assert postings[0].source_job_id == "160000"
    assert postings[0].source_url == (
        "https://careers-peraton.icims.com/jobs/160000/"
        "senior-linux-systems-engineer/job"
    )
    assert postings[0].title == "Senior Linux Systems Engineer"
    assert postings[0].canonical_key is not None
    assert postings[0].content_hash is not None


def test_parse_icims_html_dedupes_duplicate_links() -> None:
    html = """
    <html>
      <body>
        <a href="/jobs/160000/senior-linux-systems-engineer/job">
          Senior Linux Systems Engineer
        </a>
        <a href="/jobs/160000/senior-linux-systems-engineer/job">
          Senior Linux Systems Engineer
        </a>
      </body>
    </html>
    """

    postings = _parse_icims_html(
        company_config=_company_config(),
        html=html,
        search_url="https://careers-peraton.icims.com/jobs/search?ss=1",
    )

    assert len(postings) == 1


def test_collect_icims_jobs_fetches_and_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    html = """
    <html>
      <body>
        <a href="/jobs/160000/senior-linux-systems-engineer/job">
          Senior Linux Systems Engineer
        </a>
      </body>
    </html>
    """

    captured_urls = []

    def fake_get(
        url: str,
        headers: dict[str, str],
        timeout: int,
    ) -> FakeResponse:
        captured_urls.append(url)
        assert "User-Agent" in headers
        assert timeout == 30
        return FakeResponse(text=html)

    monkeypatch.setattr(requests, "get", fake_get)

    postings = collect_icims_jobs(_company_config())

    assert captured_urls == [
        "https://careers-peraton.icims.com/jobs/search?ss=1&searchRelation=keyword_all&in_iframe=1"
    ]
    assert len(postings) == 1
    assert postings[0].title == "Senior Linux Systems Engineer"


def test_collect_icims_jobs_follows_next_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page_one = """
    <html>
      <head>
        <link rel="next" href="https://careers-peraton.icims.com/jobs/search?pr=1&amp;searchRelation=keyword_all" />
      </head>
      <body>
        <a href="/jobs/160000/senior-linux-systems-engineer/job">
          Senior Linux Systems Engineer
        </a>
      </body>
    </html>
    """
    page_two = """
    <html>
      <body>
        <a href="/jobs/160001/hpc-systems-engineer/job">
          HPC Systems Engineer
        </a>
      </body>
    </html>
    """

    responses = {
        "https://careers-peraton.icims.com/jobs/search?ss=1&searchRelation=keyword_all&in_iframe=1": page_one,
        "https://careers-peraton.icims.com/jobs/search?pr=1&searchRelation=keyword_all&in_iframe=1": page_two,
    }
    captured_urls = []

    def fake_get(
        url: str,
        headers: dict[str, str],
        timeout: int,
    ) -> FakeResponse:
        captured_urls.append(url)
        return FakeResponse(text=responses[url])

    monkeypatch.setattr(requests, "get", fake_get)

    postings = collect_icims_jobs(_company_config())

    assert captured_urls == list(responses.keys())
    assert [posting.title for posting in postings] == [
        "Senior Linux Systems Engineer",
        "HPC Systems Engineer",
    ]


def test_collect_icims_jobs_wraps_request_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(
        url: str,
        headers: dict[str, str],
        timeout: int,
    ) -> FakeResponse:
        raise requests.RequestException("network failed")

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(CollectorError, match="Failed to fetch iCIMS postings"):
        collect_icims_jobs(_company_config())