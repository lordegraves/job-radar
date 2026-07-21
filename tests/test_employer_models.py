"""Verify app-owned employer source validation and collector conversion."""

import pytest

from job_radar.employer_models import EmployerSource


def test_employer_source_preserves_complete_collector_configuration() -> None:
    employer = EmployerSource(
        employer_id="example_law",
        name="Example Law",
        source_type="workday",
        enabled=True,
        source_config={
            "source_url": "https://example.invalid/jobs",
            "source_base_url": "https://example.invalid",
            "query_params": {
                "location": "Carrollton",
            },
            "page_size": 25,
            "max_pages": 3,
        },
        notes="Local paralegal employer.",
    )

    assert employer.to_company_config() == {
        "company_key": "example_law",
        "name": "Example Law",
        "source_type": "workday",
        "enabled": True,
        "source_url": "https://example.invalid/jobs",
        "source_base_url": "https://example.invalid",
        "query_params": {
            "location": "Carrollton",
        },
        "page_size": 25,
        "max_pages": 3,
        "notes": "Local paralegal employer.",
    }


def test_employer_source_rejects_unsupported_source_type() -> None:
    with pytest.raises(ValueError, match="unsupported employer source type"):
        EmployerSource(
            employer_id="example",
            name="Example",
            source_type="unknown",
        )


def test_employer_source_rejects_non_mapping_source_config() -> None:
    with pytest.raises(ValueError, match="source config must be a mapping"):
        EmployerSource(
            employer_id="example",
            name="Example",
            source_type="greenhouse",
            source_config=[],  # type: ignore[arg-type]
        )
