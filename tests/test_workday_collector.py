import pytest

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.workday import (
    parse_workday_jobs,
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