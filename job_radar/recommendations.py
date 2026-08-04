"""Turn profile-owned fit facts into occupation-neutral user guidance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from job_radar.eligibility import (
    ELIGIBILITY_NEEDS_REVIEW,
    ELIGIBILITY_NOT_ELIGIBLE,
)
from job_radar.recommendation_constants import (
    ACTION_APPLY,
    ACTION_HOLD,
    ACTION_PASS,
    ACTION_PREVIOUSLY_REVIEWED,
    ACTION_TAILOR_RESUME,
    ACTION_TRACK_STATUS,
    HISTORY_ALREADY_APPLIED,
    HISTORY_PRIOR_NO_INTERVIEW,
    HISTORY_PRIOR_NO_INTERVIEW_DESPITE_STRONG_MATCH,
    HISTORY_PRIOR_REJECTED,
    HISTORY_PRIOR_SKIPPED_SIMILAR_ROLE,
    RECOMMENDATION_SUMMARY_ORDER,
    RISK_BELOW_COMPENSATION_FLOOR,
    RISK_HARD_LOCATION_MISMATCH,
    RISK_LOCATION_NEEDS_CONFIRMATION,
    TRACK_STATUS_ALREADY_APPLIED_MESSAGE,
)

if TYPE_CHECKING:
    from job_radar.scored_posting import ScoredPosting


_RECOMMENDATION_SUMMARY_ORDER = RECOMMENDATION_SUMMARY_ORDER


def _get_recommendation_summary_counts(
    scored_postings: list[ScoredPosting],
) -> dict[str, int]:
    counts = {action: 0 for action in _RECOMMENDATION_SUMMARY_ORDER}
    for scored_posting in scored_postings:
        action = _get_recommended_action(scored_posting)
        counts[action] = counts.get(action, 0) + 1
    return counts


def _format_score_reasons(score_reasons: list[str]) -> str:
    return ", ".join(score_reasons) if score_reasons else "None"


def _get_compensation_label(scored_posting: ScoredPosting) -> str:
    return scored_posting.compensation.label if scored_posting.compensation else "Unknown"


def _get_compensation_range_label(scored_posting: ScoredPosting) -> str:
    if scored_posting.compensation is None:
        return "Unknown"
    return scored_posting.compensation.range_label


def _get_resume_match_label(scored_posting: ScoredPosting) -> str:
    return scored_posting.resume_match.label if scored_posting.resume_match else "Unknown"


def _format_resume_evidence(scored_posting: ScoredPosting) -> str:
    if scored_posting.posting.normalization_state == "incomplete":
        return "Not verified because the complete job description was unavailable"
    if scored_posting.resume_match is None or not scored_posting.resume_match.evidence:
        return "None"
    return "; ".join(scored_posting.resume_match.evidence)


def _format_resume_gaps(scored_posting: ScoredPosting) -> str:
    if scored_posting.posting.normalization_state == "incomplete":
        return "Qualification gaps could not be verified without the complete job description"
    if scored_posting.resume_match is None:
        return "None"
    groups: list[str] = []
    if scored_posting.resume_match.gaps:
        groups.extend(scored_posting.resume_match.gaps)
    return "\n".join(groups) if groups else "None"


def _get_technical_match_label(scored_posting: ScoredPosting) -> str:
    """Describe fit using this profile's resume and configured score signals."""

    resume_label = _get_resume_match_label(scored_posting)
    if resume_label != "Unknown":
        return resume_label

    signal_count = len(_get_profile_fit_signal_labels(scored_posting))
    if signal_count >= 4:
        return "Very Strong"
    if signal_count >= 2:
        return "Strong"
    if signal_count == 1:
        return "Moderate"
    return "Unknown"


def _get_hiring_probability_label(scored_posting: ScoredPosting) -> str:
    """Provide a cautious label without occupation- or employer-specific guesses."""

    risks = _get_hiring_risk_flags(scored_posting)
    resume_match = _get_resume_match_label(scored_posting)

    if (
        RISK_HARD_LOCATION_MISMATCH in risks
        or RISK_BELOW_COMPENSATION_FLOOR in risks
        or _has_profile_avoid_risk(risks)
    ):
        return "Very Low"

    if scored_posting.top_match_eligible:
        if resume_match == "Very Strong":
            return "High"
        if resume_match in {"Strong", "Medium", "Unknown"}:
            return "Medium"
        return "Low"

    if scored_posting.review_needed_eligible:
        return "Medium" if resume_match in {"Very Strong", "Strong"} else "Low"

    return "Low" if resume_match in {"Very Strong", "Strong", "Medium"} else "Very Low"


