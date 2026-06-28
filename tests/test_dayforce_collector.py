from __future__ import annotations
from logging import config

import pytest
import requests

from job_radar.collectors.dayforce import collect_dayforce_jobs
from job_radar.collectors.greenhouse import CollectorError


class FakeResponse:
    def __init__(self, data=None, text="", status_code=200):
        self._data = data
        self.text = text
        self.status_code = status_code

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, url, headers, timeout):
        self.calls.append(("GET", url, headers, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def post(self, url, headers, json, timeout):
        self.calls.append(("POST", url, headers, json, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _config():
    return {
        "company_key": "asrc_federal",
        "name": "ASRC Federal",
        "source_type": "dayforce",
        "source_url": "https://jobs.dayforcehcm.com/asrcfh/candidateportal",
        "culture_code": "en-US",
        "page_size": 25,
        "max_pages": 2,
    }


def test_collect_dayforce_jobs_builds_posting(monkeypatch):
    fake_session = FakeSession(
        [
            FakeResponse(text="<html></html>"),
            FakeResponse(data={"csrfToken": "token-123"}),
            FakeResponse(
                data={
                    "count": 1,
                    "maxCount": 1,
                    "offset": 0,
                    "jobPostings": [
                        {
                            "jobPostingId": 24907,
                            "jobReqId": 5065,
                            "jobTitle": "Principal Platform Engineer",
                            "jobDescription": "<p>Build reliable platforms.</p>",
                            "postingLocations": [
                                {
                                    "formattedAddress": "Reston, VA",
                                }
                            ],
                            "hasVirtualLocation": False,
                        }
                    ],
                }
            ),
        ]
    )

    monkeypatch.setattr(requests, "Session", lambda: fake_session)

    config = _config()
    config["max_pages"] = 1
    
    jobs = collect_dayforce_jobs(_config())

    assert len(jobs) == 1
    assert jobs[0].company_key == "asrc_federal"
    assert jobs[0].company_name == "ASRC Federal"
    assert jobs[0].source_type == "dayforce"
    assert jobs[0].title == "Principal Platform Engineer"
    assert jobs[0].location == "Reston, VA"
    assert jobs[0].description == "Build reliable platforms."
    assert jobs[0].source_job_id == "24907"
    assert jobs[0].source_url == (
        "https://jobs.dayforcehcm.com/asrcfh/candidateportal/jobs/24907"
    )
    assert jobs[0].canonical_key
    assert jobs[0].content_hash

    post_call = fake_session.calls[2]
    assert post_call[0] == "POST"
    assert post_call[1] == "https://jobs.dayforcehcm.com/api/geo/asrcfh/jobposting/search"
    assert post_call[2]["X-CSRF-TOKEN"] == "token-123"
    assert post_call[3]["cultureCode"] == "en-US"
    assert post_call[3]["paginationStart"] == 0


def test_collect_dayforce_jobs_paginates(monkeypatch):
    fake_session = FakeSession(
        [
            FakeResponse(text="<html></html>"),
            FakeResponse(data={"csrfToken": "token-123"}),
            FakeResponse(
                data={
                    "count": 25,
                    "maxCount": 26,
                    "offset": 0,
                    "jobPostings": [
                        {
                            "jobPostingId": index,
                            "jobTitle": f"Job {index}",
                            "jobDescription": "First page",
                            "postingLocations": [],
                        }
                        for index in range(100, 125)
                    ],
                }
            ),
            FakeResponse(
                data={
                    "count": 1,
                    "maxCount": 26,
                    "offset": 25,
                    "jobPostings": [
                        {
                            "jobPostingId": 125,
                            "jobTitle": "Job 125",
                            "jobDescription": "Second page",
                            "postingLocations": [],
                        }
                    ],
                }
            ),
        ]
    )

    monkeypatch.setattr(requests, "Session", lambda: fake_session)

    jobs = collect_dayforce_jobs(_config())

    assert len(jobs) == 26
    assert jobs[0].source_job_id == "100"
    assert jobs[-1].source_job_id == "125"

    first_post = fake_session.calls[2]
    second_post = fake_session.calls[3]

    assert first_post[3]["paginationStart"] == 0
    assert second_post[3]["paginationStart"] == 25


def test_collect_dayforce_jobs_deduplicates(monkeypatch):
    fake_session = FakeSession(
        [
            FakeResponse(text="<html></html>"),
            FakeResponse(data={"csrfToken": "token-123"}),
            FakeResponse(
                data={
                    "count": 2,
                    "maxCount": 2,
                    "offset": 0,
                    "jobPostings": [
                        {
                            "jobPostingId": 1,
                            "jobTitle": "Duplicate Job",
                            "jobDescription": "Same job",
                            "postingLocations": [],
                        },
                        {
                            "jobPostingId": 1,
                            "jobTitle": "Duplicate Job",
                            "jobDescription": "Same job",
                            "postingLocations": [],
                        },
                    ],
                }
            ),
        ]
    )

    monkeypatch.setattr(requests, "Session", lambda: fake_session)

    config = _config()
    config["max_pages"] = 1

    jobs = collect_dayforce_jobs(config)

    assert len(jobs) == 1
    assert jobs[0].source_job_id == "1"


def test_collect_dayforce_jobs_marks_virtual_location_remote(monkeypatch):
    fake_session = FakeSession(
        [
            FakeResponse(text="<html></html>"),
            FakeResponse(data={"csrfToken": "token-123"}),
            FakeResponse(
                data={
                    "count": 1,
                    "maxCount": 1,
                    "offset": 0,
                    "jobPostings": [
                        {
                            "jobPostingId": 99,
                            "jobTitle": "Remote Job",
                            "jobDescription": "Remote work.",
                            "postingLocations": [],
                            "hasVirtualLocation": True,
                        }
                    ],
                }
            ),
        ]
    )

    monkeypatch.setattr(requests, "Session", lambda: fake_session)

    jobs = collect_dayforce_jobs(_config())

    assert len(jobs) == 1
    assert jobs[0].location == "Remote"
    assert jobs[0].remote_status == "remote"


def test_collect_dayforce_jobs_wraps_request_errors(monkeypatch):
    fake_session = FakeSession(
        [
            requests.RequestException("boom"),
        ]
    )

    monkeypatch.setattr(requests, "Session", lambda: fake_session)

    with pytest.raises(CollectorError, match="Dayforce setup failed"):
        collect_dayforce_jobs(_config())