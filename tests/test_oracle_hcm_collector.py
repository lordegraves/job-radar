from __future__ import annotations

import pytest
import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.oracle_hcm import collect_oracle_hcm_jobs


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
        "company_key": "saic",
        "name": "SAIC",
        "source_type": "oracle_hcm",
        "source_url": "https://eihu.fa.us8.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        "site_number": "CX",
        "referer_url": "https://eihu.fa.us8.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX/",
        "page_size": 2,
        "max_pages": 2,
    }


def _payload(requisitions, total_jobs_count=None):
    if total_jobs_count is None:
        total_jobs_count = len(requisitions)

    return {
        "items": [
            {
                "TotalJobsCount": total_jobs_count,
                "requisitionList": requisitions,
            }
        ]
    }


def test_collect_oracle_hcm_jobs_builds_posting(monkeypatch):
    def fake_get(url, params, headers, timeout):
        assert url.endswith("/recruitingCEJobRequisitions")
        assert params["onlyData"] == "true"
        assert "requisitionList.workLocation" in params["expand"]
        assert params["finder"] == "findReqs;siteNumber=CX,limit=2,offset=0"
        assert headers["Referer"].endswith("/sites/CX/")
        assert timeout == 30

        return FakeResponse(
            _payload(
                [
                    {
                        "Id": "2612797",
                        "Title": "Program Security Officer",
                        "PrimaryLocation": "Annapolis Junction, MD, United States",
                        "ShortDescriptionStr": "Protect program information.",
                        "ExternalResponsibilitiesStr": "Coordinate security operations.",
                        "ExternalQualificationsStr": "Security experience required.",
                        "WorkplaceType": "On-site",
                    }
                ]
            )
        )

    monkeypatch.setattr(requests, "get", fake_get)

    jobs = collect_oracle_hcm_jobs(_config())

    assert len(jobs) == 1
    assert jobs[0].company_key == "saic"
    assert jobs[0].company_name == "SAIC"
    assert jobs[0].source_type == "oracle_hcm"
    assert jobs[0].title == "Program Security Officer"
    assert jobs[0].location == "Annapolis Junction, MD, United States"
    assert jobs[0].source_job_id == "2612797"
    assert jobs[0].remote_status == "On-site"
    assert jobs[0].source_url.endswith("/sites/CX/job/2612797")
    assert "Protect program information." in jobs[0].description
    assert "Coordinate security operations." in jobs[0].description
    assert "Security experience required." in jobs[0].description
    assert jobs[0].canonical_key
    assert jobs[0].content_hash


def test_collect_oracle_hcm_jobs_paginates(monkeypatch):
    calls = []

    def fake_get(url, params, headers, timeout):
        calls.append(params["finder"])

        if "offset=0" in params["finder"]:
            return FakeResponse(
                _payload(
                    [
                        {"Id": "1", "Title": "First Job", "PrimaryLocation": "Reston, VA, United States"},
                        {"Id": "2", "Title": "Second Job", "PrimaryLocation": "Remote"},
                    ],
                    total_jobs_count=3,
                )
            )

        return FakeResponse(
            _payload(
                [
                    {"Id": "3", "Title": "Third Job", "PrimaryLocation": "Colorado Springs, CO, United States"},
                ],
                total_jobs_count=3,
            )
        )

    monkeypatch.setattr(requests, "get", fake_get)

    jobs = collect_oracle_hcm_jobs(_config())

    assert [job.source_job_id for job in jobs] == ["1", "2", "3"]
    assert calls == [
        "findReqs;siteNumber=CX,limit=2,offset=0",
        "findReqs;siteNumber=CX,limit=2,offset=2",
    ]


def test_collect_oracle_hcm_jobs_deduplicates(monkeypatch):
    def fake_get(url, params, headers, timeout):
        return FakeResponse(
            _payload(
                [
                    {"Id": "1", "Title": "Duplicate Job", "PrimaryLocation": "Remote"},
                    {"Id": "1", "Title": "Duplicate Job", "PrimaryLocation": "Remote"},
                ]
            )
        )

    monkeypatch.setattr(requests, "get", fake_get)

    jobs = collect_oracle_hcm_jobs(_config())

    assert len(jobs) == 1
    assert jobs[0].source_job_id == "1"


def test_collect_oracle_hcm_jobs_wraps_request_errors(monkeypatch):
    def fake_get(url, params, headers, timeout):
        raise requests.RequestException("boom")

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(CollectorError, match="Oracle HCM request failed"):
        collect_oracle_hcm_jobs(_config())