def _get_recommended_action(scored_posting: ScoredPosting) -> str:
    """Recommend an action from profile-owned fit and practical eligibility."""

    if scored_posting.application is not None:
        return ACTION_TRACK_STATUS

    if (
        scored_posting.resume_match is not None
        and scored_posting.resume_match.has_critical_gap
    ):
        return ACTION_PASS

    if (
        scored_posting.eligibility is not None
        and scored_posting.eligibility.status == ELIGIBILITY_NOT_ELIGIBLE
    ):
        return ACTION_PASS

    risks = _get_hiring_risk_flags(scored_posting)
    if (
        RISK_BELOW_COMPENSATION_FLOOR in risks
        or RISK_HARD_LOCATION_MISMATCH in risks
        or _has_profile_avoid_risk(risks)
    ):
        return ACTION_PASS

    history_action = _get_history_recommended_action(scored_posting)
    if history_action is not None:
        return history_action

    if (
        scored_posting.eligibility is not None
        and scored_posting.eligibility.status == ELIGIBILITY_NEEDS_REVIEW
    ):
        return ACTION_HOLD

    resume_match = _get_resume_match_label(scored_posting)
    if scored_posting.top_match_eligible:
        if resume_match in {"Very Strong", "Strong", "Unknown"}:
            return ACTION_APPLY
        if resume_match == "Medium":
            return ACTION_TAILOR_RESUME
        return ACTION_HOLD

    if scored_posting.potential_top_match_eligible:
        if resume_match in {"Very Strong", "Strong"}:
            return (
                ACTION_HOLD
                if scored_posting.resume_match
                and scored_posting.resume_match.gaps
                else ACTION_APPLY
            )
        if resume_match == "Medium":
            return ACTION_TAILOR_RESUME
        return ACTION_HOLD

    if scored_posting.review_needed_eligible:
        return ACTION_HOLD

    return ACTION_PASS


def _get_history_recommended_action(scored_posting: ScoredPosting) -> str | None:
    history_reasons = set(scored_posting.history_risk_reasons or [])
    if HISTORY_ALREADY_APPLIED in history_reasons:
        return ACTION_TRACK_STATUS
    if (
        HISTORY_PRIOR_NO_INTERVIEW_DESPITE_STRONG_MATCH in history_reasons
        or HISTORY_PRIOR_NO_INTERVIEW in history_reasons
        or HISTORY_PRIOR_REJECTED in history_reasons
    ):
        return ACTION_TRACK_STATUS
    if scored_posting.history_risk_level == "blocker_review":
        return ACTION_PREVIOUSLY_REVIEWED
    if HISTORY_PRIOR_SKIPPED_SIMILAR_ROLE in history_reasons:
        return ACTION_PREVIOUSLY_REVIEWED
    return None


def _format_risk_summary(risks: list[str]) -> str:
    return ", ".join(_format_risk_label(risk) for risk in risks)


def _format_risk_label(risk: str) -> str:
    if risk == RISK_HARD_LOCATION_MISMATCH:
        return "the job is outside your selected area"
    if risk == RISK_LOCATION_NEEDS_CONFIRMATION:
        return "the location needs confirmation"
    if risk.startswith("profile gap: "):
        return f"the profile gap '{risk.removeprefix('profile gap: ')}'"
    if risk.startswith("profile avoid match: "):
        return f"the profile exclusion '{risk.removeprefix('profile avoid match: ')}'"
    return risk


def _get_action_rationale(scored_posting: ScoredPosting) -> str:
    action = _get_recommended_action(scored_posting)
    resume_match = _get_resume_match_label(scored_posting)
    risks = _get_hiring_risk_flags(scored_posting)

    if action == ACTION_TRACK_STATUS:
        return TRACK_STATUS_ALREADY_APPLIED_MESSAGE
    if action == ACTION_PREVIOUSLY_REVIEWED:
        return (
            "Previously reviewed: similar role history already exists. Revisit only "
            "if the scope, location, compensation, or posting details changed."
        )
    if action == ACTION_PASS:
        if risks:
            rationale = f"Pass: {_format_risk_summary(risks)} does not fit this profile."
        else:
            rationale = "Pass: this job did not meet this profile's configured fit rules."
        return _append_history_rationale(scored_posting, rationale)
    if action == ACTION_HOLD:
        if (
            scored_posting.eligibility is not None
            and scored_posting.eligibility.status == ELIGIBILITY_NEEDS_REVIEW
        ):
            rationale = "Needs review before applying. See the review items below."
        elif risks:
            rationale = f"Needs review because of {_format_risk_summary(risks)}."
        else:
            rationale = "Needs review before deciding whether to apply."
        return _append_history_rationale(scored_posting, rationale)
    if action == ACTION_TAILOR_RESUME:
        return _append_history_rationale(
            scored_posting,
            f"The role fits the profile, but the current resume match is {resume_match.lower()}.",
        )
    return _append_history_rationale(
        scored_posting,
        "This job meets the profile's configured fit and practical eligibility rules.",
    )


