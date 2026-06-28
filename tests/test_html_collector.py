from __future__ import annotations

from typing import Any

import pytest
import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.html import (
    _extract_location_from_url,
    _extract_source_job_id,
    _parse_html_jobs,
    collect_html_jobs,
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
        "company_key": "ornl",
        "name": "Oak Ridge National Laboratory",
        "source_type": "html",
        "source_url": "https://jobs.ornl.gov/go/Computational-SciencesSupercomputing-Jobs/4534300/",
    }


def test_extract_source_job_id_from_successfactors_url() -> None:
    assert (
        _extract_source_job_id(
            "https://jobs.ornl.gov/job/Oak-Ridge-IAM-Linux-Engineer-TN-37830/1394830700/"
        )
        == "1394830700"
    )


def test_extract_location_from_successfactors_url() -> None:
    assert (
        _extract_location_from_url(
            "https://jobs.ornl.gov/job/Oak-Ridge-IAM-Linux-Engineer-TN-37830/1394830700/"
        )
        == "Oak Ridge, TN"
    )


def test_parse_html_jobs_returns_job_postings() -> None:
    html = """
    <html>
      <body>
        <span class="jobTitle hidden-phone">
          <a href="/job/Oak-Ridge-IAM-Linux-Engineer-TN-37830/1394830700/" class="jobTitle-link">IAM Linux Engineer</a>
        </span>
      </body>
    </html>
    """

    postings = _parse_html_jobs(
        company_config=_company_config(),
        html=html,
        source_url="https://jobs.ornl.gov/go/Computational-SciencesSupercomputing-Jobs/4534300/",
    )

    assert len(postings) == 1
    assert postings[0].company_key == "ornl"
    assert postings[0].company_name == "Oak Ridge National Laboratory"
    assert postings[0].source_type == "html"
    assert postings[0].source_job_id == "1394830700"
    assert postings[0].source_url == (
        "https://jobs.ornl.gov/job/"
        "Oak-Ridge-IAM-Linux-Engineer-TN-37830/1394830700/"
    )
    assert postings[0].title == "IAM Linux Engineer"
    assert postings[0].location == "Oak Ridge, TN"
    assert postings[0].canonical_key is not None
    assert postings[0].content_hash is not None


def test_parse_html_jobs_dedupes_desktop_and_mobile_links() -> None:
    html = """
    <html>
      <body>
        <span class="jobTitle hidden-phone">
          <a href="/job/Oak-Ridge-IAM-Linux-Engineer-TN-37830/1394830700/" class="jobTitle-link">IAM Linux Engineer</a>
        </span>
        <span class="jobTitle visible-phone">
          <a class="jobTitle-link" href="/job/Oak-Ridge-IAM-Linux-Engineer-TN-37830/1394830700/">IAM Linux Engineer</a>
        </span>
      </body>
    </html>
    """

    postings = _parse_html_jobs(
        company_config=_company_config(),
        html=html,
        source_url="https://jobs.ornl.gov/go/Computational-SciencesSupercomputing-Jobs/4534300/",
    )

    assert len(postings) == 1


def test_collect_html_jobs_fetches_and_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    html = """
    <html>
      <body>
        <a href="/job/Oak-Ridge-HPC-Linux-Systems-Engineer%2C-Classified-Environment-TN-37830/1393480400/" class="jobTitle-link">HPC Linux Systems Engineer, Classified Environment</a>
      </body>
    </html>
    """
    captured = {}

    def fake_get(
        url: str,
        headers: dict[str, str],
        timeout: int,
    ) -> FakeResponse:
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse(text=html)

    monkeypatch.setattr(requests, "get", fake_get)

    postings = collect_html_jobs(_company_config())

    assert captured["url"] == (
        "https://jobs.ornl.gov/go/Computational-SciencesSupercomputing-Jobs/4534300/"
    )
    assert "User-Agent" in captured["headers"]
    assert captured["timeout"] == 30
    assert len(postings) == 1
    assert postings[0].title == "HPC Linux Systems Engineer, Classified Environment"


def test_collect_html_jobs_wraps_request_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(
        url: str,
        headers: dict[str, str],
        timeout: int,
    ) -> FakeResponse:
        raise requests.RequestException("network failed")

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(CollectorError, match="Failed to fetch HTML postings"):
        collect_html_jobs(_company_config())