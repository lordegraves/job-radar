"""Load and save the user-editable job-fit preference board."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

from job_radar.config import ConfigError
from job_radar.normalize import clean_text
from job_radar.profile_fit import build_initial_fit_signals
from job_radar.profile_models import FIT_SIGNAL_CATEGORIES, FitSignal, ManagedProfile
from job_radar.profile_scoring import resolve_effective_scoring_config
from job_radar.profile_storage import get_profile, update_profile


def build_profile_fit_board(
    database_path: str | Path,
    profile_id: str,
) -> tuple[ManagedProfile, tuple[FitSignal, ...]]:
    """Load one profile and return its saved or conservatively inferred board."""

    profile = get_profile(database_path, profile_id)
    if profile is None or profile.archived:
        raise ConfigError("The selected profile is not available.")

    return profile, build_initial_fit_signals(profile)


def save_profile_fit_board(
    database_path: str | Path,
    scoring_path: str | Path,
    profile_id: str,
    raw_signals_json: str,
) -> ManagedProfile:
    """Save the ordered board and apply its choices to future scan scoring."""

    profile = get_profile(database_path, profile_id)
    if profile is None or profile.archived:
        raise ConfigError("The selected profile is not available.")

    signals = _parse_fit_signals(raw_signals_json)
    current_scoring = resolve_effective_scoring_config(
        database_path,
        scoring_path,
    )
    scoring_config = _apply_fit_signals_to_scoring_config(
        current_scoring,
        signals,
    )
    updated = replace(
        profile,
        scoring_config=scoring_config,
        fit_signals=signals,
    )

    if not update_profile(database_path, updated):
        raise ConfigError("The selected profile is no longer available.")

    return updated


def _apply_fit_signals_to_scoring_config(
    current_scoring: dict[str, Any],
    signals: tuple[FitSignal, ...],
) -> dict[str, Any]:
    scoring = deepcopy(current_scoring)

    positive_keywords = _mapping_section(scoring, "positive_keywords")
    negative_keywords = _mapping_section(scoring, "negative_keywords")
    top_matches = _mapping_section(scoring, "top_matches")
    review_needed = _mapping_section(scoring, "review_needed")

    top_signals = _string_list(top_matches, "strong_signals")
    review_signals = _string_list(review_needed, "strong_signals")
    excluded_titles = _string_list(top_matches, "excluded_title_keywords")

    for signal in signals:
        term = clean_text(signal.term).lower()
        if not term:
            continue

        _remove_mapping_term(positive_keywords, term)
        _remove_mapping_term(negative_keywords, term)
        _remove_signal_term(top_signals, term)
        _remove_signal_term(review_signals, term)
        _remove_signal_term(excluded_titles, term)

        if signal.category == "strong":
            positive_keywords[term] = 10
            top_signals.append(f"title:{term}")
        elif signal.category == "review":
            review_signals.append(f"body:{term}")
        elif signal.category == "avoid":
            negative_keywords[term] = -15
            excluded_titles.append(term)

    return scoring


def _mapping_section(
    scoring: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    section = scoring.get(key)
    if not isinstance(section, dict):
        section = {}
        scoring[key] = section
    return section


def _string_list(
    section: dict[str, Any],
    key: str,
) -> list[str]:
    values = section.get(key)
    if not isinstance(values, list):
        values = []
        section[key] = values
    return values


def _remove_mapping_term(
    values: dict[str, Any],
    normalized_term: str,
) -> None:
    for existing_term in tuple(values):
        if (
            isinstance(existing_term, str)
            and clean_text(existing_term).lower() == normalized_term
        ):
            del values[existing_term]


def _remove_signal_term(
    values: list[str],
    normalized_term: str,
) -> None:
    values[:] = [
        value
        for value in values
        if not (
            isinstance(value, str)
            and _normalized_signal_term(value) == normalized_term
        )
    ]


def _normalized_signal_term(value: str) -> str:
    normalized = clean_text(value).lower()
    for prefix in ("title:", "body:"):
        if normalized.startswith(prefix):
            return normalized[len(prefix) :].strip()
    return normalized


def _parse_fit_signals(raw_signals_json: str) -> tuple[FitSignal, ...]:
    try:
        raw_signals = json.loads(raw_signals_json)
    except json.JSONDecodeError as error:
        raise ConfigError("The job-fit preferences could not be read.") from error

    if not isinstance(raw_signals, list):
        raise ConfigError("The job-fit preferences must be a list.")

    signals: list[FitSignal] = []
    seen_terms: set[str] = set()

    for raw_signal in raw_signals:
        if not isinstance(raw_signal, dict):
            raise ConfigError("Each job-fit preference must be an item.")

        raw_term = raw_signal.get("term")
        raw_category = raw_signal.get("category")
        raw_explanation = raw_signal.get("explanation", "")

        if not isinstance(raw_term, str) or not raw_term.strip():
            raise ConfigError("Each job-fit preference needs a name.")

        if raw_category not in FIT_SIGNAL_CATEGORIES:
            raise ConfigError("Each job-fit preference needs a valid category.")

        if not isinstance(raw_explanation, str):
            raise ConfigError("Job-fit explanations must be text.")

        term = " ".join(raw_term.split())
        normalized_term = term.casefold()

        if normalized_term in seen_terms:
            raise ConfigError(f'"{term}" appears more than once.')

        seen_terms.add(normalized_term)
        signals.append(
            FitSignal(
                term=term,
                category=raw_category,
                explanation=raw_explanation.strip(),
                evidence_source="user",
                user_overridden=True,
            )
        )

    return tuple(signals)
