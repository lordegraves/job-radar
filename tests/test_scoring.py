from pathlib import Path

import pytest

from job_radar.models import JobPosting
from job_radar.scoring import (
    ScoringConfigError,
    classify_location,
    load_scoring_config,
    score_posting,
)


def make_posting(
    title: str,
    description: str,
    location: str | None = "Remote",
) -> JobPosting:
    return JobPosting(
        company_key="example_ai",
        company_name="Example AI",
        source_type="greenhouse",
        source_job_id="123",
        source_url="https://example.com/jobs/123",
        title=title,
        location=location,
        description=description,
        canonical_key="example_ai:job",
        content_hash="hash",
    )


def make_location_preferences() -> dict[str, dict[str, int]]:
    return {
        "allowed": {
            "remote": 100,
            "cheyenne": 100,
        },
        "conditional": {
            "denver": -25,
            "boulder": -25,
        },
        "skipped": {
            "london": -100,
            "uk": -100,
        },
    }


def make_scoring_config() -> dict:
    return {
        "positive_keywords": {
            "infrastructure": 10,
            "linux": 10,
            "kubernetes": 8,
        },
        "negative_keywords": {
            "account executive": -20,
            "sales": -15,
            "recruiter": -12,
            "hr": -12,
            "customer success": -10,
        },
        "location_preferences": make_location_preferences(),
    }


def test_load_scoring_config_reads_keywords_and_location_preferences(
    tmp_path: Path,
) -> None:
    scoring_file = tmp_path / "scoring.yaml"
    scoring_file.write_text(
        """
positive_keywords:
  linux: 10
  kubernetes: 8

negative_keywords:
  sales: -15

location_preferences:
  allowed:
    remote: 100
    cheyenne: 100
  conditional:
    denver: -25
  skipped:
    london: -100
""",
        encoding="utf-8",
    )

    config = load_scoring_config(scoring_file)

    assert config["positive_keywords"] == {
        "linux": 10,
        "kubernetes": 8,
    }
    assert config["negative_keywords"] == {
        "sales": -15,
    }
    assert config["location_preferences"] == {
        "allowed": {
            "remote": 100,
            "cheyenne": 100,
        },
        "conditional": {
            "denver": -25,
        },
        "skipped": {
            "london": -100,
        },
    }


def test_load_scoring_config_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ScoringConfigError):
        load_scoring_config(tmp_path / "missing.yaml")


def test_score_posting_weights_title_matches_more_than_body_matches() -> None:
    posting = make_posting(
        title="Senior Linux Infrastructure Engineer",
        description="Run Kubernetes clusters.",
        location="Remote",
    )

    config = {
        "positive_keywords": {
            "linux": 10,
            "infrastructure": 10,
            "kubernetes": 8,
        },
        "negative_keywords": {},
        "location_preferences": {
            "allowed": {},
            "conditional": {},
            "skipped": {},
        },
    }

    score, reasons = score_posting(posting, config)

    assert score == 68
    assert "+30 title:linux" in reasons
    assert "+30 title:infrastructure" in reasons
    assert "+8 body:kubernetes" in reasons


def test_score_posting_applies_negative_keyword_scores_to_title_only() -> None:
    posting = make_posting(
        title="Account Executive",
        description="Sales role with recruiter and HR boilerplate.",
    )

    config = make_scoring_config()

    score, reasons = score_posting(posting, config)

    assert score == 40
    assert "-60 title:account executive" in reasons
    assert "+100 location_allowed:remote" in reasons
    assert "-15 body:sales" not in reasons
    assert "-12 body:recruiter" not in reasons
    assert "-12 body:hr" not in reasons


def test_score_posting_combines_positive_and_negative_title_scores() -> None:
    posting = make_posting(
        title="Infrastructure Customer Success Engineer",
        description="Linux troubleshooting for customers.",
    )

    config = make_scoring_config()

    score, reasons = score_posting(posting, config)

    assert score == 110
    assert "+30 title:infrastructure" in reasons
    assert "+10 body:linux" in reasons
    assert "-30 title:customer success" in reasons
    assert "+100 location_allowed:remote" in reasons


def test_score_posting_applies_allowed_location_scores() -> None:
    posting = make_posting(
        title="Senior Infrastructure Engineer",
        description="Build Linux systems.",
        location="Remote - United States",
    )

    config = make_scoring_config()

    score, reasons = score_posting(posting, config)

    assert score == 140
    assert "+30 title:infrastructure" in reasons
    assert "+10 body:linux" in reasons
    assert "+100 location_allowed:remote" in reasons


def test_score_posting_applies_conditional_location_scores() -> None:
    posting = make_posting(
        title="Senior Infrastructure Engineer",
        description="Build Linux systems.",
        location="Denver, CO",
    )

    config = make_scoring_config()

    score, reasons = score_posting(posting, config)

    assert score == 15
    assert "+30 title:infrastructure" in reasons
    assert "+10 body:linux" in reasons
    assert "-25 location_conditional:denver" in reasons


def test_score_posting_applies_skipped_location_scores() -> None:
    posting = make_posting(
        title="Senior Infrastructure Engineer",
        description="Build Linux systems.",
        location="London, UK",
    )

    config = make_scoring_config()

    score, reasons = score_posting(posting, config)

    assert score == -160
    assert "+30 title:infrastructure" in reasons
    assert "+10 body:linux" in reasons
    assert "-100 location_skipped:london" in reasons
    assert "-100 location_skipped:uk" in reasons


def test_classify_location_returns_allowed() -> None:
    posting = make_posting(
        title="Senior Infrastructure Engineer",
        description="Build Linux systems.",
        location="Remote-Friendly, United States",
    )

    config = make_scoring_config()

    assert classify_location(posting, config) == "allowed"


def test_classify_location_returns_conditional() -> None:
    posting = make_posting(
        title="Senior Infrastructure Engineer",
        description="Build Linux systems.",
        location="Denver, CO",
    )

    config = make_scoring_config()

    assert classify_location(posting, config) == "conditional"


def test_classify_location_returns_skipped() -> None:
    posting = make_posting(
        title="Senior Infrastructure Engineer",
        description="Build Linux systems.",
        location="London, UK",
    )

    config = make_scoring_config()

    assert classify_location(posting, config) == "skipped"


def test_classify_location_returns_unknown_for_unmatched_location() -> None:
    posting = make_posting(
        title="Senior Infrastructure Engineer",
        description="Build Linux systems.",
        location="Tokyo, Japan",
    )

    config = make_scoring_config()

    assert classify_location(posting, config) == "unknown"