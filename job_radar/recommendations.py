from __future__ import annotations

from typing import TYPE_CHECKING

from job_radar.recommendation_constants import (
    ACTION_APPLY,
    ACTION_APPLY_WITH_RECRUITER,
    ACTION_HOLD,
    ACTION_NETWORK_FIRST,
    ACTION_PASS,
    ACTION_PREVIOUSLY_REVIEWED,
    ACTION_TAILOR_RESUME,
    ACTION_TRACK_STATUS,
    RECOMMENDATION_SUMMARY_ORDER,
    RISK_BELOW_COMPENSATION_FLOOR,
    RISK_GENERIC_REMOTE_COMPETITION,
    RISK_HARD_LOCATION_MISMATCH,
    RISK_HIGH_COMPETITION_EMPLOYER,
    RISK_LEADERSHIP_AMBIGUITY,
    RISK_LOCATION_NEEDS_CONFIRMATION,
    RISK_PRODUCTION_KUBERNETES_TRANSLATION,
    RISK_ROLE_FAMILY_MISMATCH,
    RISK_SECURITY_DOMAIN_TRANSLATION,
    RISK_SOFTWARE_HEAVY_TRANSLATION,
    RISK_SUPPORT_ROLE,
    TRACK_STATUS_ALREADY_APPLIED_MESSAGE,
    HISTORY_ALREADY_APPLIED,
    HISTORY_PRIOR_NO_INTERVIEW,
    HISTORY_PRIOR_NO_INTERVIEW_DESPITE_STRONG_MATCH,
    HISTORY_PRIOR_REJECTED,
    HISTORY_PRIOR_SKIPPED_SIMILAR_ROLE,
)

if TYPE_CHECKING:
    from job_radar.reporting import ScoredPosting


HIGH_COMPETITION_COMPANY_KEYWORDS = [
    "openai",
    "anthropic",
    "nvidia",
    "meta",
    "google",
    "microsoft",
    "apple",
    "netflix",
    "databricks",
]


ROLE_FAMILY_MISMATCH_TITLE_KEYWORDS = [
    "frontend",
    "full stack",
    "product manager",
    "program manager",
    "project manager",
    "account manager",
    "business development",
    "developer advocate",
    "compliance",
    "facilities",
    "sourcing",
    "engineering manager",
    "technical program manager",
    "technical project manager",
    "technical product manager",
    "product",
    "partnership",
    "delivery lead",
    "enterprise applications",
    "forward deployed",
    "director",
    "gtm",
    "go-to-market",
    "sales engineer",
    "customer success",
    "project executive",
    "incident manager",
    "field services manager",
]


_RECOMMENDATION_SUMMARY_ORDER = RECOMMENDATION_SUMMARY_ORDER


def _get_recommendation_summary_counts(
    scored_postings: list[ScoredPosting],
) -> dict[str, int]:
    recommendation_counts = {
        recommendation: 0 for recommendation in _RECOMMENDATION_SUMMARY_ORDER
    }

    for scored_posting in scored_postings:
        recommended_action = _get_recommended_action(scored_posting)
        recommendation_counts[recommended_action] = (
            recommendation_counts.get(recommended_action, 0) + 1
        )

    return recommendation_counts


def _format_score_reasons(score_reasons: list[str]) -> str:
    if not score_reasons:
        return "None"

    return ", ".join(score_reasons)


def _get_compensation_label(scored_posting: ScoredPosting) -> str:
    if scored_posting.compensation is None:
        return "Unknown"

    return scored_posting.compensation.label


def _get_compensation_range_label(scored_posting: ScoredPosting) -> str:
    if scored_posting.compensation is None:
        return "Unknown"

    return scored_posting.compensation.range_label


def _get_resume_match_label(scored_posting: ScoredPosting) -> str:
    if scored_posting.resume_match is None:
        return "Unknown"

    return scored_posting.resume_match.label


def _format_resume_evidence(scored_posting: ScoredPosting) -> str:
    if scored_posting.resume_match is None or not scored_posting.resume_match.evidence:
        return "None"

    return "; ".join(scored_posting.resume_match.evidence)


def _format_resume_gaps(scored_posting: ScoredPosting) -> str:
    if scored_posting.resume_match is None or not scored_posting.resume_match.gaps:
        return "None"

    return "; ".join(scored_posting.resume_match.gaps)