def _format_eligibility_reason_text(scored_posting: ScoredPosting) -> str:
    if scored_posting.eligibility is None:
        return "No practical eligibility concerns were recorded."
    messages = [
        reason.message.strip()
        for reason in scored_posting.eligibility.reasons
        if reason.message.strip() and _is_unresolved_eligibility_reason(reason.code)
    ]
    return " ".join(messages) if messages else "No practical eligibility concerns were recorded."


def _is_unresolved_eligibility_reason(reason_code: str) -> bool:
    """Positive facts belong in summary badges, not in the user's review list."""

    positive_reason_codes = {
        "active_clearance_requirement_accepted",
        "employment_type_selected",
        "on_call_requirement_accepted",
        "schedule_matches_preference",
        "travel_within_profile_limit",
        "compensation_meets_floor",
        "remote_arrangement_selected",
        "remote_region_matches_selected_area",
        "location_matches_selected_area",
    }
    return reason_code not in positive_reason_codes


def _append_history_rationale(
    scored_posting: ScoredPosting,
    rationale: str,
) -> str:
    accepted_on_call_note = _format_accepted_on_call_note(scored_posting)
    if accepted_on_call_note:
        rationale = f"{rationale} {accepted_on_call_note}"
    history_note = _format_history_rationale_note(scored_posting)
    return f"{rationale} {history_note}" if history_note else rationale


def _format_accepted_on_call_note(scored_posting: ScoredPosting) -> str | None:
    """Keep an accepted operational obligation visible without blocking the job."""

    if scored_posting.eligibility is None:
        return None
    if any(
        reason.code == "on_call_requirement_accepted"
        for reason in scored_posting.eligibility.reasons
    ):
        return "This job includes on-call work, which this profile accepts."
    return None


def _format_history_rationale_note(scored_posting: ScoredPosting) -> str | None:
    if scored_posting.history_risk_level == "blocker_review":
        return "Review the prior similar-role history before applying."
    if scored_posting.history_risk_level == "caution":
        return "Prior similar-role history adds a caution for review."
    return None


def _is_actionable_posting(scored_posting: ScoredPosting) -> bool:
    return _get_recommended_action(scored_posting) not in {
        ACTION_PASS,
        ACTION_PREVIOUSLY_REVIEWED,
    }


def _is_top_match_display_posting(scored_posting: ScoredPosting) -> bool:
    if not scored_posting.top_match_eligible:
        return False
    if (
        scored_posting.eligibility is not None
        and scored_posting.eligibility.status == ELIGIBILITY_NEEDS_REVIEW
    ):
        return False
    return _get_recommended_action(scored_posting) in {
        ACTION_APPLY,
        ACTION_TAILOR_RESUME,
    }


def _format_hiring_risk_flags(scored_posting: ScoredPosting) -> str:
    risks = _get_hiring_risk_flags(scored_posting)
    return "; ".join(risks) if risks else "None"


def _get_hiring_risk_flags(scored_posting: ScoredPosting) -> list[str]:
    """Return only profile-derived or practical risks, never occupation guesses."""

    risks: list[str] = []
    confirmed_location_mismatch = (
        scored_posting.eligibility is not None
        and scored_posting.eligibility.status == ELIGIBILITY_NOT_ELIGIBLE
        and any(
            reason.code
            in {
                "specific_location_outside_selected_areas",
                "location_outside_selected_areas",
                "remote_region_outside_selected_areas",
            }
            for reason in scored_posting.eligibility.reasons
        )
    )
    if scored_posting.location_status == "skipped" or confirmed_location_mismatch:
        risks.append(RISK_HARD_LOCATION_MISMATCH)
    elif scored_posting.location_status in {"mixed", "conditional", "unknown"}:
        risks.append(RISK_LOCATION_NEEDS_CONFIRMATION)

    if _get_compensation_label(scored_posting) == "Below floor":
        risks.append(RISK_BELOW_COMPENSATION_FLOOR)

    for avoid_match in scored_posting.profile_avoid_matches or []:
        risks.append(f"profile avoid match: {avoid_match}")

    if scored_posting.resume_match is not None:
        for gap in scored_posting.resume_match.gaps:
            risks.append(f"profile gap: {gap}")

    return _dedupe_preserving_order(risks)


def _get_profile_fit_signal_labels(scored_posting: ScoredPosting) -> list[str]:
    labels: list[str] = []
    if scored_posting.score_evidence is not None:
        labels.extend(
            evidence.signal_label
            for evidence in scored_posting.score_evidence
            if evidence.points > 0 and evidence.source in {"title", "body"}
        )
    else:
        labels.extend(
            reason.split(maxsplit=1)[1]
            for reason in scored_posting.score_reasons
            if reason.startswith("+")
            and " " in reason
            and any(marker in reason for marker in ("title:", "body:"))
        )
    return _dedupe_preserving_order(labels)


def _has_profile_avoid_risk(risks: list[str]) -> bool:
    return any(risk.startswith("profile avoid match: ") for risk in risks)


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped
