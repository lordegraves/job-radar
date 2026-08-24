"""Tests Workday pagination, response parsing, normalized jobs, and failures."""

import pytest
import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.incremental_cache import DETAIL_PLANNER_CONFIG_KEY
from job_radar.collectors.workday import (
    WORKDAY_DETAIL_NORMALIZATION_VERSION,
    collect_workday_jobs,
    parse_workday_jobs,
)
from job_radar.detail_retrieval import DetailRetrievalDecision


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


def test_connection_test_walks_workday_results_without_detail_requests(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "job_radar.collectors.workday._fetch_workday_page",
        lambda source_url, *, payload: {
            "total": 1,
            "jobPostings": [
                {
                    "title": "Infrastructure Engineer",
                    "externalPath": "/job/Remote/Infrastructure_R123",
                    "bulletFields": ["R123"],
                    "locationsText": "Remote",
                }
            ],
        },
    )
    monkeypatch.setattr(
        "job_radar.collectors.workday._fetch_workday_detail",
        lambda *args, **kwargs: pytest.fail("detail request should be skipped"),
    )

    postings = collect_workday_jobs(
        {
            "company_key": "example",
            "name": "Example",
            "source_type": "workday",
            "source_url": "https://example.test/wday/cxs/example/jobs/jobs",
            "source_base_url": "https://example.test/jobs",
            "connection_test": True,
        }
    )

    assert len(postings) == 1
    assert postings[0].source_job_id == "R123"


def test_parse_workday_jobs_uses_external_path_for_placeholder_job_id() -> None:
    company_config = {
        "company_key": "intel",
        "name": "Intel",
        "source_type": "workday",
        "source_url": "https://intel.wd1.myworkdayjobs.com/wday/cxs/intel/jobs",
        "source_base_url": "https://intel.wd1.myworkdayjobs.com/External",
    }
    external_path = "/job/US/Infrastructure-Engineer_JR123"

    postings = parse_workday_jobs(
        company_config,
        {
            "jobPostings": [
                {
                    "title": "Infrastructure Engineer",
                    "externalPath": external_path,
                    "bulletFields": ["Spotlight Job"],
                    "locationsText": "US",
                }
            ]
        },
    )

    assert postings[0].source_job_id == external_path


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


def test_parse_workday_jobs_derives_missing_public_base_url() -> None:
    company_config = {
        "company_key": "intel",
        "name": "Intel",
        "source_type": "workday",
        "source_url": (
            "https://intel.wd1.myworkdayjobs.com/"
            "wday/cxs/intel/External/jobs"
        ),
    }
    external_path = "/job/US/Infrastructure-Engineer_JR123"

    postings = parse_workday_jobs(
        company_config,
        {
            "jobPostings": [
                {
                    "title": "Infrastructure Engineer",
                    "externalPath": external_path,
                    "locationsText": "US",
                }
            ]
        },
    )

    assert len(postings) == 1
    assert postings[0].source_url == (
        "https://intel.wd1.myworkdayjobs.com/External" + external_path
    )


def test_parse_workday_jobs_does_not_derive_untrusted_base_url() -> None:
    company_config = {
        "company_key": "example_company",
        "name": "Example Company",
        "source_type": "workday",
        "source_url": "https://example.com/wday/cxs/example/External/jobs",
    }

    postings = parse_workday_jobs(
        company_config,
        {
            "jobPostings": [
                {
                    "title": "Infrastructure Engineer",
                    "externalPath": "/job/US/Engineer_R123",
                    "locationsText": "US",
                }
            ]
        },
    )

    assert postings == []


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
                        "timeType": "Full time",
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
                    "timeType": "Full time",
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
    assert "Employment type: Full time" in (postings[0].description or "")