def _get_technical_match_label(scored_posting: ScoredPosting) -> str:
    title_text = _get_title_text(scored_posting)
    positive_labels = _get_positive_score_labels(scored_posting.score_reasons)

    if _has_any_title_keyword(title_text, ROLE_FAMILY_MISMATCH_TITLE_KEYWORDS):
        return "Weak"

    strong_signal_count = _count_matching_labels(
        positive_labels,
        [
            "hpc",
            "linux",
            "slurm",
            "gpu",
            "cluster",
            "datacenter",
            "data center",
            "infrastructure",
            "site reliability",
            "sre",
            "storage",
            "hardware",
        ],
    )

    if strong_signal_count >= 4:
        return "Very Strong"

    if strong_signal_count >= 2:
        return "Strong"

    if strong_signal_count >= 1:
        return "Moderate"

    return "Weak"


def _get_hiring_probability_label(scored_posting: ScoredPosting) -> str:
    risks = _get_hiring_risk_flags(scored_posting)
    technical_match = _get_technical_match_label(scored_posting)
    resume_match = _get_resume_match_label(scored_posting)

    if RISK_HARD_LOCATION_MISMATCH in risks:
        return "Very Low"

    if RISK_ROLE_FAMILY_MISMATCH in risks or RISK_SUPPORT_ROLE in risks:
        return "Low"

    if resume_match == "Weak":
        return "Low"

    if (
        RISK_SOFTWARE_HEAVY_TRANSLATION in risks
        or RISK_GENERIC_REMOTE_COMPETITION in risks
        or RISK_PRODUCTION_KUBERNETES_TRANSLATION in risks
        or RISK_LEADERSHIP_AMBIGUITY in risks
        or RISK_SECURITY_DOMAIN_TRANSLATION in risks
        or RISK_HIGH_COMPETITION_EMPLOYER in risks
    ):
        if technical_match in {"Very Strong", "Strong"}:
            return "Medium"
        return "Low"

    if resume_match == "Medium":
        return "Medium"

    if resume_match == "Strong" and technical_match == "Very Strong":
        return "Medium"

    if technical_match == "Very Strong":
        return "High"

    if technical_match == "Strong":
        return "Medium"

    if technical_match == "Moderate":
        return "Low"

    return "Very Low"


def _get_recommended_action(scored_posting: ScoredPosting) -> str:
    # A tracked application is not a new lead. The scan may still see the
    # posting, but reports should point back to the existing application.
    if scored_posting.application is not None:
        return ACTION_TRACK_STATUS

    hiring_probability = _get_hiring_probability_label(scored_posting)
    technical_match = _get_technical_match_label(scored_posting)
    resume_match = _get_resume_match_label(scored_posting)
    risks = _get_hiring_risk_flags(scored_posting)

    if RISK_BELOW_COMPENSATION_FLOOR in risks:
        return ACTION_PASS

    if RISK_HARD_LOCATION_MISMATCH in risks:
        return ACTION_PASS

    if RISK_ROLE_FAMILY_MISMATCH in risks or RISK_SUPPORT_ROLE in risks:
        return ACTION_PASS

    if any(risk.startswith("profile avoid match: ") for risk in risks):
        return ACTION_PASS

    history_action = _get_history_recommended_action(scored_posting)

    if history_action is not None:
        return history_action

    if (
        technical_match in {"Very Strong", "Strong"}
        and RISK_HIGH_COMPETITION_EMPLOYER in risks
        and (
            RISK_SOFTWARE_HEAVY_TRANSLATION in risks
            or RISK_SECURITY_DOMAIN_TRANSLATION in risks
            or RISK_LEADERSHIP_AMBIGUITY in risks
        )
    ):
        return ACTION_NETWORK_FIRST

    if (
        technical_match in {"Very Strong", "Strong"}
        and RISK_SOFTWARE_HEAVY_TRANSLATION in risks
        and (
            RISK_PRODUCTION_KUBERNETES_TRANSLATION in risks
            or RISK_SECURITY_DOMAIN_TRANSLATION in risks
        )
    ):
        return ACTION_NETWORK_FIRST

    if (
        technical_match in {"Very Strong", "Strong"}
        and RISK_LEADERSHIP_AMBIGUITY in risks
    ):
        return ACTION_NETWORK_FIRST

    if hiring_probability == "High" and technical_match == "Very Strong":
        if risks or resume_match != "Very Strong":
            return ACTION_APPLY_WITH_RECRUITER
        return ACTION_APPLY

    if hiring_probability == "Medium" and technical_match == "Very Strong":
        return ACTION_APPLY_WITH_RECRUITER

    if hiring_probability == "Medium" and technical_match == "Strong":
        return ACTION_TAILOR_RESUME

    if (
        technical_match in {"Very Strong", "Strong"}
        and RISK_SOFTWARE_HEAVY_TRANSLATION in risks
    ):
        return ACTION_NETWORK_FIRST

    if hiring_probability == "Low":
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
    readable_risks = [_format_risk_label(risk) for risk in risks]

    return ", ".join(readable_risks)


