from pathlib import Path

import pytest

from job_radar.models import JobPosting
from job_radar.scoring import (
    ScoringConfigError,
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


def test_load_scoring_config_reads_positive_and_negative_keywords(
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


def test_load_scoring_config_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ScoringConfigError):
        load_scoring_config(tmp_path / "missing.yaml")


def test_score_posting_adds_positive_keyword_scores() -> None:
    posting = make_posting(
        title="Senior Linux Infrastructure Engineer",
        description="Run Kubernetes clusters.",
    )

    config = {
        "positive_keywords": {
            "linux": 10,
            "infrastructure": 10,
            "kubernetes": 8,
        },
        "negative_keywords": {},
    }

    score, reasons = score_posting(posting, config)

    assert score == 28
    assert "+10 linux" in reasons
    assert "+10 infrastructure" in reasons
    assert "+8 kubernetes" in reasons


def test_score_posting_applies_negative_keyword_scores() -> None:
    posting = make_posting(
        title="Account Executive",
        description="Sales role for customer accounts.",
    )

    config = {
        "positive_keywords": {},
        "negative_keywords": {
            "account executive": -20,
            "sales": -15,
        },
    }

    score, reasons = score_posting(posting, config)

    assert score == -35
    assert "-20 account executive" in reasons
    assert "-15 sales" in reasons


def test_score_posting_combines_positive_and_negative_scores() -> None:
    posting = make_posting(
        title="Infrastructure Customer Success Engineer",
        description="Linux troubleshooting for customers.",
    )

    config = {
        "positive_keywords": {
            "infrastructure": 10,
            "linux": 10,
            "troubleshooting": 5,
        },
        "negative_keywords": {
            "customer success": -10,
        },
    }

    score, reasons = score_posting(posting, config)

    assert score == 15
    assert "+10 infrastructure" in reasons
    assert "+10 linux" in reasons
    assert "+5 troubleshooting" in reasons
    assert "-10 customer success" in reasons