def test_collect_workday_jobs_fetches_detail_when_site_is_named_jobs(
    monkeypatch,
) -> None:
    company_config = {
        "company_key": "red_hat",
        "name": "Red Hat",
        "source_type": "workday",
        "source_url": (
            "https://redhat.wd5.myworkdayjobs.com/wday/cxs/redhat/jobs/jobs"
        ),
        "source_base_url": "https://redhat.wd5.myworkdayjobs.com/jobs",
        "max_pages": 1,
    }

    class Response:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    monkeypatch.setattr(
        "job_radar.collectors.workday.requests.post",
        lambda *args, **kwargs: Response(
            {
                "total": 1,
                "jobPostings": [
                    {
                        "title": "Technical Account Manager",
                        "externalPath": (
                            "/job/Remote-US/Technical-Account-Manager_R-123"
                        ),
                        "locationsText": "Remote US",
                        "bulletFields": ["R-123"],
                    }
                ],
            }
        ),
    )

    def fake_get(url, headers, timeout):
        assert url == (
            "https://redhat.wd5.myworkdayjobs.com/wday/cxs/redhat/jobs/"
            "job/Remote-US/Technical-Account-Manager_R-123"
        )
        return Response(
            {
                "jobPostingInfo": {
                    "title": "Technical Account Manager",
                    "jobReqId": "R-123",
                    "location": "Remote US",
                    "jobDescription": "Required experience supporting Linux customers.",
                }
            }
        )

    monkeypatch.setattr("job_radar.collectors.workday.requests.get", fake_get)

    postings = collect_workday_jobs(company_config)

    assert len(postings) == 1
    assert postings[0].description == (
        "Required experience supporting Linux customers."
    )


def test_collect_workday_jobs_retries_one_transient_detail_failure(
    monkeypatch,
) -> None:
    company_config = {
        "company_key": "woodward",
        "name": "Woodward",
        "source_type": "workday",
        "source_url": (
            "https://woodward.wd5.myworkdayjobs.com/"
            "wday/cxs/woodward/woodward/jobs"
        ),
        "source_base_url": "https://woodward.wd5.myworkdayjobs.com/woodward",
        "max_pages": 1,
    }

    class SearchResponse:
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "total": 1,
                "jobPostings": [
                    {
                        "title": "Operations Supervisor",
                        "locationsText": "Niles, IL, US",
                        "bulletFields": ["JR112720"],
                        "externalPath": (
                            "/job/Niles-IL-US/Operations-Supervisor_JR112720-1"
                        ),
                    }
                ],
            }

    class DetailResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "jobPostingInfo": {
                    "title": "Operations Supervisor",
                    "location": "Niles, IL, US",
                    "jobDescription": "Required qualifications. " + "Operations " * 30,
                }
            }

    detail_attempts = 0

    def fake_get(*_args, **_kwargs):
        nonlocal detail_attempts
        detail_attempts += 1
        if detail_attempts == 1:
            raise requests.ConnectionError("temporary edge failure")
        return DetailResponse()

    monkeypatch.setattr(
        "job_radar.collectors.workday.requests.post",
        lambda *args, **kwargs: SearchResponse(),
    )
    monkeypatch.setattr(
        "job_radar.collectors.workday.requests.get",
        fake_get,
    )
    monkeypatch.setattr(
        "job_radar.collectors.workday.time.sleep",
        lambda _delay: None,
    )

    postings = collect_workday_jobs(company_config)

    assert detail_attempts == 2
    assert postings[0].description.startswith("Required qualifications")


