"""Load and save the user-editable job-fit preference board."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

from job_radar.config import ConfigError
from job_radar.normalize import clean_text
from job_radar.profile_fit import build_initial_fit_signals
from job_radar.profile_context import managed_profile_to_candidate_profile
from job_radar.profile_models import FIT_SIGNAL_CATEGORIES, FitSignal, ManagedProfile
from job_radar.profile_scoring import resolve_effective_scoring_config
from job_radar.profile_storage import get_profile, update_profile
from job_radar.resume_loader import load_resume_text


_SKILL_SECTION_HEADINGS = {
    "areas of expertise",
    "competencies",
    "core competencies",
    "core skills",
    "expertise",
    "key skills",
    "skills",
    "technical skills",
}
_SECTION_END_HEADINGS = {
    "certifications",
    "education",
    "employment",
    "employment history",
    "experience",
    "professional experience",
    "projects",
    "references",
    "summary",
    "work experience",
}
_NON_CAPABILITY_LINES = _SKILL_SECTION_HEADINGS | {
    "active",
    "expired certifications",
}
_MAX_RESUME_SUGGESTIONS = 20
_MANAGED_TOP_MATCH_MIN_SCORE = 40
_MANAGED_REVIEW_MIN_SCORE = 20


def build_profile_fit_board(
    database_path: str | Path,
    profile_id: str,
    *,
    base_directory: str | Path | None = None,
) -> tuple[ManagedProfile, tuple[FitSignal, ...]]:
    """Load one profile and return its saved or conservatively inferred board."""

    profile = get_profile(database_path, profile_id)
    if profile is None or profile.archived:
        raise ConfigError("The selected profile is not available.")

    initial = list(build_initial_fit_signals(profile))
    if profile.fit_signals or base_directory is None:
        return profile, tuple(initial)

    seen = {signal.term.casefold() for signal in initial}
    for signal in _resume_backed_suggestions(profile, base_directory):
        if signal.term.casefold() in seen:
            continue
        seen.add(signal.term.casefold())
        initial.append(signal)
    return profile, tuple(initial)


def _resume_backed_suggestions(
    profile: ManagedProfile,
    base_directory: str | Path,
) -> tuple[FitSignal, ...]:
    """Suggest bounded exact résumé evidence without deciding that it is strong."""

    if profile.resume is None:
        return ()
    candidate = managed_profile_to_candidate_profile(
        profile,
        base_directory=Path(base_directory),
    )
    if candidate.resume is None:
        return ()
    try:
        resume_text = load_resume_text(candidate.resume.source_path)
    except ConfigError:
        return ()

    normalized_resume = clean_text(resume_text).casefold()
    suggestions: list[str] = []
    for role in profile.preferences.target_roles:
        normalized_role = clean_text(role).casefold()
        if len(normalized_role) >= 4 and normalized_role in normalized_resume:
            suggestions.append(role)

    in_skill_section = False
    for raw_line in resume_text.splitlines():
        line = " ".join(raw_line.split()).strip(" •▪◦-–—")
        normalized = clean_text(line).casefold().rstrip(":")
        if normalized in _SKILL_SECTION_HEADINGS:
            in_skill_section = True
            continue
        if in_skill_section and normalized in _SECTION_END_HEADINGS:
            break
        if not in_skill_section or not _is_capability_line(line, normalized):
            continue
        suggestions.extend(_resume_capability_terms(line))

    result: list[FitSignal] = []
    seen: set[str] = set()
    for term in suggestions:
        normalized = term.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(
            FitSignal(
                term=term,
                category="review",
                explanation=(
                    "Junior found these exact words in your résumé. Move this to "
                    "Strong Match only when it describes work you can clearly "
                    "demonstrate."
                ),
                evidence_source="resume",
            )
        )
        if len(result) >= _MAX_RESUME_SUGGESTIONS:
            break
    return tuple(result)


def _resume_capability_terms(line: str) -> tuple[str, ...]:
    """Turn dense skills-list lines into phrases postings can realistically use."""

    if ":" not in line:
        parts = [part.strip() for part in line.replace("/", " & ").split(" & ")]
        if len(parts) > 1 and all(len(part.split()) >= 2 for part in parts):
            return tuple(parts)
        return (line,)

    label, raw_values = (part.strip() for part in line.split(":", maxsplit=1))
    values = tuple(
        value.strip()
        for value in raw_values.replace("/", ",").split(",")
        if value.strip()
    )
    return tuple(
        part
        for part in (label, *values)
        if _is_capability_line(part, clean_text(part).casefold())
    )


def _is_capability_line(line: str, normalized: str) -> bool:
    if normalized in _NON_CAPABILITY_LINES:
        return False
    if not 2 <= len(line) <= 120:
        return False
    if "@" in line or normalized.startswith(("http://", "https://")):
        return False
    return any(character.isalpha() for character in line)


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
        target_roles=profile.preferences.target_roles,
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
    *,
    target_roles: tuple[str, ...] = (),
) -> dict[str, Any]:
    scoring = deepcopy(current_scoring)

    positive_keywords = _mapping_section(scoring, "positive_keywords")
    negative_keywords = _mapping_section(scoring, "negative_keywords")
    top_matches = _mapping_section(scoring, "top_matches")
    review_needed = _mapping_section(scoring, "review_needed")

    top_signals = _string_list(top_matches, "strong_signals")
    top_review_signals = _string_list(top_matches, "review_signals")
    review_signals = _string_list(review_needed, "strong_signals")
    excluded_titles = _string_list(top_matches, "excluded_title_keywords")

    # Managed Job Fit terms carry 10 points each and exact target roles carry
    # the established 30-point title weight. The legacy 120/100 YAML floors
    # required an unrealistic ten exact résumé phrases before any job could be
    # reviewed. Two demonstrated skills now reach review; a target title plus
    # one demonstrated skill can reach Top Match, subject to every existing
    # résumé-gap and practical-eligibility gate.
    if (
        top_matches.get("min_score") == 120
        and review_needed.get("min_score") == 100
    ):
        top_matches["min_score"] = _MANAGED_TOP_MATCH_MIN_SCORE
        review_needed["min_score"] = _MANAGED_REVIEW_MIN_SCORE

    for signal in signals:
        term = clean_text(signal.term).lower()
        if not term:
            continue

        scoring_terms = _scoring_terms_for_signal(
            term,
            target_roles=target_roles,
            split_capability=signal.category in {"strong", "review"},
        )

        for scoring_term in {term, *scoring_terms}:
            _remove_mapping_term(positive_keywords, scoring_term)
            _remove_mapping_term(negative_keywords, scoring_term)
            _remove_signal_term(top_signals, scoring_term)
            _remove_signal_term(top_review_signals, scoring_term)
            _remove_signal_term(review_signals, scoring_term)
            _remove_signal_term(excluded_titles, scoring_term)

        if signal.category == "strong":
            for scoring_term in scoring_terms:
                positive_keywords[scoring_term] = 10
                scope = (
                    "title"
                    if _is_target_role(scoring_term, target_roles)
                    else "body"
                )
                top_signals.append(f"{scope}:{scoring_term}")
        elif signal.category == "review":
            for scoring_term in scoring_terms:
                top_review_signals.append(scoring_term)
                review_signals.append(f"body:{scoring_term}")
        elif signal.category == "avoid":
            negative_keywords[term] = -15
            excluded_titles.append(term)

    return scoring


def _is_target_role(term: str, target_roles: tuple[str, ...]) -> bool:
    """Reserve title matching for role names the user explicitly selected."""

    normalized = clean_text(term).casefold()
    return any(clean_text(role).casefold() == normalized for role in target_roles)


def _scoring_terms_for_signal(
    term: str,
    *,
    target_roles: tuple[str, ...],
    split_capability: bool,
) -> tuple[str, ...]:
    """Reuse dense saved capabilities without rewriting the user's board."""

    if not split_capability or _is_target_role(term, target_roles):
        return (term,)
    result = tuple(
        clean_text(part).lower()
        for part in _resume_capability_terms(term)
        if clean_text(part)
    )
    return result or (term,)


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