def _format_risk_label(risk: str) -> str:
    if risk == RISK_PRODUCTION_KUBERNETES_TRANSLATION:
        return "how your infrastructure background translates to production Kubernetes"

    if risk == RISK_SOFTWARE_HEAVY_TRANSLATION:
        return "the software-heavy parts of the role"

    if risk == RISK_SECURITY_DOMAIN_TRANSLATION:
        return "the security-domain parts of the role"

    if risk == RISK_HIGH_COMPETITION_EMPLOYER:
        return "the high-competition employer"

    if risk == RISK_GENERIC_REMOTE_COMPETITION:
        return "remote-role competition"

    if risk == RISK_LEADERSHIP_AMBIGUITY:
        return "the leadership expectations"

    return risk


def _get_action_rationale(scored_posting: ScoredPosting) -> str:
    recommended_action = _get_recommended_action(scored_posting)
    hiring_probability = _get_hiring_probability_label(scored_posting)
    technical_match = _get_technical_match_label(scored_posting)
    resume_match = _get_resume_match_label(scored_posting)
    risks = _get_hiring_risk_flags(scored_posting)

    if recommended_action == ACTION_APPLY:
        return _append_history_rationale(
            scored_posting,
            (
                "Clean apply: very strong technical match, very strong resume match, "
                "high hiring probability, and no hiring risks."
            ),
        )

    if recommended_action == ACTION_APPLY_WITH_RECRUITER:
        if risks:
            return _append_history_rationale(
                scored_posting,
                (
                    "Apply with recruiter outreach. Strong fit, but frame "
                    f"{_format_risk_summary(risks)} clearly."
                ),
            )

        return _append_history_rationale(
            scored_posting,
            (
                "Apply with recruiter outreach. Promising role, but review the resume "
                f"match because it is currently {resume_match.lower()}."
            ),
        )

    if recommended_action == ACTION_NETWORK_FIRST:
        if risks:
            return _append_history_rationale(
                scored_posting,
                (
                    "Network first. Useful technical signal, but direct apply is weaker "
                    f"because of {_format_risk_summary(risks)}."
                ),
            )

        return _append_history_rationale(
            scored_posting,
            (
                "Network first: this role has some alignment, but the match is not "
                "strong enough for a direct apply-first approach."
            ),
        )

    if recommended_action == ACTION_TAILOR_RESUME:
        return _append_history_rationale(
            scored_posting,
            (
                "Tailor resume: the role is worth reviewing, but the current resume "
                f"match is {resume_match.lower()} and hiring probability is "
                f"{hiring_probability.lower()}."
            ),
        )

    if recommended_action == ACTION_TRACK_STATUS:
        return TRACK_STATUS_ALREADY_APPLIED_MESSAGE

    if recommended_action == ACTION_PREVIOUSLY_REVIEWED:
        return (
            "Previously reviewed: similar role history already exists. Revisit only "
            "if the scope, location, compensation, or posting details materially changed."
        )

    if recommended_action == ACTION_HOLD:
        return _append_history_rationale(
            scored_posting,
            (
                "Hold: the role has limited hiring probability right now and should "
                "not take priority over stronger matches."
            ),
        )

    if risks:
        return _append_history_rationale(
            scored_posting,
            f"Pass: blocked by {', '.join(risks)}.",
        )

    return _append_history_rationale(
        scored_posting,
        (
            "Pass: technical match is "
            f"{technical_match.lower()} and hiring probability is "
            f"{hiring_probability.lower()}."
        ),
    )


def _append_history_rationale(
    scored_posting: ScoredPosting,
    rationale: str,
) -> str:
    history_note = _format_history_rationale_note(scored_posting)

    if history_note is None:
        return rationale

    return f"{rationale} {history_note}"


def _format_history_rationale_note(scored_posting: ScoredPosting) -> str | None:
    if scored_posting.history_risk_level == "blocker_review":
        return (
            "Review prior history before applying because a similar role had "
            "a prior history signal."
        )

    if scored_posting.history_risk_level == "caution":
        return (
            "Use caution because prior similar application history adds risk."
        )

    return None


def _is_actionable_posting(scored_posting: ScoredPosting) -> bool:
    return _get_recommended_action(scored_posting) not in {
        ACTION_PASS,
        ACTION_PREVIOUSLY_REVIEWED,
    }


def _is_top_match_display_posting(scored_posting: ScoredPosting) -> bool:
    if not scored_posting.top_match_eligible:
        return False

    if not _is_actionable_posting(scored_posting):
        return False

    if _get_recommended_action(scored_posting) == ACTION_TRACK_STATUS:
        return False

    risks = _get_hiring_risk_flags(scored_posting)

    # Top Match should mean "act on this now." Production Kubernetes translation
    # risk with only medium hiring probability belongs in Review Needed, not the
    # urgent Top Match section.
    if (
        _get_hiring_probability_label(scored_posting) == "Medium"
        and RISK_PRODUCTION_KUBERNETES_TRANSLATION in risks
        and _get_recommended_action(scored_posting)
        in {
            ACTION_APPLY,
            ACTION_APPLY_WITH_RECRUITER,
            ACTION_TAILOR_RESUME,
        }
    ):
        return False

    return True


