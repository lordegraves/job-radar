"""Explain contradictory profile choices without silently changing them."""

from dataclasses import dataclass

from job_radar.profile_models import ManagedProfile


@dataclass(frozen=True)
class ProfileAdvisory:
    code: str
    message: str


def build_profile_advisories(profile: ManagedProfile | None) -> tuple[ProfileAdvisory, ...]:
    """Return narrow, user-actionable warnings for conflicting saved choices."""

    if profile is None:
        return ()
    preferences = profile.preferences
    advisories: list[ProfileAdvisory] = []
    roles = {_normalize(value) for value in preferences.target_roles}
    exclusions = {_normalize(value) for value in preferences.exclusions}
    overlap = sorted(roles.intersection(exclusions))
    if overlap:
        advisories.append(
            ProfileAdvisory(
                code="target_role_excluded",
                message=(
                    "This profile both targets and excludes: "
                    f"{', '.join(overlap)}. Remove it from one list."
                ),
            )
        )

    leadership_markers = ("director", "head", "vice president", "vp")
    if (
        any(any(marker in role for marker in leadership_markers) for role in roles)
        and preferences.seniority_levels
        and "Executive" not in preferences.seniority_levels
    ):
        advisories.append(
            ProfileAdvisory(
                code="leadership_level_conflict",
                message=(
                    "This profile targets leadership work but filters out the "
                    "Executive job level. Include Executive or revise the target roles."
                ),
            )
        )

    if (
        preferences.compensation_floor_usd is not None
        and preferences.compensation_target_usd is not None
        and preferences.compensation_floor_usd > preferences.compensation_target_usd
    ):
        advisories.append(
            ProfileAdvisory(
                code="compensation_range_conflict",
                message=(
                    "The minimum compensation is higher than the preferred target. "
                    "Lower the minimum or raise the target."
                ),
            )
        )

    categories: dict[str, set[str]] = {}
    for signal in profile.fit_signals:
        categories.setdefault(_normalize(signal.term), set()).add(signal.category)
    conflicting_signals = sorted(
        term for term, values in categories.items() if "avoid" in values and values.intersection({"strong", "review"})
    )
    if conflicting_signals:
        advisories.append(
            ProfileAdvisory(
                code="fit_signal_conflict",
                message=(
                    "Job Fit both accepts and avoids: "
                    f"{', '.join(conflicting_signals)}. Keep each item in one group."
                ),
            )
        )
    return tuple(advisories)


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())
