from pathlib import Path
from typing import Any

import yaml

from job_radar.models import JobPosting
from job_radar.normalize import clean_text


class ScoringConfigError(Exception):
    pass


def load_scoring_config(path: str | Path) -> dict[str, dict[str, int]]:
    config_path = Path(path)

    if not config_path.exists():
        raise ScoringConfigError(f"Scoring config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict):
        raise ScoringConfigError("Scoring config must be a mapping")

    positive_keywords = data.get("positive_keywords", {})
    negative_keywords = data.get("negative_keywords", {})

    if not isinstance(positive_keywords, dict):
        raise ScoringConfigError("positive_keywords must be a mapping")

    if not isinstance(negative_keywords, dict):
        raise ScoringConfigError("negative_keywords must be a mapping")

    return {
        "positive_keywords": _validate_keyword_scores(positive_keywords),
        "negative_keywords": _validate_keyword_scores(negative_keywords),
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


def score_posting(
    posting: JobPosting,
    scoring_config: dict[str, dict[str, int]],
) -> tuple[int, list[str]]:
    searchable_text = _build_searchable_text(posting)

    score = 0
    reasons: list[str] = []

    for keyword, points in scoring_config["positive_keywords"].items():
        if keyword in searchable_text:
            score += points
            reasons.append(f"+{points} {keyword}")

    for keyword, points in scoring_config["negative_keywords"].items():
        if keyword in searchable_text:
            score += points
            reasons.append(f"{points} {keyword}")

    return score, reasons


def _build_searchable_text(posting: JobPosting) -> str:
    parts = [
        posting.title,
        posting.location,
        posting.remote_status,
        posting.salary_text,
        posting.description,
    ]

    return clean_text(" ".join(part for part in parts if part)).lower()