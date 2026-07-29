"""Tests Workday pagination, response parsing, normalized jobs, and failures."""

import pytest
import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.workday import (
    collect_workday_jobs,
    parse_workday_jobs,
)


@pytest.fixture(autouse=True)
def _prevent_unmocked_workday_detail_requests(monkeypatch):
    """Keep collector tests isolated unless a test supplies a detail response."""

    def fail_detail_request(*args, **kwargs):
        raise requests.RequestException("detail request not configured")

    monkeypatch.setattr(
        "job_radar.collectors.workday.requests.get",
        fail_detail_request,
    )


def test_parse_workday_jobs_returns_job_postings() -> None:
    company_config = {
        "company_key": "example_company",
        "name": "Example Company",
        "source_type": "workday",
        "source_url": "https://example.wd1.myworkdayjobs.com/wday/cxs/example/External/jobs",
        "source_base_url": "https://example.wd1.myworkdayjobs.com/External",
        "enabled": True,
    }

    payload = {
        "total": 1,
        "jobPostings": [
            {
                "title": "Senior Infrastructure Engineer",
                "externalPath": "/job/Remote/Senior-Infrastructure-Engineer_R123",
                "locationsText": "Remote",
                "bulletFields": ["R123"],
                "description": "Build and operate Linux infrastructure.",
            }
        ],
    }

    postings = parse_workday_jobs(company_config, payload)

    assert len(postings) == 1

    posting = postings[0]

    assert posting.company_key == "example_company"
    assert posting.company_name == "Example Company"
    assert posting.source_type == "workday"
    assert posting.source_job_id == "R123"
    assert (
        posting.source_url
        == "https://example.wd1.myworkdayjobs.com/External/job/Remote/Senior-Infrastructure-Engineer_R123"
    )
    assert posting.title == "Senior Infrastructure Engineer"
    assert posting.location == "Remote"
    assert posting.description == "Build and operate Linux infrastructure."
    assert (
        posting.canonical_key
        == "example-company:senior-infrastructure-engineer:remote"
    )
    assert posting.content_hash is not None


def test_parse_workday_jobs_uses_external_url_when_present() -> None:
    company_config = {
        "company_key": "example_company",
        "name": "Example Company",
        "source_type": "workday",
        "source_url": "https://example.wd1.myworkdayjobs.com/wday/cxs/example/External/jobs",
        "enabled": True,
    }

    payload = {
        "total": 1,
        "jobPostings": [
            {
                "title": "Infrastructure Engineer",
                "externalUrl": "https://example.com/job/R123",
                "locationsText": "Remote",
                "bulletFields": ["R123"],
            }
        ],
    }

    postings = parse_workday_jobs(company_config, payload)

    assert len(postings) == 1
    assert postings[0].source_url == "https://example.com/job/R123"


def test_parse_workday_jobs_skips_jobs_missing_title() -> None:
    company_config = {
        "company_key": "example_company",
        "name": "Example Company",
        "source_type": "workday",
        "source_base_url": "https://example.wd1.myworkdayjobs.com/External",
    }

    payload = {
        "total": 1,
        "jobPostings": [
            {
                "externalPath": "/job/Remote/Missing-Title_R123",
                "locationsText": "Remote",
            }
        ],
    }

    postings = parse_workday_jobs(company_config, payload)

    assert postings == []


def test_parse_workday_jobs_skips_jobs_missing_url() -> None:
    company_config = {
        "company_key": "example_company",
        "name": "Example Company",
        "source_type": "workday",
    }

    payload = {
        "total": 1,
        "jobPostings": [
            {
                "title": "Infrastructure Engineer",
                "locationsText": "Remote",
            }
        ],
    }

    postings = parse_workday_jobs(company_config, payload)

    assert postings == []


def test_parse_workday_jobs_rejects_payload_without_job_postings() -> None:
    company_config = {
        "company_key": "example_company",
        "name": "Example Company",
        "source_type": "workday",
    }

    with pytest.raises(CollectorError, match="jobPostings list"):
        parse_workday_jobs(company_config, {"not_jobs": []})


def test_collect_workday_jobs_stops_at_configured_max_pages(
    monkeypatch,
) -> None:
    company_config = {
        "company_key": "example_company",
        "name": "Example Company",
        "source_type": "workday",
        "source_url": (
            "https://example.wd1.myworkdayjobs.com/"
            "wday/cxs/example/External/jobs"
        ),
        "source_base_url": "https://example.wd1.myworkdayjobs.com/External",
        "page_size": 1,
        "max_pages": 2,
    }
    captured_offsets: list[int] = []

    class FakeResponse:
        def __init__(self, offset: int) -> None:
            self.text = ""
            self._offset = offset

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            job_number = self._offset + 1

            return {
                "total": 100,
                "jobPostings": [
                    {
                        "title": f"Infrastructure Engineer {job_number}",
                        "externalPath": f"/job/Remote/Engineer_R{job_number}",
                        "locationsText": "Remote",
                        "bulletFields": [f"R{job_number}"],
                    }
                ],
            }

    def fake_post(url, json, headers, timeout):
        captured_offsets.append(json["offset"])
        return FakeResponse(json["offset"])

    monkeypatch.setattr(
        "job_radar.collectors.workday.requests.post",
        fake_post,
    )

    postings = collect_workday_jobs(company_config)

    assert captured_offsets == [0, 1]
    assert len(postings) == 2


