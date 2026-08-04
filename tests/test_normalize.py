"""Tests consistent text cleanup, duplicate keys, and change-detection hashes."""

from dataclasses import replace

from job_radar.models import JobPosting
from job_radar.normalize import (
    clean_human_text,
    clean_text,
    make_canonical_key,
    make_content_hash,
    normalize_for_key,
    normalize_job_posting,
    normalize_job_postings,
)


def test_clean_text_removes_extra_whitespace() -> None:
    assert clean_text("  Senior   Infrastructure\nEngineer  ") == "Senior Infrastructure Engineer"


def test_clean_text_handles_none() -> None:
    assert clean_text(None) == ""


def test_normalize_for_key_lowercases_and_replaces_punctuation() -> None:
    assert normalize_for_key("Senior Infrastructure Engineer!") == "senior-infrastructure-engineer"


def test_make_canonical_key_includes_company_title_and_location() -> None:
    result = make_canonical_key(
        company_key="example_ai",
        title="Senior Infrastructure Engineer",
        location="Remote - US",
    )

    assert result == "example-ai:senior-infrastructure-engineer:remote-us"


def test_make_canonical_key_omits_empty_location() -> None:
    result = make_canonical_key(
        company_key="example_ai",
        title="Senior Infrastructure Engineer",
        location=None,
    )

    assert result == "example-ai:senior-infrastructure-engineer"


def test_make_content_hash_is_stable_for_same_content() -> None:
    first = make_content_hash(
        title="Senior Infrastructure Engineer",
        location="Remote",
        description="Build Linux infrastructure",
        salary_text="$180k - $220k",
    )

    second = make_content_hash(
        title="Senior Infrastructure Engineer",
        location="Remote",
        description="Build Linux infrastructure",
        salary_text="$180k - $220k",
    )

    assert first == second


def test_make_content_hash_changes_when_description_changes() -> None:
    first = make_content_hash(
        title="Senior Infrastructure Engineer",
        location="Remote",
        description="Build Linux infrastructure",
    )

    second = make_content_hash(
        title="Senior Infrastructure Engineer",
        location="Remote",
        description="Build Linux and Kubernetes infrastructure",
    )

    assert first != second


def _posting(**overrides) -> JobPosting:
    values = {
        "company_key": "example",
        "company_name": "Example",
        "source_type": "workday",
        "source_url": "https://example.com/job/1",
        "source_job_id": "1",
        "title": "Infrastructure Engineer",
        "location": "Remote",
        "remote_status": "fully remote",
        "description": "Build and operate reliable Linux infrastructure. " * 8,
    }
    values.update(overrides)
    return JobPosting(**values)


def test_clean_human_text_preserves_sections_and_removes_duplicate_markup() -> None:
    result = clean_human_text(
        "<h2>Required Qualifications</h2><p>Linux &amp; Kubernetes</p>"
        "<p>Linux &amp; Kubernetes</p>"
    )

    assert result == "Required Qualifications\nLinux & Kubernetes"


def test_normalize_job_posting_uses_common_workplace_and_semantic_hash() -> None:
    html_posting = normalize_job_posting(
        _posting(description="<p>Build Linux systems.</p>" * 20)
    )
    plain_posting = normalize_job_posting(
        _posting(description="Build Linux systems.")
    )

    assert html_posting.remote_status == "Remote"
    assert html_posting.description == "Build Linux systems."
    assert html_posting.content_hash == plain_posting.content_hash


def test_normalize_job_posting_marks_unknown_workplace_without_blocking() -> None:
    posting = normalize_job_posting(_posting(remote_status="1"))

    assert posting.normalization_state == "complete"
    assert posting.normalization_issues == ("unrecognized_workplace_value",)


def test_normalize_job_posting_marks_short_description_incomplete() -> None:
    posting = normalize_job_posting(_posting(description="Short teaser"))

    assert posting.normalization_state == "incomplete"
    assert posting.normalization_issues == ("incomplete_description",)


def test_normalize_job_posting_clears_repaired_field_issue() -> None:
    posting = _posting(
        description="Short teaser",
        normalization_state="incomplete",
        normalization_issues=("incomplete_description",),
    )

    normalized = normalize_job_posting(
        replace(posting, description="Detailed responsibilities. " * 20)
    )

    assert normalized.normalization_state == "complete"
    assert "incomplete_description" not in normalized.normalization_issues


def test_normalize_job_postings_rejects_duplicate_source_ids() -> None:
    postings = normalize_job_postings(
        [
            _posting(source_url="https://example.com/job/1"),
            _posting(source_url="https://example.com/job/2"),
        ]
    )

    assert all(posting.source_job_id is None for posting in postings)
    assert all(
        "duplicate_source_job_id" in posting.normalization_issues
        for posting in postings
    )
