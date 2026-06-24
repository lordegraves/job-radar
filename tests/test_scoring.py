from pathlib import Path

import pytest

from job_radar.models import JobPosting
from job_radar.scoring import (
    ScoringConfigError,
    classify_location,
    evaluate_top_match_eligibility,
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
            "san francisco": -100,
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
        "top_matches": {
            "excluded_title_keywords": [
                "account executive",
                "customer success",
                "recruiter",
                "sales",
            ],
            "strong_signals": [
                "title:infrastructure",
                "title:linux",
                "body:kubernetes",
            ],
        },
    }


def test_load_scoring_config_reads_keywords_location_preferences_and_top_matches(
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

top_matches:
  excluded_title_keywords:
    - sales
    - recruiting
  strong_signals:
    - title:linux
    - body:hpc
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
    assert config["top_matches"] == {
        "excluded_title_keywords": [
            "sales",
            "recruiting",
        ],
        "strong_signals": [
            "title:linux",
            "body:hpc",
        ],
    }


def test_load_scoring_config_defaults_top_matches_to_empty_lists(
    tmp_path: Path,
) -> None:
    scoring_file = tmp_path / "scoring.yaml"
    scoring_file.write_text(
        """
positive_keywords:
  linux: 10

negative_keywords: {}

location_preferences:
  allowed: {}
  conditional: {}
  skipped: {}
""",
        encoding="utf-8",
    )

    config = load_scoring_config(scoring_file)

    assert config["top_matches"] == {
        "excluded_title_keywords": [],
        "strong_signals": [],
    }


def test_load_scoring_config_rejects_invalid_top_matches(
    tmp_path: Path,
) -> None:
    scoring_file = tmp_path / "scoring.yaml"
    scoring_file.write_text(
        """
positive_keywords:
  linux: 10

negative_keywords: {}

location_preferences:
  allowed: {}
  conditional: {}
  skipped: {}

top_matches:
  excluded_title_keywords:
    sales: bad
  strong_signals:
    - title:linux
""",
        encoding="utf-8",
    )

    with pytest.raises(ScoringConfigError):
        load_scoring_config(scoring_file)


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


def test_classify_location_returns_allowed_with_travel_for_limited_travel() -> None:
    posting = make_posting(
        title="Senior Infrastructure Engineer",
        description="Build Linux systems.",
        location="Remote-Friendly, United States - Travel required 10-20%",
    )

    config = make_scoring_config()

    assert classify_location(posting, config) == "allowed_with_travel"


def test_classify_location_returns_mixed_for_remote_with_vague_travel() -> None:
    posting = make_posting(
        title="Senior Infrastructure Engineer",
        description="Build Linux systems.",
        location="Remote-Friendly, United States - Travel required",
    )

    config = make_scoring_config()

    assert classify_location(posting, config) == "mixed"


def test_classify_location_returns_mixed_for_remote_with_skipped_city() -> None:
    posting = make_posting(
        title="Senior Infrastructure Engineer",
        description="Build Linux systems.",
        location="Remote-Friendly | San Francisco, CA",
    )

    config = make_scoring_config()

    assert classify_location(posting, config) == "mixed"


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


def test_evaluate_top_match_eligibility_returns_true_for_allowed_strong_match() -> None:
    posting = make_posting(
        title="Senior Infrastructure Engineer",
        description="Build Linux systems.",
        location="Remote",
    )

    config = make_scoring_config()

    eligible, reasons = evaluate_top_match_eligibility(
        posting=posting,
        score=140,
        score_reasons=[
            "+30 title:infrastructure",
            "+10 body:linux",
            "+100 location_allowed:remote",
        ],
        location_status="allowed",
        scoring_config=config,
    )

    assert eligible is True
    assert reasons == ["eligible"]


def test_evaluate_top_match_eligibility_rejects_non_allowed_location() -> None:
    posting = make_posting(
        title="Senior Infrastructure Engineer",
        description="Build Linux systems.",
        location="Denver, CO",
    )

    config = make_scoring_config()

    eligible, reasons = evaluate_top_match_eligibility(
        posting=posting,
        score=15,
        score_reasons=[
            "+30 title:infrastructure",
            "+10 body:linux",
            "-25 location_conditional:denver",
        ],
        location_status="conditional",
        scoring_config=config,
    )

    assert eligible is False
    assert reasons == ["location_not_allowed:conditional"]


def test_evaluate_top_match_eligibility_rejects_negative_title_match() -> None:
    posting = make_posting(
        title="Infrastructure Customer Success Engineer",
        description="Linux troubleshooting for customers.",
        location="Remote",
    )

    config = make_scoring_config()

    eligible, reasons = evaluate_top_match_eligibility(
        posting=posting,
        score=110,
        score_reasons=[
            "+30 title:infrastructure",
            "+10 body:linux",
            "-30 title:customer success",
            "+100 location_allowed:remote",
        ],
        location_status="allowed",
        scoring_config=config,
    )

    assert eligible is False
    assert reasons == ["negative_title_match"]


def test_evaluate_top_match_eligibility_rejects_missing_strong_signal() -> None:
    posting = make_posting(
        title="General Systems Analyst",
        description="General operations role.",
        location="Remote",
    )

    config = make_scoring_config()

    eligible, reasons = evaluate_top_match_eligibility(
        posting=posting,
        score=100,
        score_reasons=[
            "+100 location_allowed:remote",
        ],
        location_status="allowed",
        scoring_config=config,
    )

    assert eligible is False
    assert reasons == ["missing_strong_signal"]


def test_evaluate_top_match_eligibility_uses_configured_excluded_keywords() -> None:
    posting = make_posting(
        title="Infrastructure Recruiter",
        description="Recruiting for infrastructure teams.",
        location="Remote",
    )

    config = make_scoring_config()

    eligible, reasons = evaluate_top_match_eligibility(
        posting=posting,
        score=100,
        score_reasons=[
            "+30 title:infrastructure",
            "+100 location_allowed:remote",
        ],
        location_status="allowed",
        scoring_config=config,
    )

    assert eligible is False
    assert reasons == ["excluded_title_keyword:recruiter"]


def test_evaluate_top_match_eligibility_allows_limited_travel() -> None:
    posting = make_posting(
        title="Senior Infrastructure Engineer",
        description="Build Linux systems.",
        location="Remote-Friendly, United States - Travel required 10-20%",
    )

    config = make_scoring_config()

    eligible, reasons = evaluate_top_match_eligibility(
        posting=posting,
        score=140,
        score_reasons=[
            "+30 title:infrastructure",
            "+10 body:linux",
            "+100 location_allowed:remote",
        ],
        location_status="allowed_with_travel",
        scoring_config=config,
    )

    assert eligible is True
    assert reasons == ["eligible"]