"""Evaluate practical job eligibility separately from technical-fit scoring."""

from dataclasses import dataclass
import re

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

    return _evaluate_location_based_arrangement(
        posting=posting,
        preferences=preferences,
        arrangement=arrangement,
    )


def _evaluate_location_based_arrangement(
    posting: JobPosting,
    preferences: ProfilePreferences,
    arrangement: str,
) -> EligibilityResult:
    selected_locations = tuple(
        location.label for location in preferences.location_selections
    ) or preferences.preferred_locations

    if not selected_locations:
        return EligibilityResult(
            status=ELIGIBILITY_NEEDS_REVIEW,
            reasons=(
                EligibilityReason(
                    code="no_preferred_locations_configured",
                    message=(
                        f"The job is {arrangement.lower()}, but this profile does "
                        "not have any approved commute locations configured."
                    ),
                ),
            ),
        )

    posting_location = _normalize_location_label(posting.location)

    if not posting_location:
        return EligibilityResult(
            status=ELIGIBILITY_NEEDS_REVIEW,
            reasons=(
                EligibilityReason(
                    code="job_location_unclear",
                    message=(
                        f"The job is {arrangement.lower()}, but the posting does "
                        "not provide a clear workplace location."
                    ),
                ),
            ),
        )

    for selected_location in selected_locations:
        normalized_selected_location = _normalize_location_label(selected_location)

        if _location_labels_match(
            posting_location=posting_location,
            selected_location=normalized_selected_location,
        ):
            return EligibilityResult(
                status=ELIGIBILITY_ELIGIBLE,
                reasons=(
                    EligibilityReason(
                        code="location_matches_selected_area",
                        message=(
                            f"The job is {arrangement.lower()} and its location "
                            f"matches the selected area {selected_location}."
                        ),
                    ),
                ),
            )

    if _looks_like_specific_city_state(posting.location):
        approved_locations = "; ".join(selected_locations)
        return EligibilityResult(
            status=ELIGIBILITY_NOT_ELIGIBLE,
            reasons=(
                EligibilityReason(
                    code="location_outside_selected_areas",
                    message=(
                        f"The job is {arrangement.lower()} in "
                        f"{clean_text(posting.location)}, which does not match "
                        f"the profile's selected areas: {approved_locations}."
                    ),
                ),
            ),
        )

    return EligibilityResult(
        status=ELIGIBILITY_NEEDS_REVIEW,
        reasons=(
            EligibilityReason(
                code="job_location_ambiguous",
                message=(
                    f"The job is {arrangement.lower()}, but its location could "
                    "not be matched reliably against the profile's selected areas."
                ),
            ),
        ),
    )


def _normalize_location_label(value: str | None) -> str:
    normalized = clean_text(value).lower()

    arrangement_markers = (
        "on-site",
        "onsite",
        "on site",
        "in-person",
        "in person",
        "hybrid",
    )

    for marker in arrangement_markers:
        normalized = normalized.replace(marker, " ")

    punctuation = ",;:/()[]|-"

    for character in punctuation:
        normalized = normalized.replace(character, " ")

    state_names = {
        "alabama": "al",
        "alaska": "ak",
        "arizona": "az",
        "arkansas": "ar",
        "california": "ca",
        "colorado": "co",
        "connecticut": "ct",
        "delaware": "de",
        "florida": "fl",
        "georgia": "ga",
        "hawaii": "hi",
        "idaho": "id",
        "illinois": "il",
        "indiana": "in",
        "iowa": "ia",
        "kansas": "ks",
        "kentucky": "ky",
        "louisiana": "la",
        "maine": "me",
        "maryland": "md",
        "massachusetts": "ma",
        "michigan": "mi",
        "minnesota": "mn",
        "mississippi": "ms",
        "missouri": "mo",
        "montana": "mt",
        "nebraska": "ne",
        "nevada": "nv",
        "new hampshire": "nh",
        "new jersey": "nj",
        "new mexico": "nm",
        "new york": "ny",
        "north carolina": "nc",
        "north dakota": "nd",
        "ohio": "oh",
        "oklahoma": "ok",
        "oregon": "or",
        "pennsylvania": "pa",
        "rhode island": "ri",
        "south carolina": "sc",
        "south dakota": "sd",
        "tennessee": "tn",
        "texas": "tx",
        "utah": "ut",
        "vermont": "vt",
        "virginia": "va",
        "washington": "wa",
        "west virginia": "wv",
        "wisconsin": "wi",
        "wyoming": "wy",
    }

    for state_name in sorted(state_names, key=len, reverse=True):
        normalized = re.sub(
            rf"\b{re.escape(state_name)}\b",
            state_names[state_name],
            normalized,
        )

    return clean_text(normalized)


def _location_labels_match(
    *,
    posting_location: str,
    selected_location: str,
) -> bool:
    if not posting_location or not selected_location:
        return False

    return (
        posting_location == selected_location
        or posting_location in selected_location
        or selected_location in posting_location
    )


def _looks_like_specific_city_state(value: str | None) -> bool:
    normalized = clean_text(value)

    if not normalized:
        return False

    broad_location_markers = (
        "multiple locations",
        "various locations",
        "united states",
        "us only",
        "nationwide",
        "regional",
    )

    if any(marker in normalized.lower() for marker in broad_location_markers):
        return False

    return "," in normalized or any(
        character.isdigit() for character in normalized
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