def test_collect_workday_jobs_retries_detail_with_bounded_backoff(
    monkeypatch,
) -> None:
    company_config = {
        "company_key": "example_company",
        "name": "Example Company",
        "source_type": "workday",
        "source_url": "https://example.test/wday/cxs/example/External/jobs",
        "source_base_url": "https://example.test/External",
        "max_pages": 1,
    }
    attempts = 0
    delays: list[float] = []

    class SearchResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "total": 1,
                "jobPostings": [
                    {
                        "title": "Infrastructure Engineer",
                        "locationsText": "Remote",
                        "externalPath": "/job/Remote/Engineer_R1",
                        "bulletFields": ["R1"],
                    }
                ],
            }

    class DetailResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "jobPostingInfo": {
                    "jobDescription": "Required Linux experience. " * 10,
                }
            }

    def fake_get(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts < 4:
            raise requests.ConnectionError("test-only transient failure")
        return DetailResponse()

    monkeypatch.setattr(
        "job_radar.collectors.workday.requests.post",
        lambda *args, **kwargs: SearchResponse(),
    )
    monkeypatch.setattr("job_radar.collectors.workday.requests.get", fake_get)
    monkeypatch.setattr("job_radar.collectors.workday.time.sleep", delays.append)

    postings = collect_workday_jobs(company_config)

    assert attempts == 4
    assert delays == [0.5, 1.0, 2.0]
    assert postings[0].description.startswith("Required Linux experience")


def test_collect_workday_jobs_retries_transient_search_page_failure(
    monkeypatch,
) -> None:
    company_config = {
        "company_key": "example_company",
        "name": "Example Company",
        "source_type": "workday",
        "source_url": "https://example.test/wday/cxs/example/External/jobs",
        "source_base_url": "https://example.test/External",
        "max_pages": 1,
    }
    attempts = 0

    class SearchResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "total": 1,
                "jobPostings": [
                    {
                        "title": "Infrastructure Engineer",
                        "locationsText": "Remote",
                        "description": "Operate Linux infrastructure. " * 10,
                        "externalPath": "/job/Remote/Engineer_R1",
                        "bulletFields": ["R1"],
                    }
                ],
            }

    def fake_post(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise requests.ConnectionError("test-only transient failure")
        return SearchResponse()

    monkeypatch.setattr("job_radar.collectors.workday.requests.post", fake_post)
    monkeypatch.setattr("job_radar.collectors.workday.time.sleep", lambda _delay: None)

    postings = collect_workday_jobs(company_config)

    assert attempts == 2
    assert len(postings) == 1


def test_collect_workday_jobs_skips_detail_when_shared_planner_is_conclusive(
    monkeypatch,
) -> None:
    requests_seen: list[str] = []

    class SearchResponse:
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "total": 1,
                "jobPostings": [
                    {
                        "title": "Senior Tax Accountant",
                        "locationsText": "Houston, Texas",
                        "bulletFields": ["R100"],
                        "externalPath": "/job/Houston/Senior-Tax-Accountant_R100",
                    }
                ],
            }

    def fake_post(url, **_kwargs):
        return SearchResponse()

    def fake_get(url, **_kwargs):
        requests_seen.append(url)
        raise AssertionError("detail retrieval should have been skipped")

    monkeypatch.setattr("job_radar.collectors.workday.requests.post", fake_post)
    monkeypatch.setattr("job_radar.collectors.workday.requests.get", fake_get)
    config = {
        "company_key": "example_company",
        "name": "Example Company",
        "source_type": "workday",
        "source_url": "https://example.test/wday/cxs/example/External/jobs",
        "source_base_url": "https://example.test/External",
        "max_pages": 1,
    }
    config[DETAIL_PLANNER_CONFIG_KEY] = lambda _title, _location: (
        DetailRetrievalDecision(False, "Clearly unrelated title.")
    )

    postings = collect_workday_jobs(config)

    assert requests_seen == []
    assert len(postings) == 1
    assert postings[0].description is None
    assert postings[0].detail_retrieval_reason == "Clearly unrelated title."
    assert postings[0].detail_retrieval_state == "skipped_unrelated"


def test_collect_workday_jobs_reuses_fresh_unchanged_detail(
    monkeypatch,
) -> None:
    from datetime import UTC, datetime

    from job_radar.collectors.incremental_cache import (
        CACHE_CONFIG_KEY,
        listing_fingerprint,
    )
    from job_radar.models import JobPosting
    from job_radar.storage import CachedSourcePosting

    raw_job = {
        "title": "Platform Engineer",
        "externalPath": "/job/Remote/Platform-Engineer_R1",
        "locationsText": "Remote",
        "bulletFields": ["R1"],
    }
    cached_posting = JobPosting(
        company_key="example_company",
        company_name="Example Company",
        source_type="workday",
        source_job_id="R1",
        source_url="https://example.test/job/R1",
        title="Platform Engineer",
        location="Remote",
        description="Complete cached responsibilities and qualifications. " * 8,
        canonical_key="example",
        content_hash="cached",
    )
    fingerprint = listing_fingerprint(
        {
            "identity": "R1",
            "title": "Platform Engineer",
            "location": "Remote",
            "external_path": raw_job["externalPath"],
                "normalization_version": WORKDAY_DETAIL_NORMALIZATION_VERSION,
            }
    )
    company_config = {
        "company_key": "example_company",
        "name": "Example Company",
        "source_type": "workday",
        "source_url": "https://example.test/wday/cxs/example/External/jobs",
        "source_base_url": "https://example.test/External",
        "max_pages": 1,
        CACHE_CONFIG_KEY: {
            "R1": CachedSourcePosting(
                posting=cached_posting,
                listing_fingerprint=fingerprint,
                detail_verified_at=datetime.now(UTC).isoformat(),
            )
        },
    }

    class SearchResponse:
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {"total": 1, "jobPostings": [raw_job]}

    monkeypatch.setattr(
        "job_radar.collectors.workday.requests.post",
        lambda *args, **kwargs: SearchResponse(),
    )
    monkeypatch.setattr(
        "job_radar.collectors.workday.requests.get",
        lambda *args, **kwargs: pytest.fail("detail request was not skipped"),
    )

    postings = collect_workday_jobs(company_config)

    assert postings[0].description == (
        "Complete cached responsibilities and qualifications. " * 8
    )


