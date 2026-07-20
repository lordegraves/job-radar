"""Evaluate practical job eligibility separately from technical-fit scoring."""

from dataclasses import dataclass
import re

from job_radar.compensation import CompensationResult
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

EMPLOYMENT_FULL_TIME = "Full-time"
EMPLOYMENT_PART_TIME = "Part-time"
EMPLOYMENT_CONTRACT = "Contract"
EMPLOYMENT_TEMPORARY = "Temporary"
EMPLOYMENT_SEASONAL = "Seasonal"
EMPLOYMENT_INTERNSHIP = "Internship or apprenticeship"

SCHEDULE_ANY = "Any schedule"
SCHEDULE_DAY = "Day shift"
SCHEDULE_EVENING = "Evening shift"
SCHEDULE_NIGHT = "Night shift"
SCHEDULE_WEEKDAYS = "Weekdays"
SCHEDULE_WEEKENDS = "Weekends accepted"
SCHEDULE_FLEXIBLE = "Flexible schedule"


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


def evaluate_practical_eligibility(
    posting: JobPosting,
    preferences: ProfilePreferences | None,
    compensation: CompensationResult | None,
) -> EligibilityResult | None:
    """Combine practical checks without changing recommendation behavior."""

    if preferences is None:
        return None

    results = (
        evaluate_workplace_eligibility(posting, preferences),
        _evaluate_compensation_eligibility(
            preferences=preferences,
            compensation=compensation,
        ),
        _evaluate_employment_type_eligibility(
            posting=posting,
            preferences=preferences,
        ),
        _evaluate_schedule_eligibility(
            posting=posting,
            preferences=preferences,
        ),
        _evaluate_travel_eligibility(
            posting=posting,
            preferences=preferences,
        ),
    )
    evaluated_results = tuple(result for result in results if result is not None)

    if not evaluated_results:
        return EligibilityResult(status=ELIGIBILITY_ELIGIBLE)

    if any(
        result.status == ELIGIBILITY_NOT_ELIGIBLE
        for result in evaluated_results
    ):
        status = ELIGIBILITY_NOT_ELIGIBLE
    elif any(
        result.status == ELIGIBILITY_NEEDS_REVIEW
        for result in evaluated_results
    ):
        status = ELIGIBILITY_NEEDS_REVIEW
    else:
        status = ELIGIBILITY_ELIGIBLE

    return EligibilityResult(
        status=status,
        reasons=tuple(
            reason
            for result in evaluated_results
            for reason in result.reasons
        ),
    )


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
        return _evaluate_remote_arrangement(
            posting=posting,
            preferences=preferences,
        )

    return _evaluate_location_based_arrangement(
        posting=posting,
        preferences=preferences,
        arrangement=arrangement,
    )


def _posting_text(posting: JobPosting) -> str:
    return clean_text(
        " ".join(
            value
            for value in (
                posting.title,
                posting.location,
                posting.description,
            )
            if value
        )
    ).lower()


def _evaluate_employment_type_eligibility(
    *,
    posting: JobPosting,
    preferences: ProfilePreferences,
) -> EligibilityResult | None:
    if not preferences.employment_types:
        return None

    detected_types = _detect_employment_types(posting)

    if not detected_types:
        return EligibilityResult(
            status=ELIGIBILITY_NEEDS_REVIEW,
            reasons=(
                EligibilityReason(
                    code="employment_type_unclear",
                    message=(
                        "The posting does not clearly identify an employment type "
                        "that can be compared with this profile."
                    ),
                ),
            ),
        )

    matching_types = tuple(
        employment_type
        for employment_type in detected_types
        if employment_type in preferences.employment_types
    )

    if matching_types:
        return EligibilityResult(
            status=ELIGIBILITY_ELIGIBLE,
            reasons=(
                EligibilityReason(
                    code="employment_type_selected",
                    message=(
                        f"The posting identifies the job as "
                        f"{', '.join(matching_types)}, which this profile accepts."
                    ),
                ),
            ),
        )

    return EligibilityResult(
        status=ELIGIBILITY_NOT_ELIGIBLE,
        reasons=(
            EligibilityReason(
                code="employment_type_not_selected",
                message=(
                    f"The posting identifies the job as "
                    f"{', '.join(detected_types)}, which is not included in "
                    "this profile's selected employment types."
                ),
            ),
        ),
    )


