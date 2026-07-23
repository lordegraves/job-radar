"""Describe profile-owned company recommendations and their evidence."""

from dataclasses import dataclass


NEW = "NEW"
ADDED = "ADDED"
DISMISSED = "DISMISSED"
NOT_RELEVANT = "NOT_RELEVANT"
MAYBE_LATER = "MAYBE_LATER"
NEEDS_SETUP = "NEEDS_SETUP"
UNAVAILABLE = "UNAVAILABLE"
RECOMMENDATION_STATES = {
    NEW,
    ADDED,
    DISMISSED,
    NOT_RELEVANT,
    MAYBE_LATER,
    NEEDS_SETUP,
    UNAVAILABLE,
}


@dataclass(frozen=True)
class CompanyRecommendation:
    """Present one recommendation without exposing its internal score."""

    profile_id: str
    employer_id: str
    employer_name: str
    evidence: tuple[str, ...]
    can_scan: bool
    state: str
    generated_at: str
    last_evaluated_at: str
