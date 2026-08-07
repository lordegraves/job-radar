"""Verify Eightfold public search results become normalized Junior jobs."""

import threading

import pytest
import requests

from job_radar.collectors.eightfold import collect_eightfold_jobs
from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.incremental_cache import DETAIL_PLANNER_CONFIG_KEY
from job_radar.detail_retrieval import DetailRetrievalDecision


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_eightfold_prefetches_known_result_pages_with_two_workers(monkeypatch) -> None:
    barrier = threading.Barrier(2)
    starts: list[int] = []

    def fake_get_response(url, **kwargs):
        if not url.endswith("/api/pcsx/search"):
            raise AssertionError("Unrelated summaries must not fetch details.")
        start = kwargs["params"]["start"]
        starts.append(start)
        if start in {20, 40}:
            barrier.wait(timeout=1)
        positions = [
            {
                "id": start + offset + 1,
                "name": f"Sales Role {start + offset}",
                "positionUrl": f"/careers/job/{start + offset + 1}",
            }
            for offset in range(20)
        ]
        return _Response({"data": {"count": 60, "positions": positions}})

    monkeypatch.setattr(
        "job_radar.collectors.eightfold.get_response",
        fake_get_response,
    )
    jobs = collect_eightfold_jobs(
        {
            "company_key": "example",
            "name": "Example",
            "source_url": "https://apply.example.com",
            "domain": "example.com",
            "max_pages": 3,
            DETAIL_PLANNER_CONFIG_KEY: lambda _title, _location: (
                DetailRetrievalDecision(False, "clearly unrelated")
            ),
        }
    )

    assert len(jobs) == 60
    assert sorted(starts) == [0, 20, 40]


