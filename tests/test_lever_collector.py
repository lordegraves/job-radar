import pytest

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.lever import (
    build_lever_jobs_url,
    parse_lever_jobs,
)


def test_build_lever_jobs_url() -> None:
    assert (
        build_lever_jobs_url("researchlabs")
        == "https://api.lever.co/v0/postings/researchlabs?mode=json"
    )


def test_parse_lever_jobs_returns_job_postings() -> None:
    company_config = {
        "company_key": "research_labs",
        "name": "Research Labs",
        "source_type": "lever",
        "source_slug": "researchlabs",
        "enabled": True,
    }

    payload = [
        {
            "id": "abc-123",
            "text": "Senior Linux Infrastructure Engineer",
            "hostedUrl": "https://jobs.lever.co/researchlabs/abc-123",
            "descriptionPlain": "Operate Linux infrastructure for research systems.",
            "categories": {
                "location": "Remote",
                "team": "Infrastructure",
                "commitment": "Full-time",
            },
        }
    ]

    postings = parse_lever_jobs(company_config, payload)

    assert len(postings) == 1

    posting = postings[0]

    assert posting.company_key == "research_labs"
    assert posting.company_name == "Research Labs"
    assert posting.source_type == "lever"
    assert posting.source_job_id == "abc-123"
    assert posting.source_url == "https://jobs.lever.co/researchlabs/abc-123"
    assert posting.title == "Senior Linux Infrastructure Engineer"
    assert posting.location == "Remote"
    assert posting.description == "Operate Linux infrastructure for research systems."
    assert posting.canonical_key == "research-labs:senior-linux-infrastructure-engineer:remote"
    assert posting.content_hash is not None


def test_parse_lever_jobs_uses_html_description_if_plain_missing() -> None:
    company_config = {
        "company_key": "research_labs",
        "name": "Research Labs",
        "source_type": "lever",
    }

    payload = [
        {
            "id": "abc-123",
            "text": "Infrastructure Engineer",
            "hostedUrl": "https://jobs.lever.co/researchlabs/abc-123",
            "description": "<p>Build infrastructure.</p>",
            "categories": {"location": "Remote"},
        }
    ]

    postings = parse_lever_jobs(company_config, payload)

    assert len(postings) == 1
    assert postings[0].description == "<p>Build infrastructure.</p>"


def test_parse_lever_jobs_skips_jobs_missing_title() -> None:
    company_config = {
        "company_key": "research_labs",
        "name": "Research Labs",
        "source_type": "lever",
    }

    payload = [
        {
            "id": "abc-123",
            "hostedUrl": "https://jobs.lever.co/researchlabs/abc-123",
            "categories": {"location": "Remote"},
        }
    ]

    postings = parse_lever_jobs(company_config, payload)

    assert postings == []


def test_parse_lever_jobs_skips_jobs_missing_url() -> None:
    company_config = {
        "company_key": "research_labs",
        "name": "Research Labs",
        "source_type": "lever",
    }

    payload = [
        {
            "id": "abc-123",
            "text": "Infrastructure Engineer",
            "categories": {"location": "Remote"},
        }
    ]

    postings = parse_lever_jobs(company_config, payload)

    assert postings == []


def test_parse_lever_jobs_rejects_non_list_payload() -> None:
    company_config = {
        "company_key": "research_labs",
        "name": "Research Labs",
        "source_type": "lever",
    }

    with pytest.raises(CollectorError, match="Lever payload must be a list"):
        parse_lever_jobs(company_config, {"not": "a list"})  # type: ignore[arg-type]