def test_collect_workday_jobs_retries_legacy_incomplete_cached_detail(
    monkeypatch,
) -> None:
    from datetime import UTC, datetime

    from job_radar.collectors.incremental_cache import (
        CACHE_CONFIG_KEY,
        listing_fingerprint,
    )
    from job_radar.models import JobPosting
    from job_radar.storage import CachedSourcePosting

    raw_job = {
        "title": "Platform Engineer",
        "externalPath": "/job/Remote/Platform-Engineer_R1",
        "locationsText": "Remote",
        "bulletFields": ["R1"],
    }
    fingerprint = listing_fingerprint(
        {
            "identity": "R1",
            "title": "Platform Engineer",
            "location": "Remote",
            "external_path": raw_job["externalPath"],
            "normalization_version": WORKDAY_DETAIL_NORMALIZATION_VERSION,
        }
    )
    company_config = {
        "company_key": "example_company",
        "name": "Example Company",
        "source_type": "workday",
        "source_url": "https://example.test/wday/cxs/example/External/jobs",
        "source_base_url": "https://example.test/External",
        "max_pages": 1,
        CACHE_CONFIG_KEY: {
            "R1": CachedSourcePosting(
                posting=JobPosting(
                    company_key="example_company",
                    company_name="Example Company",
                    source_type="workday",
                    source_job_id="R1",
                    source_url="https://example.test/job/R1",
                    title="Platform Engineer",
                    location="Remote",
                    description=None,
                    canonical_key="example",
                    content_hash="legacy-incomplete",
                ),
                listing_fingerprint=fingerprint,
                detail_verified_at=datetime.now(UTC).isoformat(),
            )
        },
    }

    class SearchResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"total": 1, "jobPostings": [raw_job]}

    class DetailResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "jobPostingInfo": {
                    "jobDescription": "Required Linux experience. " * 10,
                }
            }

    detail_requests = 0

    def fake_get(*_args, **_kwargs):
        nonlocal detail_requests
        detail_requests += 1
        return DetailResponse()

    monkeypatch.setattr(
        "job_radar.collectors.workday.requests.post",
        lambda *args, **kwargs: SearchResponse(),
    )
    monkeypatch.setattr("job_radar.collectors.workday.requests.get", fake_get)

    postings = collect_workday_jobs(company_config)

    assert detail_requests == 1
    assert postings[0].description.startswith("Required Linux experience")


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


def test_collect_workday_jobs_exceeds_the_previous_1000_job_ceiling(
    monkeypatch,
) -> None:
    company_config = {
        "company_key": "large_company",
        "name": "Large Company",
        "source_type": "workday",
        "source_url": (
            "https://large.wd1.myworkdayjobs.com/"
            "wday/cxs/large/External/jobs"
        ),
        "source_base_url": "https://large.wd1.myworkdayjobs.com/External",
    }
    total = 1_064
    captured_offsets: list[int] = []

    class FakeResponse:
        def __init__(self, offset: int, limit: int) -> None:
            self._offset = offset
            self._limit = limit

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            remaining = max(0, total - self._offset)
            count = min(self._limit, remaining)
            return {
                "total": total if self._offset == 0 else 0,
                "jobPostings": [
                    {
                        "title": f"Engineer {job_number}",
                        "externalPath": f"/job/Remote/Engineer_R{job_number}",
                        "locationsText": "Remote",
                        "bulletFields": [f"R{job_number}"],
                        "description": "Required infrastructure experience.",
                    }
                    for job_number in range(
                        self._offset + 1,
                        self._offset + count + 1,
                    )
                ],
            }

    def fake_post(url, json, headers, timeout):
        del url, headers, timeout
        captured_offsets.append(json["offset"])
        return FakeResponse(json["offset"], json["limit"])

    monkeypatch.setattr(
        "job_radar.collectors.workday.requests.post",
        fake_post,
    )

    postings = collect_workday_jobs(company_config)

    assert len(postings) == total
    assert captured_offsets[-1] == 1_060


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
