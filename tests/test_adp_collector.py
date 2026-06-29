from __future__ import annotations

import pytest
import requests

from job_radar.collectors.adp import collect_adp_jobs
from job_radar.collectors.greenhouse import CollectorError


class FakeResponse:
    def __init__(self, data=None, status_code=200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def _config():
    return {
        "company_key": "usra",
        "name": "USRA",
        "source_type": "adp",
        "source_url": (
            "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/"
            "recruitment.html?cid=f03960f2-20cd-4828-9ae5-415eefc7072e"
            "&ccId=19000101_000001&lang=en_US"
        ),
        "locale": "en_US",
        "page_size": 2,
        "max_pages": 2,
    }


def _payload(jobs):
    return {
        "jobRequisitions": jobs,
        "meta": {},
    }


def test_collect_adp_jobs_builds_posting(monkeypatch):
    calls = []

    def fake_get(url, params, headers, timeout):
        calls.append((url, params, headers, timeout))

        return FakeResponse(
            _payload(
                [
                    {
                        "itemID": "9202023571292_1",
                        "requisitionTitle": "Engineer, Software (EarthRISE)",
                        "postDate": "2026-04-07T11:27:00.000-04:00",
                        "clientRequisitionID": "1415",
                        "workLevelCode": {"shortName": "Full-time"},
                        "payGradeRange": {
                            "minimumRate": {
                                "amountValue": 70245.0,
                                "currencyCode": "USD",
                            },
                            "maximumRate": {
                                "amountValue": 105420.0,
                                "currencyCode": "USD",
                            },
                        },
                        "customFieldGroup": {
                            "stringFields": [
                                {
                                    "stringValue": "Engineering",
                                    "nameCode": {"codeValue": "JobClass"},
                                },
                                {
                                    "stringValue": "70245.00 To 105420.00 (USD) Annually",
                                    "nameCode": {"codeValue": "SalaryRange"},
                                },
                            ],
                            "codeFields": [
                                {
                                    "shortName": "Annually",
                                    "nameCode": {"codeValue": "SalaryType"},
                                }
                            ],
                        },
                        "requisitionLocations": [
                            {
                                "address": {
                                    "cityName": "Huntsville",
                                    "countrySubdivisionLevel1": {"codeValue": "AL"},
                                    "postalCode": "35805",
                                },
                                "nameCode": {"shortName": " Huntsville, AL, US"},
                            }
                        ],
                    }
                ]
            )
        )

    monkeypatch.setattr(requests, "get", fake_get)

    jobs = collect_adp_jobs(_config())

    assert len(jobs) == 1
    assert jobs[0].company_key == "usra"
    assert jobs[0].company_name == "USRA"
    assert jobs[0].source_type == "adp"
    assert jobs[0].title == "Engineer, Software (EarthRISE)"
    assert jobs[0].location == "Huntsville, AL, US"
    assert jobs[0].source_job_id == "9202023571292_1"
    assert jobs[0].salary_text == "70245.00 To 105420.00 (USD) Annually"
    assert jobs[0].source_url == (
        "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/"
        "recruitment.html?cid=f03960f2-20cd-4828-9ae5-415eefc7072e"
        "&ccId=19000101_000001&lang=en_US"
        "&jobId=9202023571292_1&selectedMenuKey=CurrentOpenings"
    )
    assert "1415" in jobs[0].description
    assert "JobClass: Engineering" in jobs[0].description
    assert jobs[0].canonical_key
    assert jobs[0].content_hash

    assert len(calls) == 1
    url, params, headers, timeout = calls[0]

    assert url == (
        "https://workforcenow.adp.com/mascsr/default/careercenter/public/"
        "events/staffing/v1/job-requisitions"
    )
    assert params["cid"] == "f03960f2-20cd-4828-9ae5-415eefc7072e"
    assert params["ccId"] == "19000101_000001"
    assert params["lang"] == "en_US"
    assert params["locale"] == "en_US"
    assert params["$skip"] == 0
    assert params["$top"] == 2
    assert params["userQuery"] == ""
    assert headers["X-Requested-With"] == "XMLHttpRequest"
    assert headers["x-forwarded-host"] == "workforcenow.adp.com"
    assert timeout == 30


def test_collect_adp_jobs_paginates(monkeypatch):
    calls = []

    def fake_get(url, params, headers, timeout):
        calls.append(params.copy())

        if params["$skip"] == 0:
            return FakeResponse(
                _payload(
                    [
                        {
                            "itemID": "1",
                            "requisitionTitle": "First Job",
                            "requisitionLocations": [],
                        },
                        {
                            "itemID": "2",
                            "requisitionTitle": "Second Job",
                            "requisitionLocations": [],
                        },
                    ]
                )
            )

        return FakeResponse(
            _payload(
                [
                    {
                        "itemID": "3",
                        "requisitionTitle": "Third Job",
                        "requisitionLocations": [],
                    }
                ]
            )
        )

    monkeypatch.setattr(requests, "get", fake_get)

    jobs = collect_adp_jobs(_config())

    assert [job.source_job_id for job in jobs] == ["1", "2", "3"]
    assert calls[0]["$skip"] == 0
    assert calls[1]["$skip"] == 2


def test_collect_adp_jobs_deduplicates(monkeypatch):
    def fake_get(url, params, headers, timeout):
        return FakeResponse(
            _payload(
                [
                    {
                        "itemID": "1",
                        "requisitionTitle": "Duplicate Job",
                        "requisitionLocations": [],
                    },
                    {
                        "itemID": "1",
                        "requisitionTitle": "Duplicate Job",
                        "requisitionLocations": [],
                    },
                ]
            )
        )

    monkeypatch.setattr(requests, "get", fake_get)

    config = _config()
    config["max_pages"] = 1

    jobs = collect_adp_jobs(config)

    assert len(jobs) == 1
    assert jobs[0].source_job_id == "1"


def test_collect_adp_jobs_wraps_request_errors(monkeypatch):
    def fake_get(url, params, headers, timeout):
        raise requests.RequestException("boom")

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(CollectorError, match="ADP request failed"):
        collect_adp_jobs(_config())


def test_collect_adp_jobs_requires_cid(monkeypatch):
    config = _config()
    config["source_url"] = (
        "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/"
        "recruitment.html?ccId=19000101_000001&lang=en_US"
    )

    with pytest.raises(CollectorError, match="ADP cid missing"):
        collect_adp_jobs(config)


def test_collect_adp_jobs_requires_cc_id(monkeypatch):
    config = _config()
    config["source_url"] = (
        "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/"
        "recruitment.html?cid=f03960f2-20cd-4828-9ae5-415eefc7072e&lang=en_US"
    )

    with pytest.raises(CollectorError, match="ADP ccId missing"):
        collect_adp_jobs(config)