def _detect_employment_types(posting: JobPosting) -> tuple[str, ...]:
    text = _posting_text(posting)
    detected: list[str] = []

    markers = (
        (
            EMPLOYMENT_INTERNSHIP,
            (
                "internship",
                "apprenticeship",
                "apprentice role",
                "apprentice position",
            ),
        ),
        (
            EMPLOYMENT_PART_TIME,
            (
                "part-time",
                "part time",
            ),
        ),
        (
            EMPLOYMENT_FULL_TIME,
            (
                "full-time",
                "full time",
            ),
        ),
        (
            EMPLOYMENT_TEMPORARY,
            (
                "temporary role",
                "temporary position",
                "temporary employment",
                "temp role",
                "temp position",
            ),
        ),
        (
            EMPLOYMENT_SEASONAL,
            (
                "seasonal role",
                "seasonal position",
                "seasonal employment",
            ),
        ),
        (
            EMPLOYMENT_CONTRACT,
            (
                "contract role",
                "contract position",
                "contract employment",
                "contractor role",
                "contractor position",
                "employment type contract",
                "job type contract",
            ),
        ),
    )

    for employment_type, employment_markers in markers:
        if any(marker in text for marker in employment_markers):
            detected.append(employment_type)

    return tuple(detected)


def _evaluate_schedule_eligibility(
    *,
    posting: JobPosting,
    preferences: ProfilePreferences,
) -> EligibilityResult | None:
    selected_schedule = preferences.schedule_preference

    if selected_schedule is None or selected_schedule == SCHEDULE_ANY:
        return None

    detected_schedules = _detect_schedule_requirements(posting)

    if not detected_schedules:
        return EligibilityResult(
            status=ELIGIBILITY_NEEDS_REVIEW,
            reasons=(
                EligibilityReason(
                    code="schedule_unclear",
                    message=(
                        "The posting does not clearly identify a work schedule "
                        "that can be compared with this profile."
                    ),
                ),
            ),
        )

    if "On-call" in detected_schedules:
        return EligibilityResult(
            status=ELIGIBILITY_NEEDS_REVIEW,
            reasons=(
                EligibilityReason(
                    code="on_call_schedule_needs_review",
                    message=(
                        "The posting includes an on-call requirement that should "
                        "be reviewed against this profile's schedule preference."
                    ),
                ),
            ),
        )

    if selected_schedule == SCHEDULE_WEEKENDS:
        if SCHEDULE_WEEKENDS in detected_schedules:
            return EligibilityResult(
                status=ELIGIBILITY_ELIGIBLE,
                reasons=(
                    EligibilityReason(
                        code="schedule_matches_preference",
                        message=(
                            "The posting includes weekend work and this profile "
                            "accepts weekends."
                        ),
                    ),
                ),
            )

        return EligibilityResult(
            status=ELIGIBILITY_NEEDS_REVIEW,
            reasons=(
                EligibilityReason(
                    code="schedule_needs_confirmation",
                    message=(
                        "The posting identifies a schedule, but the profile's "
                        "weekend acceptance does not establish whether that "
                        "schedule is preferred."
                    ),
                ),
            ),
        )

    if selected_schedule in detected_schedules:
        return EligibilityResult(
            status=ELIGIBILITY_ELIGIBLE,
            reasons=(
                EligibilityReason(
                    code="schedule_matches_preference",
                    message=(
                        f"The posting's {selected_schedule.lower()} matches this "
                        "profile's schedule preference."
                    ),
                ),
            ),
        )

    return EligibilityResult(
        status=ELIGIBILITY_NOT_ELIGIBLE,
        reasons=(
            EligibilityReason(
                code="schedule_conflicts_with_preference",
                message=(
                    f"The posting requires {', '.join(detected_schedules)}, but "
                    f"this profile selected {selected_schedule.lower()}."
                ),
            ),
        ),
    )


def _detect_schedule_requirements(posting: JobPosting) -> tuple[str, ...]:
    text = _posting_text(posting)
    detected: list[str] = []

    markers = (
        (SCHEDULE_NIGHT, ("night shift", "overnight shift", "third shift", "3rd shift")),
        (SCHEDULE_EVENING, ("evening shift", "second shift", "2nd shift")),
        (SCHEDULE_DAY, ("day shift", "first shift", "1st shift")),
        (
            SCHEDULE_WEEKENDS,
            (
                "weekends required",
                "weekend work required",
                "must work weekends",
                "weekend shift",
            ),
        ),
        (
            SCHEDULE_WEEKDAYS,
            (
                "weekday schedule",
                "weekdays only",
                "monday through friday",
                "monday-friday",
            ),
        ),
        (
            SCHEDULE_FLEXIBLE,
            (
                "flexible schedule",
                "flexible work schedule",
                "flexible hours",
            ),
        ),
        (
            "On-call",
            (
                "on-call",
                "on call",
            ),
        ),
    )

    for schedule, schedule_markers in markers:
        if any(marker in text for marker in schedule_markers):
            detected.append(schedule)

    return tuple(detected)


