from __future__ import annotations

from typing import Any

import pytest
import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.jibe import (
    _build_source_url,
    _get_location,
    _parse_jibe_payload,
    collect_jibe_jobs,
)


class FakeResponse:
    def __init__(
        self,
        payload: dict[str, Any] | list[Any] | None = None,
        status_code: int = 200,
    ) -> None:
        self._payload = payload if payload is not None else {}
        self.status_code = status_code
        self.text = str(self._payload)

    def json(self) -> dict[str, Any] | list[Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def _company_config() -> dict[str, Any]:
    return {
        "company_key": "amd",
        "name": "AMD",
        "source_type": "jibe",
        "source_url": "https://careers.amd.com/api/jobs",
        "referer_url": "https://careers.amd.com/careers-home/jobs",
        "job_url_template": "https://careers.amd.com/careers-home/jobs/{slug}",
    }


def test_get_location_prefers_full_location() -> None:
    data = {
        "full_location": "Austin, Texas",
        "short_location": "Austin",
        "city": "Austin",
        "state": "Texas",
        "country": "United States",
    }

    assert _get_location(data) == "Austin, Texas"


def test_build_source_url_uses_template() -> None:
    data = {"slug": "87440", "apply_url": "https://careers-amd.icims.com/jobs/87440/login"}

    assert (
        _build_source_url(_company_config(), data)
        == "https://careers.amd.com/careers-home/jobs/87440"
    )


def test_parse_jibe_payload_returns_job_postings() -> None:
    payload = {
        "jobs": [
            {
                "data": {
                    "slug": "87440",
                    "req_id": "87440",
                    "title": "GPU Performance Architect",
                    "description": "Build GPU performance models.",
                    "responsibilities": "Tune GPU systems.",
                    "qualifications": "Linux experience.",
                    "full_location": "Austin, Texas",
                    "tags2": ["USD $126,490.00/Yr."],
                    "tags3": ["USD $180,700.00/Yr."],
                }
            }
        ]
    }

    postings = _parse_jibe_payload(_company_config(), payload)

    assert len(postings) == 1
    assert postings[0].company_key == "amd"
    assert postings[0].company_name == "AMD"
    assert postings[0].source_type == "jibe"
    assert postings[0].source_job_id == "87440"
    assert postings[0].source_url == "https://careers.amd.com/careers-home/jobs/87440"
    assert postings[0].title == "GPU Performance Architect"
    assert postings[0].location == "Austin, Texas"
    assert "Build GPU performance models." in postings[0].description
    assert "Tune GPU systems." in postings[0].description
    assert "Linux experience." in postings[0].description
    assert postings[0].salary_text == "USD $126,490.00/Yr. | USD $180,700.00/Yr."
    assert postings[0].canonical_key is not None
    assert postings[0].content_hash is not None


def test_parse_jibe_payload_skips_incomplete_jobs() -> None:
    payload = {
        "jobs": [
            {"data": {"req_id": "87440", "title": ""}},
            {"data": {"title": "Missing ID"}},
        ]
    }

    assert _parse_jibe_payload(_company_config(), payload) == []


def test_parse_jibe_payload_requires_jobs_list() -> None:
    with pytest.raises(CollectorError, match="Jibe response jobs field is not a list"):
        _parse_jibe_payload(_company_config(), {"jobs": {}})


def test_collect_jibe_jobs_fetches_and_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "jobs": [
            {
                "data": {
                    "slug": "87440",
                    "req_id": "87440",
                    "title": "GPU Performance Architect",
                    "description": "Build GPU performance models.",
                    "full_location": "Austin, Texas",
                }
            }
        ]
    }
    captured = {}

    def fake_get(
        url: str,
        headers: dict[str, str],
        timeout: int,
    ) -> FakeResponse:
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse(payload=payload)

    monkeypatch.setattr(requests, "get", fake_get)

    postings = collect_jibe_jobs(_company_config())

    assert captured["url"] == "https://careers.amd.com/api/jobs"
    assert captured["headers"]["Referer"] == "https://careers.amd.com/careers-home/jobs"
    assert captured["timeout"] == 30
    assert len(postings) == 1
    assert postings[0].title == "GPU Performance Architect"


def test_collect_jibe_jobs_wraps_request_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(
        url: str,
        headers: dict[str, str],
        timeout: int,
    ) -> FakeResponse:
        raise requests.RequestException("network failed")

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(CollectorError, match="Failed to fetch Jibe postings"):
        collect_jibe_jobs(_company_config())


def test_collect_jibe_jobs_requires_json_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(
        url: str,
        headers: dict[str, str],
        timeout: int,
    ) -> FakeResponse:
        return FakeResponse(payload=[])

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(CollectorError, match="Jibe response is not a JSON object"):
        collect_jibe_jobs(_company_config())