from pathlib import Path
from typing import Any

import yaml

from job_radar.models import JobPosting
from job_radar.normalize import clean_text


TITLE_WEIGHT = 3
BODY_WEIGHT = 1


class ScoringConfigError(Exception):
    pass


def load_scoring_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)

    if not config_path.exists():
        raise ScoringConfigError(f"Scoring config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict):
        raise ScoringConfigError("Scoring config must be a mapping")

    positive_keywords = data.get("positive_keywords", {})
    negative_keywords = data.get("negative_keywords", {})
    location_preferences = data.get("location_preferences", {})
    top_matches = data.get("top_matches", {})

    if not isinstance(positive_keywords, dict):
        raise ScoringConfigError("positive_keywords must be a mapping")

    if not isinstance(negative_keywords, dict):
        raise ScoringConfigError("negative_keywords must be a mapping")

    return {
        "positive_keywords": _validate_keyword_scores(positive_keywords),
        "negative_keywords": _validate_keyword_scores(negative_keywords),
        "location_preferences": _validate_location_preferences(location_preferences),
        "top_matches": _validate_top_matches(top_matches),
    }


def _validate_keyword_scores(raw_scores: dict[str, Any]) -> dict[str, int]:
    validated_scores: dict[str, int] = {}

    for keyword, score in raw_scores.items():
        if not isinstance(keyword, str):
            raise ScoringConfigError("Scoring keyword must be a string")

        if not isinstance(score, int):
            raise ScoringConfigError(f"Score for keyword '{keyword}' must be an integer")

        cleaned_keyword = clean_text(keyword).lower()

        if not cleaned_keyword:
            raise ScoringConfigError("Scoring keyword cannot be empty")

        validated_scores[cleaned_keyword] = score

    return validated_scores


def _validate_keyword_list(raw_keywords: Any, config_key: str) -> list[str]:
    if raw_keywords is None:
        raw_keywords = []

    if not isinstance(raw_keywords, list):
        raise ScoringConfigError(f"{config_key} must be a list")

    validated_keywords: list[str] = []

    for keyword in raw_keywords:
        if not isinstance(keyword, str):
            raise ScoringConfigError(f"{config_key} entries must be strings")

        cleaned_keyword = clean_text(keyword).lower()

        if not cleaned_keyword:
            raise ScoringConfigError(f"{config_key} entries cannot be empty")

        validated_keywords.append(cleaned_keyword)

    return validated_keywords


def _validate_location_preferences(
    raw_preferences: Any,
) -> dict[str, dict[str, int]]:
    if raw_preferences is None:
        raw_preferences = {}

    if not isinstance(raw_preferences, dict):
        raise ScoringConfigError("location_preferences must be a mapping")

    allowed = raw_preferences.get("allowed", {})
    conditional = raw_preferences.get("conditional", {})
    skipped = raw_preferences.get("skipped", {})

    if not isinstance(allowed, dict):
        raise ScoringConfigError("location_preferences.allowed must be a mapping")

    if not isinstance(conditional, dict):
        raise ScoringConfigError("location_preferences.conditional must be a mapping")

    if not isinstance(skipped, dict):
        raise ScoringConfigError("location_preferences.skipped must be a mapping")

    return {
        "allowed": _validate_keyword_scores(allowed),
        "conditional": _validate_keyword_scores(conditional),
        "skipped": _validate_keyword_scores(skipped),
    }


def _validate_top_matches(raw_top_matches: Any) -> dict[str, list[str]]:
    if raw_top_matches is None:
        raw_top_matches = {}

    if not isinstance(raw_top_matches, dict):
        raise ScoringConfigError("top_matches must be a mapping")

    excluded_title_keywords = raw_top_matches.get("excluded_title_keywords", [])
    strong_signals = raw_top_matches.get("strong_signals", [])

    return {
        "excluded_title_keywords": _validate_keyword_list(
            excluded_title_keywords,
            "top_matches.excluded_title_keywords",
        ),
        "strong_signals": _validate_keyword_list(
            strong_signals,
            "top_matches.strong_signals",
        ),
    }


def score_posting(
    posting: JobPosting,
    scoring_config: dict[str, Any],
) -> tuple[int, list[str]]:
    title_text = clean_text(posting.title).lower()
    body_text = _build_body_text(posting)
    location_text = clean_text(posting.location).lower()

    score = 0
    reasons: list[str] = []

    for keyword, points in scoring_config["positive_keywords"].items():
        if keyword in title_text:
            weighted_points = points * TITLE_WEIGHT
            score += weighted_points
            reasons.append(f"+{weighted_points} title:{keyword}")
        elif keyword in body_text:
            weighted_points = points * BODY_WEIGHT
            score += weighted_points
            reasons.append(f"+{weighted_points} body:{keyword}")

    for keyword, points in scoring_config["negative_keywords"].items():
        if keyword in title_text:
            weighted_points = points * TITLE_WEIGHT
            score += weighted_points
            reasons.append(f"{weighted_points} title:{keyword}")

    location_score, location_reasons = _score_location(
        location_text=location_text,
        location_preferences=scoring_config["location_preferences"],
    )
    score += location_score
    reasons.extend(location_reasons)

    return score, reasons


def _score_location(
    location_text: str,
    location_preferences: dict[str, dict[str, int]],
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    for keyword, points in location_preferences["allowed"].items():
        if keyword in location_text:
            score += points
            reasons.append(f"+{points} location_allowed:{keyword}")

    for keyword, points in location_preferences["conditional"].items():
        if keyword in location_text:
            score += points
            reasons.append(f"{points} location_conditional:{keyword}")

    for keyword, points in location_preferences["skipped"].items():
        if keyword in location_text:
            score += points
            reasons.append(f"{points} location_skipped:{keyword}")

    return score, reasons


def classify_location(
    posting: JobPosting,
    scoring_config: dict[str, Any],
) -> str:
    location_text = clean_text(posting.location).lower()
    location_preferences = scoring_config["location_preferences"]

    if not location_text:
        return "unknown"

    has_allowed_location = _has_location_keyword(
        location_text,
        location_preferences["allowed"],
    )
    has_conditional_location = _has_location_keyword(
        location_text,
        location_preferences["conditional"],
    )
    has_skipped_location = _has_location_keyword(
        location_text,
        location_preferences["skipped"],
    )

    if has_allowed_location and _has_limited_travel(location_text):
        return "allowed_with_travel"

    if has_allowed_location and _has_travel_required(location_text):
        return "mixed"

    if has_allowed_location and has_skipped_location:
        return "mixed"

    if has_allowed_location and has_conditional_location:
        return "mixed"

    if has_allowed_location:
        return "allowed"

    if has_conditional_location:
        return "conditional"

    if has_skipped_location:
        return "skipped"

    return "unknown"


def _has_location_keyword(
    location_text: str,
    location_keywords: dict[str, int],
) -> bool:
    for keyword in location_keywords:
        if keyword in location_text:
            return True

    return False


def _has_travel_required(location_text: str) -> bool:
    travel_markers = [
        "travel required",
        "requires travel",
        "travel:",
        "travel -",
        "travel up to",
    ]

    for marker in travel_markers:
        if marker in location_text:
            return True

    return False


def _has_limited_travel(location_text: str) -> bool:
    limited_travel_markers = [
        "travel required 10-20%",
        "travel required 10 - 20%",
        "travel 10-20%",
        "travel 10 - 20%",
        "10-20% travel",
        "10 - 20% travel",
        "up to 20% travel",
        "travel up to 20%",
    ]

    for marker in limited_travel_markers:
        if marker in location_text:
            return True

    return False


def evaluate_top_match_eligibility(
    posting: JobPosting,
    score: int,
    score_reasons: list[str],
    location_status: str,
    scoring_config: dict[str, Any],
) -> tuple[bool, list[str]]:
    if location_status != "allowed":
        return False, [f"location_not_allowed:{location_status}"]

    if score <= 0:
        return False, ["score_not_positive"]

    if _has_negative_title_match(score_reasons):
        return False, ["negative_title_match"]

    excluded_keyword = _find_excluded_title_keyword(posting, scoring_config)
    if excluded_keyword:
        return False, [f"excluded_title_keyword:{excluded_keyword}"]

    if not _has_strong_technical_signal(score_reasons, scoring_config):
        return False, ["missing_strong_signal"]

    return True, ["eligible"]


def _has_negative_title_match(score_reasons: list[str]) -> bool:
    for reason in score_reasons:
        if reason.startswith("-") and "title:" in reason:
            return True

    return False


def _find_excluded_title_keyword(
    posting: JobPosting,
    scoring_config: dict[str, Any],
) -> str | None:
    title = clean_text(posting.title).lower()
    excluded_title_keywords = scoring_config["top_matches"]["excluded_title_keywords"]

    for keyword in excluded_title_keywords:
        if keyword in title:
            return keyword

    return None


def _has_strong_technical_signal(
    score_reasons: list[str],
    scoring_config: dict[str, Any],
) -> bool:
    strong_signals = scoring_config["top_matches"]["strong_signals"]

    for reason in score_reasons:
        for signal in strong_signals:
            if signal in reason:
                return True

    return False


def _build_body_text(posting: JobPosting) -> str:
    parts = [
        posting.remote_status,
        posting.salary_text,
        posting.description,
    ]

    return clean_text(" ".join(part for part in parts if part)).lower()