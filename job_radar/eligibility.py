"""Represent practical job eligibility separately from technical-fit scoring."""

from dataclasses import dataclass


ELIGIBILITY_ELIGIBLE = "eligible"
ELIGIBILITY_NEEDS_REVIEW = "needs_review"
ELIGIBILITY_NOT_ELIGIBLE = "not_eligible"

VALID_ELIGIBILITY_STATUSES = {
    ELIGIBILITY_ELIGIBLE,
    ELIGIBILITY_NEEDS_REVIEW,
    ELIGIBILITY_NOT_ELIGIBLE,
}


@dataclass(frozen=True)
class EligibilityReason:
    """Describe one practical fact that affected job eligibility."""

    code: str
    message: str

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("eligibility reason code cannot be empty")

        if not self.message.strip():
            raise ValueError("eligibility reason message cannot be empty")


@dataclass(frozen=True)
class EligibilityResult:
    """Carry a practical eligibility status and its human-readable reasons."""

    status: str
    reasons: tuple[EligibilityReason, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in VALID_ELIGIBILITY_STATUSES:
            raise ValueError(f"unsupported eligibility status: {self.status}")
