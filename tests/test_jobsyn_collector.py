from __future__ import annotations

import pytest
import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.jobsyn import collect_jobsyn_jobs


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._payload


def test_collect_jobsyn_jobs_builds_posting(monkeypatch):
    calls = []

    def fake_get(url, params, headers, timeout):
        calls.append((url, params, headers, timeout))
        return FakeResponse(
            {
                "featured_jobs": [],
                "jobs": [
                    {
                        "title_exact": "Senior Linux Systems Engineer",
                        "location_exact": "Albuquerque, NM",
                        "description": "Linux systems engineering role.",
                        "reqid": "123456",
                        "guid": "ABCDEF",
                    }
                ],
                "pagination": {
                    "has_more_pages": False,
                    "page": 1,
                    "total_pages": 1,
                },
            }
        )

    monkeypatch.setattr(requests, "get", fake_get)

    postings = collect_jobsyn_jobs(_company_config())

    assert len(postings) == 1
    assert postings[0].company_key == "sandia"
    assert postings[0].company_name == "Sandia National Laboratories"
    assert postings[0].source_type == "jobsyn"
    assert postings[0].title == "Senior Linux Systems Engineer"
    assert postings[0].location == "Albuquerque, NM"
    assert postings[0].description == "Linux systems engineering role."
    assert postings[0].source_job_id == "123456"
    assert postings[0].canonical_key
    assert postings[0].content_hash

    assert calls[0][0] == "https://prod-search-api.jobsyn.org/api/v1/solr/search"
    assert calls[0][1] == {"page": 1, "num_items": 40}
    assert calls[0][2]["X-Origin"] == "sandia.jobs"


def test_collect_jobsyn_jobs_paginates(monkeypatch):
    pages = {
        1: {
            "featured_jobs": [],
            "jobs": [
                {
                    "title_exact": "First Job",
                    "location_exact": "Albuquerque, NM",
                    "description": "First description.",
                    "reqid": "111111",
                }
            ],
            "pagination": {
                "has_more_pages": True,
                "page": 1,
                "total_pages": 2,
            },
        },
        2: {
            "featured_jobs": [],
            "jobs": [
                {
                    "title_exact": "Second Job",
                    "location_exact": "Livermore, CA",
                    "description": "Second description.",
                    "reqid": "222222",
                }
            ],
            "pagination": {
                "has_more_pages": False,
                "page": 2,
                "total_pages": 2,
            },
        },
    }

    def fake_get(url, params, headers, timeout):
        return FakeResponse(pages[params["page"]])

    monkeypatch.setattr(requests, "get", fake_get)

    postings = collect_jobsyn_jobs(_company_config())

    assert [posting.title for posting in postings] == ["First Job", "Second Job"]


def test_collect_jobsyn_jobs_deduplicates_featured_jobs(monkeypatch):
    def fake_get(url, params, headers, timeout):
        raw_job = {
            "title_exact": "Featured Job",
            "location_exact": "Albuquerque, NM",
            "description": "Same job in featured and regular results.",
            "reqid": "333333",
        }
        return FakeResponse(
            {
                "featured_jobs": [raw_job],
                "jobs": [raw_job],
                "pagination": {
                    "has_more_pages": False,
                    "page": 1,
                    "total_pages": 1,
                },
            }
        )

    monkeypatch.setattr(requests, "get", fake_get)

    postings = collect_jobsyn_jobs(_company_config())

    assert len(postings) == 1
    assert postings[0].source_job_id == "333333"


def test_collect_jobsyn_jobs_wraps_request_errors(monkeypatch):
    def fake_get(url, params, headers, timeout):
        raise requests.Timeout("timed out")

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(CollectorError, match="Jobsyn request failed"):
        collect_jobsyn_jobs(_company_config())


def _company_config():
    return {
        "company_key": "sandia",
        "name": "Sandia National Laboratories",
        "source_type": "jobsyn",
        "source_url": "https://prod-search-api.jobsyn.org/api/v1/solr/search",
        "x_origin": "sandia.jobs",
        "origin_url": "https://sandia.jobs",
        "referer_url": "https://sandia.jobs/jobs/",
        "page_size": 40,
        "max_pages": 3,
    }