def _evaluate_travel_eligibility(
    *,
    posting: JobPosting,
    preferences: ProfilePreferences,
) -> EligibilityResult | None:
    if preferences.travel_tolerance is None:
        return None

    try:
        maximum_travel = int(preferences.travel_tolerance.rstrip("%"))
    except ValueError:
        return EligibilityResult(
            status=ELIGIBILITY_NEEDS_REVIEW,
            reasons=(
                EligibilityReason(
                    code="travel_preference_unclear",
                    message=(
                        "This profile's maximum travel preference could not be "
                        "interpreted as a percentage."
                    ),
                ),
            ),
        )

    required_travel = _extract_travel_percentage(posting)

    if required_travel is not None:
        if required_travel > maximum_travel:
            return EligibilityResult(
                status=ELIGIBILITY_NOT_ELIGIBLE,
                reasons=(
                    EligibilityReason(
                        code="travel_exceeds_profile_limit",
                        message=(
                            f"The posting may require up to {required_travel}% "
                            f"travel, above this profile's {maximum_travel}% limit."
                        ),
                    ),
                ),
            )

        return EligibilityResult(
            status=ELIGIBILITY_ELIGIBLE,
            reasons=(
                EligibilityReason(
                    code="travel_within_profile_limit",
                    message=(
                        f"The posting may require up to {required_travel}% travel, "
                        f"within this profile's {maximum_travel}% limit."
                    ),
                ),
            ),
        )

    if _has_vague_travel_requirement(posting):
        return EligibilityResult(
            status=ELIGIBILITY_NEEDS_REVIEW,
            reasons=(
                EligibilityReason(
                    code="travel_percentage_unclear",
                    message=(
                        "The posting requires travel but does not provide a clear "
                        "percentage to compare with this profile's limit."
                    ),
                ),
            ),
        )

    return None


def _extract_travel_percentage(posting: JobPosting) -> int | None:
    text = _posting_text(posting)
    ranges = re.findall(
        r"(\d{1,3})\s*(?:-|–|to)\s*(\d{1,3})\s*%\s*travel",
        text,
    )
    percentages = [
        int(value)
        for value in re.findall(
            r"(?:up to\s*)?(\d{1,3})\s*%\s*travel",
            text,
        )
    ]

    for lower, upper in ranges:
        percentages.extend((int(lower), int(upper)))

    travel_first_ranges = re.findall(
        r"travel(?:\s+required)?(?:\s+up to)?\s+"
        r"(\d{1,3})\s*(?:-|–|to)\s*(\d{1,3})\s*%",
        text,
    )
    travel_first_percentages = re.findall(
        r"travel(?:\s+required)?(?:\s+up to)?\s+(\d{1,3})\s*%",
        text,
    )

    for lower, upper in travel_first_ranges:
        percentages.extend((int(lower), int(upper)))

    percentages.extend(int(value) for value in travel_first_percentages)

    valid_percentages = [
        percentage for percentage in percentages if 0 <= percentage <= 100
    ]

    return max(valid_percentages) if valid_percentages else None


def _has_vague_travel_requirement(posting: JobPosting) -> bool:
    text = _posting_text(posting)

    return any(
        marker in text
        for marker in (
            "travel required",
            "requires travel",
            "travel is required",
            "must travel",
            "willingness to travel",
        )
    )


