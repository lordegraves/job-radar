from __future__ import annotations

import pytest
import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.smartrecruiters import collect_smartrecruiters_jobs


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _config():
    return {
        "company_key": "llnl",
        "name": "Lawrence Livermore National Laboratory",
        "source_type": "smartrecruiters",
        "source_url": "https://api.smartrecruiters.com/v1/companies/LLNL/postings",
        "company_identifier": "LLNL",
        "page_size": 2,
        "max_pages": 2,
    }


def _payload(jobs, total_found=None):
    if total_found is None:
        total_found = len(jobs)

    return {
        "offset": 0,
        "limit": 2,
        "totalFound": total_found,
        "content": jobs,
    }


def test_collect_smartrecruiters_jobs_builds_posting(monkeypatch):
    def fake_get(url, params, headers, timeout):
        assert url == "https://api.smartrecruiters.com/v1/companies/LLNL/postings"
        assert params == {"limit": 2, "offset": 0}
        assert headers["Accept"] == "application/json, text/plain, */*"
        assert timeout == 30

        return FakeResponse(
            _payload(
                [
                    {
                        "id": "3743990013799376",
                        "name": "Database Reliability Engineer",
                        "refNumber": "REF1234A",
                        "location": {
                            "fullLocation": "Livermore, CA, United States",
                            "remote": False,
                            "hybrid": True,
                        },
                        "industry": {"label": "Research"},
                        "function": {"label": "Information Technology"},
                        "typeOfEmployment": {"label": "Full-time"},
                        "experienceLevel": {"label": "Mid-Senior Level"},
                        "customField": [
                            {
                                "fieldLabel": "Organization",
                                "valueLabel": "Computing",
                            },
                            {
                                "fieldLabel": "Category",
                                "valueLabel": "Information Technology",
                            },
                        ],
                    }
                ]
            )
        )

    monkeypatch.setattr(requests, "get", fake_get)

    jobs = collect_smartrecruiters_jobs(_config())

    assert len(jobs) == 1
    assert jobs[0].company_key == "llnl"
    assert jobs[0].company_name == "Lawrence Livermore National Laboratory"
    assert jobs[0].source_type == "smartrecruiters"
    assert jobs[0].title == "Database Reliability Engineer"
    assert jobs[0].location == "Livermore, CA, United States"
    assert jobs[0].source_job_id == "3743990013799376"
    assert jobs[0].remote_status == "Hybrid"
    assert jobs[0].source_url == (
        "https://jobs.smartrecruiters.com/LLNL/"
        "3743990013799376-database-reliability-engineer"
    )
    assert "REF1234A" in jobs[0].description
    assert "Organization: Computing" in jobs[0].description
    assert jobs[0].canonical_key
    assert jobs[0].content_hash


def test_collect_smartrecruiters_jobs_paginates(monkeypatch):
    calls = []

    def fake_get(url, params, headers, timeout):
        calls.append(params.copy())

        if params["offset"] == 0:
            return FakeResponse(
                _payload(
                    [
                        {"id": "1", "name": "First Job", "location": {"fullLocation": "Livermore, CA"}},
                        {"id": "2", "name": "Second Job", "location": {"fullLocation": "Remote", "remote": True}},
                    ],
                    total_found=3,
                )
            )

        return FakeResponse(
            _payload(
                [
                    {"id": "3", "name": "Third Job", "location": {"fullLocation": "Livermore, CA"}},
                ],
                total_found=3,
            )
        )

    monkeypatch.setattr(requests, "get", fake_get)

    jobs = collect_smartrecruiters_jobs(_config())

    assert [job.source_job_id for job in jobs] == ["1", "2", "3"]
    assert calls == [
        {"limit": 2, "offset": 0},
        {"limit": 2, "offset": 2},
    ]


def test_collect_smartrecruiters_jobs_deduplicates(monkeypatch):
    def fake_get(url, params, headers, timeout):
        return FakeResponse(
            _payload(
                [
                    {"id": "1", "name": "Duplicate Job", "location": {"fullLocation": "Livermore, CA"}},
                    {"id": "1", "name": "Duplicate Job", "location": {"fullLocation": "Livermore, CA"}},
                ]
            )
        )

    monkeypatch.setattr(requests, "get", fake_get)

    jobs = collect_smartrecruiters_jobs(_config())

    assert len(jobs) == 1
    assert jobs[0].source_job_id == "1"


def test_collect_smartrecruiters_jobs_wraps_request_errors(monkeypatch):
    def fake_get(url, params, headers, timeout):
        raise requests.RequestException("boom")

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(CollectorError, match="SmartRecruiters request failed"):
        collect_smartrecruiters_jobs(_config())