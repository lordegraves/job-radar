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

    if not isinstance(positive_keywords, dict):
        raise ScoringConfigError("positive_keywords must be a mapping")

    if not isinstance(negative_keywords, dict):
        raise ScoringConfigError("negative_keywords must be a mapping")

    return {
        "positive_keywords": _validate_keyword_scores(positive_keywords),
        "negative_keywords": _validate_keyword_scores(negative_keywords),
        "location_preferences": _validate_location_preferences(location_preferences),
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

    for keyword in location_preferences["allowed"]:
        if keyword in location_text:
            return "allowed"

    for keyword in location_preferences["conditional"]:
        if keyword in location_text:
            return "conditional"

    for keyword in location_preferences["skipped"]:
        if keyword in location_text:
            return "skipped"

    if not location_text:
        return "unknown"

    return "unknown"

def _build_body_text(posting: JobPosting) -> str:
    parts = [
        posting.remote_status,
        posting.salary_text,
        posting.description,
    ]

    return clean_text(" ".join(part for part in parts if part)).lower()