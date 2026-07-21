"""Translate active scoring configuration into a read-only, user-facing view."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from job_radar.profile_scoring import resolve_effective_scoring_config
from job_radar.scoring import ScoringConfigError, load_scoring_config


@dataclass(frozen=True)
class WeightedPreference:
    """One configured term and the base points it adds or subtracts."""

    term: str
    points: int


@dataclass(frozen=True)
class ScoringPreferencesView:
    """Plain-language representation of the rules already used by scans."""

    positive_keywords: tuple[WeightedPreference, ...] = ()
    negative_keywords: tuple[WeightedPreference, ...] = ()
    allowed_locations: tuple[str, ...] = ()
    conditional_locations: tuple[WeightedPreference, ...] = ()
    skipped_locations: tuple[WeightedPreference, ...] = ()
    top_match_min_score: int | None = None
    review_needed_min_score: int | None = None
    excluded_title_keywords: tuple[str, ...] = ()
    top_match_signals: tuple[str, ...] = ()
    review_needed_signals: tuple[str, ...] = ()
    review_excluded_location_statuses: tuple[str, ...] = ()
    load_error: str | None = None


def build_scoring_preferences_view(
    scoring_path: str | Path,
) -> ScoringPreferencesView:
    """Load file-based rules for legacy users and direct configuration views."""

    try:
        config = load_scoring_config(scoring_path)
    except (OSError, ScoringConfigError) as error:
        return ScoringPreferencesView(load_error=str(error))

    return _build_scoring_preferences_view(config)


def build_effective_scoring_preferences_view(
    database_path: str | Path,
    scoring_path: str | Path,
) -> ScoringPreferencesView:
    """Show the same effective rules that the next scan will use."""

    try:
        config = resolve_effective_scoring_config(
            database_path,
            scoring_path,
        )
    except (OSError, ScoringConfigError) as error:
        return ScoringPreferencesView(load_error=str(error))

    return _build_scoring_preferences_view(config)


def _build_scoring_preferences_view(
    config: dict[str, Any],
) -> ScoringPreferencesView:
    locations = config["location_preferences"]
    top_matches = config["top_matches"]
    review_needed = config["review_needed"]

    return ScoringPreferencesView(
        positive_keywords=_weighted_preferences(config["positive_keywords"]),
        negative_keywords=_weighted_preferences(config["negative_keywords"]),
        # Allowed-location values are intentionally not presented as score points:
        # the current engine uses these terms to determine eligibility and awards 0.
        allowed_locations=tuple(locations["allowed"]),
        conditional_locations=_weighted_preferences(locations["conditional"]),
        skipped_locations=_weighted_preferences(locations["skipped"]),
        top_match_min_score=top_matches["min_score"],
        review_needed_min_score=review_needed["min_score"],
        excluded_title_keywords=tuple(top_matches["excluded_title_keywords"]),
        top_match_signals=_friendly_signals(top_matches["strong_signals"]),
        review_needed_signals=_friendly_signals(review_needed["strong_signals"]),
        review_excluded_location_statuses=tuple(
            review_needed["excluded_location_statuses"]
        ),
    )


def _weighted_preferences(values: dict[str, int]) -> tuple[WeightedPreference, ...]:
    return tuple(
        WeightedPreference(term=term, points=points)
        for term, points in values.items()
    )


def _friendly_signals(values: list[str]) -> tuple[str, ...]:
    labels = {"title": "Job title", "body": "Job description"}
    friendly: list[str] = []

    for value in values:
        source, separator, term = value.partition(":")
        if separator and source in labels:
            friendly.append(f"{labels[source]}: {term}")
        else:
            friendly.append(value)

    return tuple(friendly)
