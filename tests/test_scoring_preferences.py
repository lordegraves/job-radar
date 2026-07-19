"""Tests the read-only, plain-language view of active scoring preferences."""

from pathlib import Path

from job_radar.scoring_preferences import build_scoring_preferences_view


def test_scoring_preferences_view_preserves_existing_rule_meaning(
    tmp_path: Path,
) -> None:
    scoring_file = tmp_path / "scoring.yaml"
    scoring_file.write_text(
        """
positive_keywords:
  linux: 10
negative_keywords:
  sales: -15
location_preferences:
  allowed:
    remote: 100
    northern colorado: 100
  conditional:
    denver: -25
  skipped:
    new york: -100
top_matches:
  min_score: 120
  excluded_title_keywords:
    - sales
  strong_signals:
    - title:linux
review_needed:
  min_score: 100
  excluded_location_statuses:
    - skipped
  strong_signals:
    - body:linux
""",
        encoding="utf-8",
    )

    view = build_scoring_preferences_view(scoring_file)

    assert view.load_error is None
    assert view.positive_keywords[0].term == "linux"
    assert view.positive_keywords[0].points == 10
    assert view.negative_keywords[0].points == -15
    assert view.allowed_locations == ("remote", "northern colorado")
    assert view.conditional_locations[0].points == -25
    assert view.skipped_locations[0].points == -100
    assert view.top_match_min_score == 120
    assert view.review_needed_min_score == 100
    assert view.top_match_signals == ("Job title: linux",)
    assert view.review_needed_signals == ("Job description: linux",)


def test_scoring_preferences_view_reports_missing_file_without_crashing(
    tmp_path: Path,
) -> None:
    view = build_scoring_preferences_view(tmp_path / "missing.yaml")

    assert view.load_error is not None
    assert "Scoring config not found" in view.load_error
