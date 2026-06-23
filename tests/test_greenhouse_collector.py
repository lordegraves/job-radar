import pytest

from job_radar.collectors.greenhouse import (
    CollectorError,
    build_greenhouse_jobs_url,
    parse_greenhouse_jobs,
)


def test_build_greenhouse_jobs_url() -> None:
    assert (
        build_greenhouse_jobs_url("exampleai")
        == "https://boards-api.greenhouse.io/v1/boards/exampleai/jobs?content=true"
    )


def test_parse_greenhouse_jobs_returns_job_postings() -> None:
    company_config = {
        "company_key": "example_ai",
        "name": "Example AI",
        "source_type": "greenhouse",
        "source_slug": "exampleai",
        "enabled": True,
    }

    payload = {
        "jobs": [
            {
                "id": 123,
                "title": "Senior Infrastructure Engineer",
                "location": {"name": "Remote"},
                "absolute_url": "https://boards.greenhouse.io/exampleai/jobs/123",
                "content": "Build and operate Linux infrastructure.",
            }
        ],
        "meta": {"total": 1},
    }

    postings = parse_greenhouse_jobs(company_config, payload)

    assert len(postings) == 1

    posting = postings[0]

    assert posting.company_key == "example_ai"
    assert posting.company_name == "Example AI"
    assert posting.source_type == "greenhouse"
    assert posting.source_job_id == "123"
    assert posting.source_url == "https://boards.greenhouse.io/exampleai/jobs/123"
    assert posting.title == "Senior Infrastructure Engineer"
    assert posting.location == "Remote"
    assert posting.description == "Build and operate Linux infrastructure."
    assert posting.canonical_key == "example-ai:senior-infrastructure-engineer:remote"
    assert posting.content_hash is not None


def test_parse_greenhouse_jobs_skips_jobs_missing_title() -> None:
    company_config = {
        "company_key": "example_ai",
        "name": "Example AI",
        "source_type": "greenhouse",
    }

    payload = {
        "jobs": [
            {
                "id": 123,
                "location": {"name": "Remote"},
                "absolute_url": "https://boards.greenhouse.io/exampleai/jobs/123",
                "content": "Missing title.",
            }
        ]
    }

    postings = parse_greenhouse_jobs(company_config, payload)

    assert postings == []


def test_parse_greenhouse_jobs_skips_jobs_missing_url() -> None:
    company_config = {
        "company_key": "example_ai",
        "name": "Example AI",
        "source_type": "greenhouse",
    }

    payload = {
        "jobs": [
            {
                "id": 123,
                "title": "Senior Infrastructure Engineer",
                "location": {"name": "Remote"},
                "content": "Missing URL.",
            }
        ]
    }

    postings = parse_greenhouse_jobs(company_config, payload)

    assert postings == []


def test_parse_greenhouse_jobs_rejects_payload_without_jobs_list() -> None:
    company_config = {
        "company_key": "example_ai",
        "name": "Example AI",
        "source_type": "greenhouse",
    }

    payload = {"not_jobs": []}

    with pytest.raises(CollectorError, match="jobs list"):
        parse_greenhouse_jobs(company_config, payload)