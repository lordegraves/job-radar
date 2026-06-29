from __future__ import annotations

from typing import Any

import pytest
import requests

from job_radar.collectors.activate import collect_activate_jobs
from job_radar.collectors.greenhouse import CollectorError


class FakeResponse:
    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        text: str = "",
        status_code: int = 200,
    ) -> None:
        self._payload = payload
        self.text = text
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        if self._payload is None:
            raise ValueError("invalid json")

        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def _config() -> dict[str, Any]:
    return {
        "company_key": "lanl",
        "name": "Los Alamos National Laboratory",
        "source_type": "activate",
        "source_url": "https://lanl.jobs/Search/SearchResults",
        "source_base_url": "https://lanl.jobs",
        "referer_url": "https://lanl.jobs/search/searchjobs",
        "page_size": 25,
        "max_pages": 1,
    }


def test_collect_activate_jobs_returns_job_postings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "Result": "OK",
        "TotalRecordCount": 1,
        "Records": [
            {
                "ID": "2bd0cb41-fa2b-44ee-9328-39d78ba67891",
                "ReferenceNumber": "<span>IRC144820</span>",
                "Title": "<span>Nuclear Facilities Engineer 3/4 - Shift Technical Engineer</span>",
                "CityStateDataAbbrev": "<span>Los Alamos, NM</span>",
                "DepartmentName": "<span>71E03C</span>",
                "PostedDate": "<span>6/26/2026</span>",
                "TrackingObject": {
                    "ReferenceNumberJson": "IRC144820",
                    "TitleJson": "Nuclear Facilities Engineer 3/4 - Shift Technical Engineer",
                    "DepartmentNameJson": "71E03C",
                    "PostedDateJson": "6/26/2026",
                    "LocationNamesJson": ["Los Alamos, NM"],
                    "AtsCategoryNamesJson": ["Engineering"],
                },
            }
        ],
    }
    captured = {}

    def fake_get(
        url: str,
        params: dict[str, int],
        headers: dict[str, str],
        timeout: int,
    ) -> FakeResponse:
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse(payload=payload)

    monkeypatch.setattr(requests, "get", fake_get)

    jobs = collect_activate_jobs(_config())

    assert captured["url"] == "https://lanl.jobs/Search/SearchResults"
    assert captured["params"] == {"jtStartIndex": 0, "jtPageSize": 25}
    assert captured["headers"]["Referer"] == "https://lanl.jobs/search/searchjobs"
    assert captured["headers"]["X-Requested-With"] == "XMLHttpRequest"
    assert captured["timeout"] == 30

    assert len(jobs) == 1
    assert jobs[0].company_key == "lanl"
    assert jobs[0].company_name == "Los Alamos National Laboratory"
    assert jobs[0].source_type == "activate"
    assert jobs[0].source_job_id == "2bd0cb41-fa2b-44ee-9328-39d78ba67891"
    assert jobs[0].source_url == (
        "https://lanl.jobs/search/jobdetails/"
        "nuclear-facilities-engineer-3-4-shift-technical-engineer/"
        "2bd0cb41-fa2b-44ee-9328-39d78ba67891"
    )
    assert jobs[0].title == "Nuclear Facilities Engineer 3/4 - Shift Technical Engineer"
    assert jobs[0].location == "Los Alamos, NM"
    assert jobs[0].description == "IRC144820 | 71E03C | 6/26/2026 | Engineering"
    assert jobs[0].canonical_key is not None
    assert jobs[0].content_hash is not None


def test_collect_activate_jobs_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    payloads = [
        {
            "Result": "OK",
            "TotalRecordCount": 2,
            "Records": [
                {
                    "ID": "first-id",
                    "Title": "<span>First Job</span>",
                    "CityStateDataAbbrev": "<span>Los Alamos, NM</span>",
                    "TrackingObject": {"TitleJson": "First Job"},
                }
            ],
        },
        {
            "Result": "OK",
            "TotalRecordCount": 2,
            "Records": [
                {
                    "ID": "second-id",
                    "Title": "<span>Second Job</span>",
                    "CityStateDataAbbrev": "<span>Los Alamos, NM</span>",
                    "TrackingObject": {"TitleJson": "Second Job"},
                }
            ],
        },
    ]
    starts = []

    def fake_get(
        url: str,
        params: dict[str, int],
        headers: dict[str, str],
        timeout: int,
    ) -> FakeResponse:
        starts.append(params["jtStartIndex"])
        return FakeResponse(payload=payloads.pop(0))

    config = _config()
    config["page_size"] = 1
    config["max_pages"] = 2

    monkeypatch.setattr(requests, "get", fake_get)

    jobs = collect_activate_jobs(config)

    assert starts == [0, 1]
    assert [job.title for job in jobs] == ["First Job", "Second Job"]


def test_collect_activate_jobs_wraps_request_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(
        url: str,
        params: dict[str, int],
        headers: dict[str, str],
        timeout: int,
    ) -> FakeResponse:
        raise requests.RequestException("network failed")

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(CollectorError, match="Failed to fetch Activate postings"):
        collect_activate_jobs(_config())