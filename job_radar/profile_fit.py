"""Build user-visible job-fit signals from profile and scoring evidence."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from job_radar.profile_models import FitSignal, ManagedProfile


@dataclass(frozen=True)
class _SignalCandidate:
    term: str
    category: str
    explanation: str
    evidence_source: str
    priority: int


_CATEGORY_PRIORITY = {
    "ignored": 0,
    "strong": 1,
    "review": 2,
    "avoid": 3,
}


def build_initial_fit_signals(profile: ManagedProfile) -> tuple[FitSignal, ...]:
    """Return saved signals or infer a conservative first board for one profile."""

    if profile.fit_signals:
        return profile.fit_signals

    candidates: dict[str, _SignalCandidate] = {}

    _add_profile_terms(
        candidates,
        profile.preferences.core_strengths,
        category="strong",
        explanation="Your profile identifies this as a demonstrated strength.",
    )
    _add_profile_terms(
        candidates,
        profile.preferences.credible_adjacent,
        category="review",
        explanation=(
            "Your profile shows related or adjacent experience, so jobs emphasizing "
            "this should receive a closer review."
        ),
    )
    _add_profile_terms(
        candidates,
        profile.preferences.learning_or_gap,
        category="review",
        explanation=(
            "Your profile identifies this as an area where experience or ownership "
            "may need clarification."
        ),
    )
    _add_profile_terms(
        candidates,
        profile.preferences.exclusions,
        category="avoid",
        explanation="Your profile identifies this as work you want to avoid.",
    )

    scoring_config = profile.scoring_config
    if isinstance(scoring_config, Mapping):
        _add_scoring_keywords(
            candidates,
            scoring_config.get("positive_keywords"),
            category="strong",
            explanation="The current scoring rules treat this as positive job-fit evidence.",
            priority=10,
        )
        _add_scoring_signals(
            candidates,
            scoring_config,
            section_name="top_matches",
            category="strong",
            explanation="The current scoring rules use this as strong-match evidence.",
            priority=15,
        )
        _add_scoring_signals(
            candidates,
            scoring_config,
            section_name="review_needed",
            category="review",
            explanation="The current scoring rules use this as a reason for closer review.",
            priority=20,
        )
        _add_scoring_keywords(
            candidates,
            scoring_config.get("negative_keywords"),
            category="avoid",
            explanation="The current scoring rules treat this as negative job-fit evidence.",
            priority=25,
        )

    return tuple(
        FitSignal(
            term=candidate.term,
            category=candidate.category,
            explanation=candidate.explanation,
            evidence_source=candidate.evidence_source,
        )
        for candidate in candidates.values()
    )


def _add_profile_terms(
    candidates: dict[str, _SignalCandidate],
    terms: Iterable[str],
    *,
    category: str,
    explanation: str,
) -> None:
    for term in terms:
        _add_candidate(
            candidates,
            _SignalCandidate(
                term=_display_term(term),
                category=category,
                explanation=explanation,
                evidence_source="profile",
                priority=30,
            ),
        )


def _add_scoring_keywords(
    candidates: dict[str, _SignalCandidate],
    raw_keywords: object,
    *,
    category: str,
    explanation: str,
    priority: int,
) -> None:
    if not isinstance(raw_keywords, Mapping):
        return

    for raw_term in raw_keywords:
        if not isinstance(raw_term, str) or not raw_term.strip():
            continue

        _add_candidate(
            candidates,
            _SignalCandidate(
                term=_display_term(raw_term),
                category=category,
                explanation=explanation,
                evidence_source="scoring",
                priority=priority,
            ),
        )


def _add_scoring_signals(
    candidates: dict[str, _SignalCandidate],
    scoring_config: Mapping[object, object],
    *,
    section_name: str,
    category: str,
    explanation: str,
    priority: int,
) -> None:
    section = scoring_config.get(section_name)
    if not isinstance(section, Mapping):
        return

    raw_signals = section.get("strong_signals")
    if not isinstance(raw_signals, list):
        return

    for raw_signal in raw_signals:
        if not isinstance(raw_signal, str):
            continue

        term = _signal_term(raw_signal)
        if not term:
            continue

        _add_candidate(
            candidates,
            _SignalCandidate(
                term=_display_term(term),
                category=category,
                explanation=explanation,
                evidence_source="scoring",
                priority=priority,
            ),
        )


def _add_candidate(
    candidates: dict[str, _SignalCandidate],
    candidate: _SignalCandidate,
) -> None:
    key = candidate.term.casefold()
    existing = candidates.get(key)

    if existing is None:
        candidates[key] = candidate
        return

    if candidate.priority > existing.priority:
        candidates[key] = candidate
        return

    if (
        candidate.priority == existing.priority
        and _CATEGORY_PRIORITY[candidate.category]
        > _CATEGORY_PRIORITY[existing.category]
    ):
        candidates[key] = candidate


def _signal_term(raw_signal: str) -> str:
    normalized = raw_signal.strip()

    for prefix in ("title:", "body:"):
        if normalized.casefold().startswith(prefix):
            return normalized[len(prefix) :].strip()

    return normalized


def _display_term(raw_term: str) -> str:
    normalized = " ".join(raw_term.replace("_", " ").split())
    return normalized.title()