def _evaluate_compensation_eligibility(
    *,
    preferences: ProfilePreferences,
    compensation: CompensationResult | None,
) -> EligibilityResult | None:
    if preferences.compensation_floor_usd is None:
        return None

    if compensation is None or compensation.label == "Unknown":
        return EligibilityResult(
            status=ELIGIBILITY_NEEDS_REVIEW,
            reasons=(
                EligibilityReason(
                    code="compensation_unknown",
                    message=(
                        "The posting does not provide a usable annual compensation "
                        "range to compare with this profile's minimum."
                    ),
                ),
            ),
        )

    if compensation.label == "Below floor":
        return EligibilityResult(
            status=ELIGIBILITY_NOT_ELIGIBLE,
            reasons=(
                EligibilityReason(
                    code="compensation_below_floor",
                    message=(
                        f"The advertised compensation {compensation.range_label} "
                        "is below this profile's minimum."
                    ),
                ),
            ),
        )

    if compensation.label == "Partial range meets floor":
        return EligibilityResult(
            status=ELIGIBILITY_NEEDS_REVIEW,
            reasons=(
                EligibilityReason(
                    code="compensation_partially_meets_floor",
                    message=(
                        f"The advertised compensation {compensation.range_label} "
                        "only partially meets this profile's minimum."
                    ),
                ),
            ),
        )

    return EligibilityResult(
        status=ELIGIBILITY_ELIGIBLE,
        reasons=(
            EligibilityReason(
                code="compensation_meets_floor",
                message=(
                    f"The advertised compensation {compensation.range_label} "
                    "meets this profile's minimum."
                ),
            ),
        ),
    )


def _evaluate_remote_arrangement(
    *,
    posting: JobPosting,
    preferences: ProfilePreferences,
) -> EligibilityResult:
    posting_state = _extract_remote_restriction_state(posting.location)

    if posting_state is None:
        return EligibilityResult(
            status=ELIGIBILITY_ELIGIBLE,
            reasons=(
                EligibilityReason(
                    code="remote_arrangement_selected",
                    message="The job is remote and this profile accepts remote work.",
                ),
            ),
        )

    selected_locations = tuple(
        location.label for location in preferences.location_selections
    ) or preferences.preferred_locations

    if not selected_locations:
        return EligibilityResult(
            status=ELIGIBILITY_NEEDS_REVIEW,
            reasons=(
                EligibilityReason(
                    code="remote_region_needs_confirmation",
                    message=(
                        "The job is remote but appears restricted to a specific "
                        "state, and this profile has no selected locations to "
                        "confirm residency eligibility."
                    ),
                ),
            ),
        )

    selected_states = {
        state
        for location in selected_locations
        if (state := _extract_state_abbreviation(location)) is not None
    }

    if posting_state in selected_states:
        return EligibilityResult(
            status=ELIGIBILITY_ELIGIBLE,
            reasons=(
                EligibilityReason(
                    code="remote_region_matches_selected_area",
                    message=(
                        "The job is remote and its state restriction matches "
                        "one of this profile's selected locations."
                    ),
                ),
            ),
        )

    if selected_states:
        return EligibilityResult(
            status=ELIGIBILITY_NOT_ELIGIBLE,
            reasons=(
                EligibilityReason(
                    code="remote_region_outside_selected_areas",
                    message=(
                        "The job is remote but appears restricted to a state "
                        "outside this profile's selected locations."
                    ),
                ),
            ),
        )

    return EligibilityResult(
        status=ELIGIBILITY_NEEDS_REVIEW,
        reasons=(
            EligibilityReason(
                code="remote_region_needs_confirmation",
                message=(
                    "The job is remote but its state restriction could not be "
                    "compared reliably with this profile's selected locations."
                ),
            ),
        ),
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


def _extract_remote_restriction_state(value: str | None) -> str | None:
    normalized = clean_text(value).lower()

    if not normalized:
        return None

    multi_location_markers = (
        ";",
        "|",
        "multiple locations",
        "various locations",
    )

    if any(marker in normalized for marker in multi_location_markers):
        return None

    broad_remote_markers = (
        "united states",
        "usa",
        "nationwide",
        "us only",
        "u.s. only",
    )

    if any(marker in normalized for marker in broad_remote_markers):
        return None

    return _extract_state_abbreviation(value)


def _extract_state_abbreviation(value: str | None) -> str | None:
    normalized = _normalize_location_label(value)
    tokens = normalized.split()

    state_abbreviations = {
        "al",
        "ak",
        "az",
        "ar",
        "ca",
        "co",
        "ct",
        "de",
        "fl",
        "ga",
        "hi",
        "id",
        "il",
        "in",
        "ia",
        "ks",
        "ky",
        "la",
        "me",
        "md",
        "ma",
        "mi",
        "mn",
        "ms",
        "mo",
        "mt",
        "ne",
        "nv",
        "nh",
        "nj",
        "nm",
        "ny",
        "nc",
        "nd",
        "oh",
        "ok",
        "or",
        "pa",
        "ri",
        "sc",
        "sd",
        "tn",
        "tx",
        "ut",
        "vt",
        "va",
        "wa",
        "wv",
        "wi",
        "wy",
    }

    for token in reversed(tokens):
        if token in state_abbreviations:
            return token

    return None


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
