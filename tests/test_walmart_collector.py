"""Verify profile-scoped Walmart collection, pagination, and job details."""

from __future__ import annotations

import pytest
import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.walmart import (
    DETAIL_QUERY_ID,
    SEARCH_QUERY_ID,
    collect_walmart_jobs,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


def _config(**overrides):
    config = {
        "company_key": "walmart",
        "name": "Walmart",
        "source_type": "walmart",
        "source_url": "https://careers.walmart.com/api/graphql",
        "walmart_target_roles": ["Platform Engineer"],
        "walmart_locations": ["Colorado", "Remote"],
        "max_pages": 3,
    }
    config.update(overrides)
    return config


def _search_payload(page, jobs, total=3, refined="platform engineer"):
    return {
        "data": {
            "jobSearchAssistant": {
                "thread_id": "S-test-thread",
                "tool_messages": [
                    {
                        "artifact": {
                            "status": "success",
                            "job_page_number": page,
                            "page_size": 10,
                            "total_jobs": total,
                            "refined_query": refined,
                            "filters": "primaryLocationState == 'CO'",
                            "jobs": jobs,
                        }
                    }
                ],
            }
        }
    }


def _detail_payload(ids):
    return {
        "data": {
            "bulkUnifiedJobDetails": [
                {
                    "jobId": job_id,
                    "jobPostingTitle": f"Platform Engineer {job_id}",
                    "description": "<p>Operate Kubernetes platforms.</p>",
                }
                for job_id in ids
            ]
        }
    }


def test_collect_walmart_jobs_exhausts_scoped_pages_and_fetches_details(monkeypatch):
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append(json)
        assert url == "https://careers.walmart.com/api/graphql"
        assert headers["Referer"].startswith("https://careers.walmart.com")
        assert timeout == 90
        if json["queryId"] == SEARCH_QUERY_ID:
            context = json["variables"]["chatRequest"]["context"]["job_search_context"]
            page = context["job_page"]
            if page == 0:
                message = json["variables"]["chatRequest"]["messages"][0]["content"][0]["text"]
                assert message == "Platform Engineer jobs in Colorado or Remote"
                return FakeResponse(
                    _search_payload(
                        0,
                            [
                                {
                                    "job_id": f"R-{index}",
                                    "city": "Denver",
                                    "state": "CO",
                                    "country": "US",
                                }
                                for index in range(1, 11)
                            ],
                            total=11,
                    )
                )
            assert context["refined_query"] == "platform engineer"
            assert context["filters"] == "primaryLocationState == 'CO'"
            assert (
                json["variables"]["chatRequest"]["messages"][0]["content"][0][
                    "text"
                ]
                == "Show me page number 2"
            )
            return FakeResponse(
                _search_payload(
                    1,
                    [{"job_id": "R-11", "city": "Remote", "country": "US"}],
                    total=11,
                )
            )
        assert json["queryId"] == DETAIL_QUERY_ID
        return FakeResponse(
            _detail_payload(json["variables"]["jobIds"].split(","))
        )

    monkeypatch.setattr(requests, "post", fake_post)

    jobs = collect_walmart_jobs(_config())

    assert [job.source_job_id for job in jobs] == [
        *(f"R-{index}" for index in range(1, 11)),
        "R-11",
    ]
    assert all(job.description == "Operate Kubernetes platforms." for job in jobs)
    assert jobs[0].source_url == "https://careers.walmart.com/us/en/jobs/R-1"
    assert len([call for call in calls if call["queryId"] == SEARCH_QUERY_ID]) == 2


def test_collect_walmart_jobs_requires_profile_roles():
    with pytest.raises(CollectorError, match="target role"):
        collect_walmart_jobs(_config(walmart_target_roles=[]))


def test_collect_walmart_jobs_rejects_truncated_scope(monkeypatch):
    def fake_post(url, *, json, headers, timeout):
        if json["queryId"] == SEARCH_QUERY_ID:
            page = json["variables"]["chatRequest"]["context"][
                "job_search_context"
            ]["job_page"]
            return FakeResponse(
                _search_payload(
                    page,
                    (
                        [{"job_id": "R-1", "city": "Denver", "state": "CO"}]
                        if page == 0
                        else []
                    ),
                    total=2,
                )
            )
        return FakeResponse(_detail_payload(["R-1"]))

    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(CollectorError, match="ended its scoped results"):
        collect_walmart_jobs(_config())


def test_collect_walmart_connection_test_is_intentionally_bounded(monkeypatch):
    def fake_post(url, *, json, headers, timeout):
        if json["queryId"] == SEARCH_QUERY_ID:
            return FakeResponse(
                _search_payload(
                    0,
                    [{"job_id": "R-1", "city": "Denver", "state": "CO"}],
                    total=50,
                )
            )
        return FakeResponse(_detail_payload(["R-1"]))

    monkeypatch.setattr(requests, "post", fake_post)

    jobs = collect_walmart_jobs(_config(connection_test=True, max_pages=1))

    assert [job.source_job_id for job in jobs] == ["R-1"]
