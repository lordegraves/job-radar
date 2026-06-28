from __future__ import annotations

import json

import pytest
import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.phenom import collect_phenom_jobs


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def _config():
    return {
        "company_key": "battelle",
        "name": "Battelle",
        "source_type": "phenom",
        "source_url": "https://jobs.battelle.org/us/en/search-results",
        "job_base_url": "https://jobs.battelle.org/us/en",
        "page_size": 2,
        "max_pages": 2,
    }


def _html(search_data):
    ddo = {
        "eagerLoadRefineSearch": search_data,
    }
    return f"""
    <html>
      <head>
        <script type="text/javascript">
          var phApp = phApp || {{}};
          phApp.ddo = {json.dumps(ddo)};
        </script>
      </head>
    </html>
    """


def test_collect_phenom_jobs_builds_posting(monkeypatch):
    search_data = {
        "status": 200,
        "hits": 1,
        "totalHits": 1,
        "data": {
            "jobs": [
                {
                    "title": "Systems Engineer",
                    "jobSeqNo": "BMIBMIUS12345EXTERNALENUS",
                    "reqId": "12345",
                    "jobId": "12345",
                    "location": "Columbus, OH",
                    "category": "Information Technology",
                    "subCategory": "Systems Engineering",
                    "type": "Full-Time",
                    "descriptionTeaser": "Build and support technical systems.",
                    "postedDate": "2026-06-01T00:00:00.000+0000",
                }
            ]
        },
    }

    def fake_get(url, headers, timeout):
        assert url == "https://jobs.battelle.org/us/en/search-results?from=0&s=1"
        assert headers["Accept"].startswith("text/html")
        assert timeout == 30
        return FakeResponse(_html(search_data))

    monkeypatch.setattr(requests, "get", fake_get)

    jobs = collect_phenom_jobs(_config())

    assert len(jobs) == 1
    assert jobs[0].company_key == "battelle"
    assert jobs[0].company_name == "Battelle"
    assert jobs[0].source_type == "phenom"
    assert jobs[0].title == "Systems Engineer"
    assert jobs[0].location == "Columbus, OH"
    assert jobs[0].source_job_id == "12345"
    assert jobs[0].source_url == (
        "https://jobs.battelle.org/us/en/job/"
        "BMIBMIUS12345EXTERNALENUS/systems-engineer"
    )
    assert "Build and support technical systems." in jobs[0].description
    assert "Category: Information Technology" in jobs[0].description
    assert jobs[0].canonical_key
    assert jobs[0].content_hash


def test_collect_phenom_jobs_paginates(monkeypatch):
    calls = []

    def fake_get(url, headers, timeout):
        calls.append(url)

        if "from=0" in url:
            return FakeResponse(
                _html(
                    {
                        "status": 200,
                        "hits": 2,
                        "totalHits": 3,
                        "data": {
                            "jobs": [
                                {
                                    "title": "First Job",
                                    "jobSeqNo": "SEQ1",
                                    "reqId": "1",
                                    "location": "Columbus, OH",
                                },
                                {
                                    "title": "Second Job",
                                    "jobSeqNo": "SEQ2",
                                    "reqId": "2",
                                    "location": "Columbus, OH",
                                },
                            ]
                        },
                    }
                )
            )

        return FakeResponse(
            _html(
                {
                    "status": 200,
                    "hits": 1,
                    "totalHits": 3,
                    "data": {
                        "jobs": [
                            {
                                "title": "Third Job",
                                "jobSeqNo": "SEQ3",
                                "reqId": "3",
                                "location": "Columbus, OH",
                            }
                        ]
                    },
                }
            )
        )

    monkeypatch.setattr(requests, "get", fake_get)

    jobs = collect_phenom_jobs(_config())

    assert [job.source_job_id for job in jobs] == ["1", "2", "3"]
    assert calls == [
        "https://jobs.battelle.org/us/en/search-results?from=0&s=1",
        "https://jobs.battelle.org/us/en/search-results?from=2&s=1",
    ]


def test_collect_phenom_jobs_deduplicates(monkeypatch):
    search_data = {
        "status": 200,
        "hits": 2,
        "totalHits": 2,
        "data": {
            "jobs": [
                {
                    "title": "Duplicate Job",
                    "jobSeqNo": "SEQ1",
                    "reqId": "1",
                    "location": "Columbus, OH",
                },
                {
                    "title": "Duplicate Job",
                    "jobSeqNo": "SEQ1",
                    "reqId": "1",
                    "location": "Columbus, OH",
                },
            ]
        },
    }

    def fake_get(url, headers, timeout):
        return FakeResponse(_html(search_data))

    monkeypatch.setattr(requests, "get", fake_get)

    jobs = collect_phenom_jobs(_config())

    assert len(jobs) == 1
    assert jobs[0].source_job_id == "1"


def test_collect_phenom_jobs_wraps_request_errors(monkeypatch):
    def fake_get(url, headers, timeout):
        raise requests.RequestException("boom")

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(CollectorError, match="Phenom request failed"):
        collect_phenom_jobs(_config())