def test_eightfold_collector_fetches_search_and_detail(monkeypatch) -> None:
    calls = []

    def fake_get_response(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/api/pcsx/search"):
            return _Response(
                {
                    "data": {
                        "count": 1,
                        "positions": [
                            {
                                "id": 123,
                                "displayJobId": "JR-123",
                                "name": "Platform Engineer",
                                "locations": ["Colorado, United States"],
                                "positionUrl": "/careers/job/123",
                            }
                        ],
                    }
                }
            )
        return _Response(
            {
                "data": {
                    "displayJobId": "JR-123",
                    "locations": ["Colorado, United States"],
                    "jobDescription": "<p>Operate reliable systems.</p>",
                    "workLocationOption": "hybrid",
                }
            }
        )

    monkeypatch.setattr(
        "job_radar.collectors.eightfold.get_response",
        fake_get_response,
    )
    jobs = collect_eightfold_jobs(
        {
            "company_key": "example",
            "name": "Example",
            "source_type": "eightfold",
            "source_url": "https://apply.example.com",
            "domain": "example.com",
        }
    )

    assert len(jobs) == 1
    assert jobs[0].title == "Platform Engineer"
    assert jobs[0].description == "Operate reliable systems."
    assert jobs[0].remote_status == "hybrid"
    assert jobs[0].source_url == "https://apply.example.com/careers/job/123"
    assert calls[0][1]["params"]["domain"] == "example.com"
    assert calls[1][1]["params"]["position_id"] == "123"


def test_eightfold_skips_unrelated_position_detail(monkeypatch) -> None:
    calls = []

    def fake_get_response(url, **kwargs):
        calls.append(url)
        assert url.endswith("/api/pcsx/search")
        return _Response(
            {
                "data": {
                    "count": 1,
                    "positions": [
                        {
                            "id": 456,
                            "displayJobId": "JR-456",
                            "name": "Senior Tax Accountant",
                            "locations": ["Washington, United States"],
                            "positionUrl": "/careers/job/456",
                        }
                    ],
                }
            }
        )

    monkeypatch.setattr(
        "job_radar.collectors.eightfold.get_response",
        fake_get_response,
    )
    jobs = collect_eightfold_jobs(
        {
            "company_key": "example",
            "name": "Example",
            "source_type": "eightfold",
            "source_url": "https://apply.example.com",
            "domain": "example.com",
            DETAIL_PLANNER_CONFIG_KEY: lambda title, location: (
                DetailRetrievalDecision(False, "clearly unrelated")
            ),
        }
    )

    assert calls == ["https://apply.example.com/api/pcsx/search"]
    assert len(jobs) == 1
    assert jobs[0].detail_retrieval_reason == "clearly unrelated"
    assert jobs[0].detail_retrieval_state == "skipped_unrelated"


def test_microsoft_url_detects_eightfold_source() -> None:
    from job_radar.employer_resolution_service import detect_employer_source

    result = detect_employer_source(
        "https://careers.microsoft.com/v2/global/en/home.html"
    )

    assert result.scan_ready is True
    assert result.source_type == "eightfold"
    assert result.source_config["source_url"] == (
        "https://apply.careers.microsoft.com"
    )
    assert result.source_config["display_name"] == "Microsoft"


def test_eightfold_connection_test_reads_only_one_search_page(monkeypatch) -> None:
    calls = []

    def fake_get_response(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/api/pcsx/search"):
            return _Response(
                {
                    "data": {
                        "count": 1,
                        "positions": [
                            {
                                "id": 123,
                                "displayJobId": "JR-123",
                                "name": "Platform Engineer",
                                "locations": ["Colorado, United States"],
                                "positionUrl": "/careers/job/123",
                            }
                        ],
                    }
                }
            )
        return _Response(
            {
                "data": {
                    "displayJobId": "JR-123",
                    "locations": ["Colorado, United States"],
                    "jobDescription": "Operate reliable systems.",
                }
            }
        )

    monkeypatch.setattr(
        "job_radar.collectors.eightfold.get_response",
        fake_get_response,
    )

    jobs = collect_eightfold_jobs(
        {
            "company_key": "example",
            "name": "Example",
            "source_type": "eightfold",
            "source_url": "https://apply.example.com",
            "domain": "example.com",
            "max_pages": 1,
            "connection_test": True,
        }
    )

    assert len(jobs) == 1
    assert len(calls) == 2
    assert calls[0][0].endswith("/api/pcsx/search")
    assert calls[1][0].endswith("/api/pcsx/position_details")


def test_eightfold_retries_temporary_detail_failure(monkeypatch) -> None:
    response = requests.Response()
    response.status_code = 429
    detail_calls = 0

    def fake_get_response(url, **kwargs):
        nonlocal detail_calls
        if url.endswith("/api/pcsx/search"):
            return _Response(
                {
                    "data": {
                        "count": 1,
                        "positions": [
                            {
                                "id": 123,
                                "name": "Platform Engineer",
                                "positionUrl": "/careers/job/123",
                            }
                        ],
                    }
                }
            )
        detail_calls += 1
        if detail_calls < 3:
            raise requests.HTTPError("private response text", response=response)
        return _Response(
            {
                "data": {
                    "displayJobId": "JR-123",
                    "jobDescription": "Operate reliable systems.",
                }
            }
        )

    monkeypatch.setattr(
        "job_radar.collectors.eightfold.get_response",
        fake_get_response,
    )
    monkeypatch.setattr("job_radar.collectors.eightfold.time.sleep", lambda _: None)

    jobs = collect_eightfold_jobs(
        {
            "company_key": "example",
            "name": "Example",
            "source_url": "https://apply.example.com",
            "domain": "example.com",
        }
    )

    assert len(jobs) == 1
    assert jobs[0].description == "Operate reliable systems."
    assert detail_calls == 3


def test_eightfold_opens_detail_circuit_and_keeps_all_listings(monkeypatch) -> None:
    from job_radar.collectors.incremental_cache import WARNINGS_CONFIG_KEY

    detail_calls = 0

    def fake_get_response(url, **kwargs):
        nonlocal detail_calls
        if url.endswith("/api/pcsx/search"):
            return _Response(
                {
                    "data": {
                        "count": 5,
                        "positions": [
                            {
                                "id": number,
                                "name": f"Platform Engineer {number}",
                                "positionUrl": f"/careers/job/{number}",
                                "descriptionTeaser": "Operate reliable systems.",
                            }
                            for number in range(1, 6)
                        ],
                    }
                }
            )
        detail_calls += 1
        assert kwargs["timeout"] == 10
        raise requests.ConnectionError("private response text")

    monkeypatch.setattr(
        "job_radar.collectors.eightfold.get_response",
        fake_get_response,
    )
    config = {
        "company_key": "example",
        "name": "Example",
        "source_url": "https://apply.example.com",
        "domain": "example.com",
    }

    jobs = collect_eightfold_jobs(config)

    assert len(jobs) == 5
    assert detail_calls == 3
    assert all(job.description == "Operate reliable systems." for job in jobs)
    assert all(job.detail_retrieval_state == "unavailable" for job in jobs)
    assert len(config[WARNINGS_CONFIG_KEY]) == 1
    assert "evaluated conservatively as incomplete" in config[WARNINGS_CONFIG_KEY][0]


def test_eightfold_connection_test_still_fails_when_detail_is_unavailable(
    monkeypatch,
) -> None:
    def fake_get_response(url, **kwargs):
        if url.endswith("/api/pcsx/search"):
            return _Response(
                {
                    "data": {
                        "count": 1,
                        "positions": [
                            {
                                "id": 1,
                                "name": "Platform Engineer",
                                "positionUrl": "/careers/job/1",
                            }
                        ],
                    }
                }
            )
        raise requests.ConnectionError("private response text")

    monkeypatch.setattr(
        "job_radar.collectors.eightfold.get_response",
        fake_get_response,
    )

    with pytest.raises(CollectorError, match="position details"):
        collect_eightfold_jobs(
            {
                "company_key": "example",
                "name": "Example",
                "source_url": "https://apply.example.com",
                "domain": "example.com",
                "connection_test": True,
                "max_pages": 1,
            }
        )


def test_cached_eightfold_retry_uses_internal_position_id_from_url(
    monkeypatch,
) -> None:
    from job_radar.collectors.eightfold import enrich_cached_eightfold_posting
    from job_radar.models import JobPosting

    requested_ids: list[str] = []

    def fake_detail(**kwargs):
        requested_ids.append(kwargs["position_id"])
        return {
            "jobDescription": "Operate reliable infrastructure. " * 10,
            "locations": ["United States"],
        }

    monkeypatch.setattr(
        "job_radar.collectors.eightfold._fetch_position_detail",
        fake_detail,
    )
    posting = JobPosting(
        company_key="microsoft",
        company_name="Microsoft",
        source_type="eightfold",
        source_url="https://apply.careers.microsoft.com/careers/job/1970393556957615",
        source_job_id="200047236",
        title="Platform Engineer",
        location="United States",
        description="Short summary",
    )

    enriched = enrich_cached_eightfold_posting(
        posting,
        {
            "source_url": "https://apply.careers.microsoft.com",
            "domain": "microsoft.com",
            "name": "Microsoft",
        },
    )

    assert requested_ids == ["1970393556957615"]
    assert enriched.detail_retrieval_state is None
    assert len(enriched.description or "") >= 200


def test_eightfold_reuses_fresh_unchanged_detail(monkeypatch) -> None:
    from datetime import UTC, datetime

    from job_radar.collectors.incremental_cache import (
        CACHE_CONFIG_KEY,
        listing_fingerprint,
    )
    from job_radar.models import JobPosting
    from job_radar.storage import CachedSourcePosting

    raw_position = {
        "id": 123,
        "name": "Platform Engineer",
        "locations": ["Remote"],
        "positionUrl": "/careers/job/123",
    }
    fingerprint = listing_fingerprint(
        {
            "id": "123",
            "title": "Platform Engineer",
            "path": "/careers/job/123",
                "locations": ["Remote"],
                "workstyle": None,
            }
        )
    cached = CachedSourcePosting(
        posting=JobPosting(
            company_key="example",
            company_name="Example",
            source_type="eightfold",
            source_job_id="123",
            source_url="https://apply.example.com/careers/job/123",
            title="Platform Engineer",
            location="Remote",
            description="Complete cached responsibilities and qualifications. " * 8,
            canonical_key="example",
            content_hash="cached",
        ),
        listing_fingerprint=fingerprint,
        detail_verified_at=datetime.now(UTC).isoformat(),
    )

    def fake_get_response(url, **kwargs):
        if url.endswith("/api/pcsx/search"):
            return _Response(
                {"data": {"count": 1, "positions": [raw_position]}}
            )
        raise AssertionError("detail request was not skipped")

    monkeypatch.setattr(
        "job_radar.collectors.eightfold.get_response",
        fake_get_response,
    )
    jobs = collect_eightfold_jobs(
        {
            "company_key": "example",
            "name": "Example",
            "source_type": "eightfold",
            "source_url": "https://apply.example.com",
            "domain": "example.com",
            CACHE_CONFIG_KEY: {"123": cached},
        }
    )

    assert jobs[0].description == (
        "Complete cached responsibilities and qualifications. " * 8
    )


def test_eightfold_reuses_fresh_detail_when_summary_metadata_changes(
    monkeypatch,
) -> None:
    from datetime import UTC, datetime

    from job_radar.collectors.incremental_cache import CACHE_CONFIG_KEY
    from job_radar.models import JobPosting
    from job_radar.storage import CachedSourcePosting

    raw_position = {
        "id": 123,
        "displayJobId": "JR123",
        "name": "Platform Engineer",
        "locations": ["Remote - United States"],
        "positionUrl": "/careers/job/123",
        "efcustomTextJobRequisitionWorkstyle": "Remote",
    }
    cached = CachedSourcePosting(
        posting=JobPosting(
            company_key="example",
            company_name="Example",
            source_type="eightfold",
            source_job_id="JR123",
            source_url="https://apply.example.com/careers/job/123",
            title="Platform Engineer",
            location="United States, Multiple Locations",
            description="Complete cached responsibilities and qualifications. " * 8,
            canonical_key="example",
            content_hash="cached",
        ),
        listing_fingerprint="older-summary-metadata",
        detail_verified_at=datetime.now(UTC).isoformat(),
    )

    def fake_get_response(url, **kwargs):
        if url.endswith("/api/pcsx/search"):
            return _Response({"data": {"count": 1, "positions": [raw_position]}})
        raise AssertionError("fresh cached detail should avoid a detail request")

    monkeypatch.setattr(
        "job_radar.collectors.eightfold.get_response",
        fake_get_response,
    )
    jobs = collect_eightfold_jobs(
        {
            "company_key": "example",
            "name": "Example",
            "source_type": "eightfold",
            "source_url": "https://apply.example.com",
            "domain": "example.com",
            CACHE_CONFIG_KEY: {"JR123": cached},
        }
    )

    assert jobs[0].description == cached.posting.description
    assert jobs[0].location == "Remote - United States"
    assert jobs[0].remote_status == "Remote"


def test_eightfold_uses_actual_server_page_size_and_keeps_fetching(
    monkeypatch,
) -> None:
    starts = []

    def fake_get_response(url, **kwargs):
        if url.endswith("/api/pcsx/search"):
            start = kwargs["params"]["start"]
            starts.append(start)
            positions = (
                [
                    {
                            "id": start + offset + 1,
                            "name": f"Role {start + offset + 1}",
                            "positionUrl": f"/careers/job/{start + offset + 1}",
                    }
                    for offset in range(10)
                ]
                if start < 20
                else []
            )
            return _Response({"data": {"count": 20, "positions": positions}})
        position_id = kwargs["params"]["position_id"]
        return _Response(
            {
                "data": {
                    "displayJobId": str(position_id),
                    "locations": ["Spring, Texas, United States"],
                    "jobDescription": "Analyze business data.",
                    "workLocationOption": "onsite",
                    "efcustomTextJobRequisitionWorkstyle": "Flex",
                }
            }
        )

    monkeypatch.setattr(
        "job_radar.collectors.eightfold.get_response",
        fake_get_response,
    )
    jobs = collect_eightfold_jobs(
        {
            "company_key": "example",
            "name": "Example",
            "source_type": "eightfold",
            "source_url": "https://apply.example.com",
            "domain": "example.com",
        }
    )

    assert len(jobs) == 20
    assert starts == [0, 10]
    assert all(job.remote_status == "Flex" for job in jobs)


def test_eightfold_ignores_false_zero_total_on_later_page(monkeypatch) -> None:
    starts = []

    def fake_get_response(url, **kwargs):
        if not url.endswith("/api/pcsx/search"):
            raise AssertionError("Connection-test mode must not fetch details.")
        start = kwargs["params"]["start"]
        starts.append(start)
        if start >= 30:
            return _Response({"data": {"count": 0, "positions": []}})
        positions = [
            {
                "id": start + offset + 1,
                "name": f"Role {start + offset + 1}",
                "positionUrl": f"/careers/job/{start + offset + 1}",
            }
            for offset in range(10)
        ]
        return _Response(
            {
                "data": {
                    "count": 30 if start == 0 else 0,
                    "positions": positions,
                }
            }
        )

    monkeypatch.setattr(
        "job_radar.collectors.eightfold.get_response",
        fake_get_response,
    )
    jobs = collect_eightfold_jobs(
        {
            "company_key": "example",
            "name": "Example",
            "source_type": "eightfold",
            "source_url": "https://apply.example.com",
            "domain": "example.com",
            "connection_test": True,
        }
    )

    assert len(jobs) == 30
    assert starts == [0, 10, 20]


def test_eightfold_stops_when_source_repeats_a_page(monkeypatch) -> None:
    starts = []

    def fake_get_response(url, **kwargs):
        if not url.endswith("/api/pcsx/search"):
            raise AssertionError("Connection-test mode must not fetch details.")
        start = kwargs["params"]["start"]
        starts.append(start)
        positions = [
            {
                "id": offset + 1,
                "name": f"Role {offset + 1}",
                "positionUrl": f"/careers/job/{offset + 1}",
            }
            for offset in range(10)
        ]
        return _Response({"data": {"count": 50, "positions": positions}})

    monkeypatch.setattr(
        "job_radar.collectors.eightfold.get_response",
        fake_get_response,
    )
    jobs = collect_eightfold_jobs(
        {
            "company_key": "example",
            "name": "Example",
            "source_type": "eightfold",
            "source_url": "https://apply.example.com",
            "domain": "example.com",
            "connection_test": True,
        }
    )

    assert len(jobs) == 10
    assert starts == [0, 10]


def test_eightfold_records_initial_search_request_failure_stage(monkeypatch) -> None:
    response = requests.Response()
    response.status_code = 429

    def fake_get_response(url, **kwargs):
        raise requests.HTTPError("private response text", response=response)

    monkeypatch.setattr(
        "job_radar.collectors.eightfold.get_response",
        fake_get_response,
    )

    with pytest.raises(CollectorError) as caught:
        collect_eightfold_jobs(
            {
                "company_key": "example",
                "name": "Example",
                "source_url": "https://apply.example.com",
                "domain": "example.com",
            }
        )

    assert caught.value.failure_stage == "initial_search_request"


def test_eightfold_records_later_results_request_failure_stage(monkeypatch) -> None:
    response = requests.Response()
    response.status_code = 429
    calls = 0

    def fake_get_response(url, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _Response(
                {
                    "data": {
                        "count": 20,
                        "positions": [
                            {
                                "id": index,
                                "name": f"Role {index}",
                                "positionUrl": f"/careers/job/{index}",
                            }
                            for index in range(10)
                        ],
                    }
                }
            )
        raise requests.HTTPError("private response text", response=response)

    monkeypatch.setattr(
        "job_radar.collectors.eightfold.get_response",
        fake_get_response,
    )

    with pytest.raises(CollectorError) as caught:
        collect_eightfold_jobs(
            {
                "company_key": "example",
                "name": "Example",
                "source_url": "https://apply.example.com",
                "domain": "example.com",
                "connection_test": True,
            }
        )

    assert caught.value.failure_stage == "results_pagination_request"


def test_eightfold_retries_rate_limited_results_page(monkeypatch) -> None:
    response = requests.Response()
    response.status_code = 429
    response.headers["Retry-After"] = "3"
    search_calls = 0
    delays = []

    def fake_get_response(url, **kwargs):
        nonlocal search_calls
        if url.endswith("/api/pcsx/position_details"):
            position_id = kwargs["params"]["position_id"]
            return _Response(
                {
                    "data": {
                        "displayJobId": str(position_id),
                        "jobDescription": "Operate reliable systems.",
                    }
                }
            )
        search_calls += 1
        start = kwargs["params"]["start"]
        if search_calls == 2:
            raise requests.HTTPError("rate limited", response=response)
        positions = (
            [
                {
                    "id": start + 1,
                    "name": f"Role {start + 1}",
                    "positionUrl": f"/careers/job/{start + 1}",
                }
            ]
            if start < 2
            else []
        )
        return _Response(
            {"data": {"count": 2, "positions": positions}}
        )

    monkeypatch.setattr(
        "job_radar.collectors.eightfold.get_response",
        fake_get_response,
    )
    monkeypatch.setattr(
        "job_radar.collectors.eightfold.time.sleep",
        delays.append,
    )

    jobs = collect_eightfold_jobs(
        {
            "company_key": "example",
            "name": "Example",
            "source_url": "https://apply.example.com",
            "domain": "example.com",
            "max_pages": 3,
        }
    )

    assert len(jobs) == 2
    assert 3.0 in delays