def _format_hiring_risk_flags(scored_posting: ScoredPosting) -> str:
    risks = _get_hiring_risk_flags(scored_posting)

    if not risks:
        return "None"

    return "; ".join(risks)


def _get_hiring_risk_flags(scored_posting: ScoredPosting) -> list[str]:
    title_text = _get_title_text(scored_posting)
    company_text = (scored_posting.posting.company_name or "").lower()
    location_text = (scored_posting.posting.location or "").lower()
    positive_labels = _get_positive_score_labels(scored_posting.score_reasons)
    risks: list[str] = []

    if scored_posting.location_status == "skipped":
        risks.append(RISK_HARD_LOCATION_MISMATCH)
    elif _has_any_location_keyword(
        location_text,
        [
            "apac",
            "emea",
            "europe",
            "eu",
            "netherlands",
            "amsterdam",
            "germany",
            "france",
            "uk",
            "united kingdom",
            "singapore",
            "australia",
        ],
    ):
        risks.append(RISK_HARD_LOCATION_MISMATCH)
    elif scored_posting.location_status in {"mixed", "conditional", "unknown"}:
        risks.append(RISK_LOCATION_NEEDS_CONFIRMATION)

    if _has_any_title_keyword(title_text, ROLE_FAMILY_MISMATCH_TITLE_KEYWORDS):
        risks.append(RISK_ROLE_FAMILY_MISMATCH)

    if any(
        keyword in company_text for keyword in HIGH_COMPETITION_COMPANY_KEYWORDS
    ):
        risks.append(RISK_HIGH_COMPETITION_EMPLOYER)

    if _has_any_title_keyword(title_text, ["support", "technical support", "analyst"]):
        risks.append(RISK_SUPPORT_ROLE)

    if _has_any_title_keyword(title_text, ["architect"]) and not _has_any_title_keyword(
        title_text,
        ["engineer", "administrator", "operations", "sre", "site reliability"],
    ):
        risks.append(RISK_ROLE_FAMILY_MISMATCH)

    if _has_any_title_keyword(title_text, ["manager"]):
        risks.append(RISK_ROLE_FAMILY_MISMATCH)

    if _has_any_title_keyword(title_text, ["lead"]):
        risks.append(RISK_LEADERSHIP_AMBIGUITY)

    if _has_any_title_keyword(
        title_text,
        ["security engineer", "infrastructure security"],
    ):
        risks.append(RISK_SECURITY_DOMAIN_TRANSLATION)

    if _has_any_title_keyword(
        title_text,
        ["software engineer", "frontend", "full stack", "platform engineer"],
    ):
        risks.append(RISK_SOFTWARE_HEAVY_TRANSLATION)

    if "kubernetes" in positive_labels or "k8s" in positive_labels:
        risks.append(RISK_PRODUCTION_KUBERNETES_TRANSLATION)

    if (
        scored_posting.location_status == "allowed"
        and "remote" in positive_labels
        and _get_technical_match_label(scored_posting) != "Very Strong"
    ):
        risks.append(RISK_GENERIC_REMOTE_COMPETITION)

    if _get_compensation_label(scored_posting) == "Below floor":
        risks.append(RISK_BELOW_COMPENSATION_FLOOR)

    for avoid_match in scored_posting.profile_avoid_matches or []:
        risks.append(f"profile avoid match: {avoid_match}")

    return _dedupe_preserving_order(risks)


def _get_title_text(scored_posting: ScoredPosting) -> str:
    return (scored_posting.posting.title or "").lower()


def _get_positive_score_labels(score_reasons: list[str]) -> list[str]:
    labels: list[str] = []

    for reason in score_reasons:
        if not reason.startswith("+"):
            continue

        if ":" not in reason:
            continue

        label = reason.split(":", maxsplit=1)[1].strip().lower()

        if label:
            labels.append(label)

    return _dedupe_preserving_order(labels)


def _has_any_title_keyword(title_text: str, keywords: list[str]) -> bool:
    return any(keyword in title_text for keyword in keywords)


def _has_any_location_keyword(location_text: str, keywords: list[str]) -> bool:
    return any(keyword in location_text for keyword in keywords)


def _count_matching_labels(labels: list[str], keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if keyword in labels)


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    deduped_values: list[str] = []

    for value in values:
        if value not in deduped_values:
            deduped_values.append(value)

    return deduped_values
