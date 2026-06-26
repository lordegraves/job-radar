import pytest

from job_radar.collectors.ashby import (
    build_ashby_jobs_url,
    parse_ashby_jobs,
)
from job_radar.collectors.greenhouse import CollectorError


def test_build_ashby_jobs_url() -> None:
    assert (
        build_ashby_jobs_url("ExampleAI")
        == "https://api.ashbyhq.com/posting-api/job-board/ExampleAI?includeCompensation=true"
    )


def test_parse_ashby_jobs_returns_job_postings() -> None:
    company_config = {
        "company_key": "example_ai",
        "name": "Example AI",
        "source_type": "ashby",
        "source_slug": "ExampleAI",
        "enabled": True,
    }

    payload = {
        "jobs": [
            {
                "id": "abc-123",
                "title": "Senior Infrastructure Engineer",
                "jobUrl": "https://jobs.ashbyhq.com/ExampleAI/abc-123",
                "locationName": "Remote",
                "descriptionPlain": "Build and operate Linux infrastructure.",
                "compensation": {
                    "compensationTierSummary": "$180K - $220K",
                },
            }
        ]
    }

    postings = parse_ashby_jobs(company_config, payload)

    assert len(postings) == 1

    posting = postings[0]

    assert posting.company_key == "example_ai"
    assert posting.company_name == "Example AI"
    assert posting.source_type == "ashby"
    assert posting.source_job_id == "abc-123"
    assert posting.source_url == "https://jobs.ashbyhq.com/ExampleAI/abc-123"
    assert posting.title == "Senior Infrastructure Engineer"
    assert posting.location == "Remote"
    assert posting.description == "Build and operate Linux infrastructure."
    assert posting.salary_text == "$180K - $220K"
    assert posting.canonical_key == "example-ai:senior-infrastructure-engineer:remote"
    assert posting.content_hash is not None


def test_parse_ashby_jobs_uses_nested_location_name() -> None:
    company_config = {
        "company_key": "example_ai",
        "name": "Example AI",
        "source_type": "ashby",
    }

    payload = {
        "jobs": [
            {
                "id": "abc-123",
                "title": "Infrastructure Engineer",
                "jobUrl": "https://jobs.ashbyhq.com/ExampleAI/abc-123",
                "location": {"name": "New York, NY"},
            }
        ]
    }

    postings = parse_ashby_jobs(company_config, payload)

    assert len(postings) == 1
    assert postings[0].location == "New York, NY"


def test_parse_ashby_jobs_skips_jobs_missing_title() -> None:
    company_config = {
        "company_key": "example_ai",
        "name": "Example AI",
        "source_type": "ashby",
    }

    payload = {
        "jobs": [
            {
                "id": "abc-123",
                "jobUrl": "https://jobs.ashbyhq.com/ExampleAI/abc-123",
                "locationName": "Remote",
            }
        ]
    }

    postings = parse_ashby_jobs(company_config, payload)

    assert postings == []


def test_parse_ashby_jobs_skips_jobs_missing_url() -> None:
    company_config = {
        "company_key": "example_ai",
        "name": "Example AI",
        "source_type": "ashby",
    }

    payload = {
        "jobs": [
            {
                "id": "abc-123",
                "title": "Infrastructure Engineer",
                "locationName": "Remote",
            }
        ]
    }

    postings = parse_ashby_jobs(company_config, payload)

    assert postings == []


def test_parse_ashby_jobs_rejects_payload_without_jobs_list() -> None:
    company_config = {
        "company_key": "example_ai",
        "name": "Example AI",
        "source_type": "ashby",
    }

    with pytest.raises(CollectorError, match="jobs list"):
        parse_ashby_jobs(company_config, {"not_jobs": []})