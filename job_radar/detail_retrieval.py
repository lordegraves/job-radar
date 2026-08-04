"""Conservatively decide which listing summaries need a full description."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any, Callable

from job_radar.candidate_profile import CandidateProfile
from job_radar.normalize import clean_text


@dataclass(frozen=True)
class DetailRetrievalDecision:
    retrieve: bool
    reason: str


DetailRetrievalPlanner = Callable[[str, str | None], DetailRetrievalDecision]

_AMBIGUOUS_ROLE_WORDS = {
    "administrator", "architect", "consultant", "developer", "engineer",
    "infrastructure", "operations", "platform", "reliability", "support",
    "system", "systems", "technical", "technology",
}
_GENERIC_WORDS = {
    "associate", "chief", "global", "intern", "junior", "lead", "manager",
    "principal", "senior", "specialist", "staff", "sr", "vice", "president",
}


def build_detail_retrieval_planner(
    candidate_profile: CandidateProfile | None,
    scoring_config: dict[str, Any],
) -> tuple[DetailRetrievalPlanner, str]:
    """Return a profile-owned planner; uncertainty always retrieves detail."""

    positive_phrases = _normalized_phrases(
        list(scoring_config.get("positive_keywords", {}))
        + list(scoring_config.get("top_matches", {}).get("strong_signals", []))
        + (candidate_profile.target_roles if candidate_profile else [])
        + (candidate_profile.core_strengths if candidate_profile else [])
        + (candidate_profile.credible_adjacent if candidate_profile else [])
    )
    exclusion_phrases = _normalized_phrases(
        list(scoring_config.get("negative_keywords", {}))
        + list(scoring_config.get("top_matches", {}).get("excluded_title_keywords", []))
        + (candidate_profile.avoid if candidate_profile else [])
    )
    positive_tokens = _meaningful_tokens(positive_phrases)
    signature = sha256(
        json.dumps(
            {"positive": positive_phrases, "excluded": exclusion_phrases, "version": 1},
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    def plan(title: str, _location: str | None) -> DetailRetrievalDecision:
        normalized_title = clean_text(title).lower()
        if not normalized_title:
            return DetailRetrievalDecision(True, "The listing title is missing.")
        if any(_contains_phrase(normalized_title, phrase) for phrase in positive_phrases):
            return DetailRetrievalDecision(True, "The title matches selected target work.")
        excluded = next(
            (
                phrase
                for phrase in exclusion_phrases
                if _contains_phrase(normalized_title, phrase)
            ),
            None,
        )
        if excluded:
            return DetailRetrievalDecision(
                False,
                f"The title clearly matches the profile exclusion '{excluded}'.",
            )
        title_tokens = set(re.findall(r"[a-z0-9+#.]+", normalized_title))
        if title_tokens & positive_tokens:
            return DetailRetrievalDecision(True, "The title contains related work evidence.")
        if title_tokens & _AMBIGUOUS_ROLE_WORDS:
            return DetailRetrievalDecision(
                True,
                "The title is ambiguous enough to require the complete description.",
            )
        return DetailRetrievalDecision(
            False,
            "The title has no connection to selected target work and is not ambiguous.",
        )

    return plan, signature


def _normalized_phrases(values: list[object]) -> list[str]:
    phrases: list[str] = []
    for value in values:
        phrase = clean_text(str(value).split(":", 1)[-1]).lower()
        if phrase and phrase not in phrases:
            phrases.append(phrase)
    return phrases


def _meaningful_tokens(phrases: list[str]) -> set[str]:
    return {
        token
        for phrase in phrases
        for token in re.findall(r"[a-z0-9+#.]+", phrase)
        if len(token) >= 3 and token not in _GENERIC_WORDS
    }


def _contains_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None