def test_collect_workday_jobs_fetches_complete_job_detail(
    monkeypatch,
) -> None:
    company_config = {
        "company_key": "example_company",
        "name": "Example Company",
        "source_type": "workday",
        "source_url": (
            "https://example.wd1.myworkdayjobs.com/"
            "wday/cxs/example/External_Career/jobs"
        ),
        "source_base_url": "https://example.wd1.myworkdayjobs.com/External_Career",
        "page_size": 20,
        "max_pages": 1,
    }

    class SearchResponse:
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "total": 1,
                "jobPostings": [
                    {
                        "title": "Kubernetes Platform Architect",
                        "externalPath": (
                            "/job/United-Kingdom-Remote-Location/"
                            "Kubernetes-Platform-Architect_R025880"
                        ),
                        "locationsText": "United Kingdom-Remote Location",
                        "bulletFields": ["R025880"],
                    }
                ],
            }

    class DetailResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "jobPostingInfo": {
                    "title": "Kubernetes Platform Architect",
                    "jobDescription": (
                        "Required qualifications include platform architecture "
                        "leadership and Kubernetes product expertise. This role "
                        "requires travel up to 50 percent across customer sites."
                    ),
                    "location": "United Kingdom-Remote Location",
                    "jobReqId": "R025880",
                }
            }

    monkeypatch.setattr(
        "job_radar.collectors.workday.requests.post",
        lambda *args, **kwargs: SearchResponse(),
    )

    def fake_get(url, headers, timeout):
        assert url == (
            "https://example.wd1.myworkdayjobs.com/wday/cxs/example/"
            "External_Career/job/United-Kingdom-Remote-Location/"
            "Kubernetes-Platform-Architect_R025880"
        )
        assert headers["Accept"] == "application/json"
        assert timeout == 30
        return DetailResponse()

    monkeypatch.setattr(
        "job_radar.collectors.workday.requests.get",
        fake_get,
    )

    postings = collect_workday_jobs(company_config)

    assert len(postings) == 1
    assert postings[0].location == "United Kingdom-Remote Location"
    assert "travel up to 50 percent" in (postings[0].description or "")


def test_collect_workday_jobs_ignores_false_zero_total_on_later_pages(
    monkeypatch,
) -> None:
    company_config = {
        "company_key": "example_company",
        "name": "Example Company",
        "source_type": "workday",
        "source_url": (
            "https://example.wd1.myworkdayjobs.com/"
            "wday/cxs/example/External/jobs"
        ),
        "source_base_url": "https://example.wd1.myworkdayjobs.com/External",
        "page_size": 1,
        "max_pages": 5,
    }
    captured_offsets: list[int] = []

    class FakeResponse:
        def __init__(self, offset: int) -> None:
            self.text = ""
            self._offset = offset

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            job_number = self._offset + 1
            return {
                "total": 3 if self._offset == 0 else 0,
                "jobPostings": [
                    {
                        "title": f"Infrastructure Engineer {job_number}",
                        "externalPath": f"/job/Remote/Engineer_R{job_number}",
                        "locationsText": "Remote",
                        "bulletFields": [f"R{job_number}"],
                    }
                ],
            }

    def fake_post(url, json, headers, timeout):
        captured_offsets.append(json["offset"])
        return FakeResponse(json["offset"])

    monkeypatch.setattr(
        "job_radar.collectors.workday.requests.post",
        fake_post,
    )

    postings = collect_workday_jobs(company_config)

    assert captured_offsets == [0, 1, 2]
    assert len(postings) == 3


def test_collect_workday_jobs_stops_when_endpoint_repeats_a_page(
    monkeypatch,
) -> None:
    company_config = {
        "company_key": "example_company",
        "name": "Example Company",
        "source_type": "workday",
        "source_url": (
            "https://example.wd1.myworkdayjobs.com/"
            "wday/cxs/example/External/jobs"
        ),
        "source_base_url": "https://example.wd1.myworkdayjobs.com/External",
        "page_size": 1,
        "max_pages": 5,
    }
    captured_offsets: list[int] = []

    class FakeResponse:
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "total": 100,
                "jobPostings": [
                    {
                        "title": "Repeated Infrastructure Engineer",
                        "externalPath": "/job/Remote/Engineer_R1",
                        "locationsText": "Remote",
                        "bulletFields": ["R1"],
                    }
                ],
            }

    def fake_post(url, json, headers, timeout):
        captured_offsets.append(json["offset"])
        return FakeResponse()

    monkeypatch.setattr(
        "job_radar.collectors.workday.requests.post",
        fake_post,
    )

    postings = collect_workday_jobs(company_config)

    assert captured_offsets == [0, 1]
    assert len(postings) == 1
