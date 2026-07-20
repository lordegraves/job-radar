"""Evaluate practical job eligibility separately from technical-fit scoring."""

from dataclasses import dataclass

from job_radar.models import JobPosting
from job_radar.normalize import clean_text
from job_radar.profile_models import ProfilePreferences


ELIGIBILITY_ELIGIBLE = "eligible"
ELIGIBILITY_NEEDS_REVIEW = "needs_review"
ELIGIBILITY_NOT_ELIGIBLE = "not_eligible"

VALID_ELIGIBILITY_STATUSES = {
    ELIGIBILITY_ELIGIBLE,
    ELIGIBILITY_NEEDS_REVIEW,
    ELIGIBILITY_NOT_ELIGIBLE,
}

ARRANGEMENT_REMOTE = "Remote"
ARRANGEMENT_HYBRID = "Hybrid"
ARRANGEMENT_ON_SITE = "On-site"


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


def evaluate_workplace_eligibility(
    posting: JobPosting,
    preferences: ProfilePreferences | None,
) -> EligibilityResult | None:
    """Evaluate workplace arrangement without changing legacy scan behavior."""

    if preferences is None:
        return None

    arrangement = _classify_workplace_arrangement(posting)

    if arrangement is None:
        return EligibilityResult(
            status=ELIGIBILITY_NEEDS_REVIEW,
            reasons=(
                EligibilityReason(
                    code="workplace_arrangement_unclear",
                    message=(
                        "The posting does not clearly say whether the job is "
                        "remote, hybrid, or on-site."
                    ),
                ),
            ),
        )

    if arrangement not in preferences.work_arrangements:
        return EligibilityResult(
            status=ELIGIBILITY_NOT_ELIGIBLE,
            reasons=(
                EligibilityReason(
                    code="workplace_arrangement_not_selected",
                    message=(
                        f"The job is {arrangement.lower()}, but that workplace "
                        "arrangement is not included in this profile."
                    ),
                ),
            ),
        )

    if arrangement == ARRANGEMENT_REMOTE:
        return EligibilityResult(
            status=ELIGIBILITY_ELIGIBLE,
            reasons=(
                EligibilityReason(
                    code="remote_arrangement_selected",
                    message="The job is remote and this profile accepts remote work.",
                ),
            ),
        )

    return EligibilityResult(
        status=ELIGIBILITY_NEEDS_REVIEW,
        reasons=(
            EligibilityReason(
                code="commute_eligibility_not_evaluated",
                message=(
                    f"The job is {arrangement.lower()} and that arrangement is "
                    "accepted, but the job location still needs to be checked "
                    "against the profile's selected commute areas."
                ),
            ),
        ),
    )


def _classify_workplace_arrangement(posting: JobPosting) -> str | None:
    text = clean_text(
        " ".join(
            value
            for value in (
                posting.remote_status,
                posting.location,
            )
            if value
        )
    ).lower()

    if not text:
        return None

    if "hybrid" in text:
        return ARRANGEMENT_HYBRID

    if any(
        marker in text
        for marker in (
            "on-site",
            "onsite",
            "on site",
            "in-person",
            "in person",
        )
    ):
        return ARRANGEMENT_ON_SITE

    if any(
        marker in text
        for marker in (
            "remote",
            "virtual",
            "work from home",
            "work-from-home",
        )
    ):
        return ARRANGEMENT_REMOTE

    return None
