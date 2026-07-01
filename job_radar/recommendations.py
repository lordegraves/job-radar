from __future__ import annotations

from typing import TYPE_CHECKING

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


_RECOMMENDATION_SUMMARY_ORDER = [
    "Apply",
    "Apply + Recruiter Message",
    "Network First",
    "Tailor Resume",
    "Hold",
    "Pass",
]


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

    if "hard location mismatch" in risks:
        return "Very Low"

    if "role family mismatch" in risks or "support role" in risks:
        return "Low"

    if resume_match == "Weak":
        return "Low"

    if (
        "software-heavy translation risk" in risks
        or "generic remote competition" in risks
        or "production Kubernetes translation risk" in risks
        or "leadership ambiguity risk" in risks
        or "security-domain translation risk" in risks
        or "high competition employer" in risks
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
    hiring_probability = _get_hiring_probability_label(scored_posting)
    technical_match = _get_technical_match_label(scored_posting)
    resume_match = _get_resume_match_label(scored_posting)
    risks = _get_hiring_risk_flags(scored_posting)

    if "below compensation floor" in risks:
        return "Pass"

    if "hard location mismatch" in risks:
        return "Pass"

    if "role family mismatch" in risks or "support role" in risks:
        return "Pass"

    if any(risk.startswith("profile avoid match: ") for risk in risks):
        return "Pass"

    if (
        technical_match in {"Very Strong", "Strong"}
        and "high competition employer" in risks
        and (
            "software-heavy translation risk" in risks
            or "security-domain translation risk" in risks
            or "leadership ambiguity risk" in risks
        )
    ):
        return "Network First"

    if (
        technical_match in {"Very Strong", "Strong"}
        and "software-heavy translation risk" in risks
        and (
            "production Kubernetes translation risk" in risks
            or "security-domain translation risk" in risks
        )
    ):
        return "Network First"

    if (
        technical_match in {"Very Strong", "Strong"}
        and "leadership ambiguity risk" in risks
    ):
        return "Network First"

    if hiring_probability == "High" and technical_match == "Very Strong":
        if risks or resume_match != "Very Strong":
            return "Apply + Recruiter Message"
        return "Apply"

    if hiring_probability == "Medium" and technical_match == "Very Strong":
        return "Apply + Recruiter Message"

    if hiring_probability == "Medium" and technical_match == "Strong":
        return "Tailor Resume"

    if (
        technical_match in {"Very Strong", "Strong"}
        and "software-heavy translation risk" in risks
    ):
        return "Network First"

    if hiring_probability == "Low":
        return "Hold"

    return "Pass"


def _get_action_rationale(scored_posting: ScoredPosting) -> str:
    recommended_action = _get_recommended_action(scored_posting)
    hiring_probability = _get_hiring_probability_label(scored_posting)
    technical_match = _get_technical_match_label(scored_posting)
    resume_match = _get_resume_match_label(scored_posting)
    risks = _get_hiring_risk_flags(scored_posting)

    if recommended_action == "Apply":
        return _append_history_rationale(
            scored_posting,
            (
                "Clean apply: very strong technical match, very strong resume match, "
                "high hiring probability, and no hiring risks."
            ),
        )

    if recommended_action == "Apply + Recruiter Message":
        if risks:
            return _append_history_rationale(
                scored_posting,
                (
                    "Apply with recruiter positioning: this role is strong, but needs "
                    f"positioning around {', '.join(risks)}."
                ),
            )

        return _append_history_rationale(
            scored_posting,
            (
                "Apply with recruiter positioning: this role is promising, but the "
                f"resume match is {resume_match.lower()} and should be framed clearly."
            ),
        )

    if recommended_action == "Network First":
        if risks:
            return _append_history_rationale(
                scored_posting,
                (
                    "Network first: this role has useful technical signal, but direct "
                    f"apply is weaker because of {', '.join(risks)}."
                ),
            )

        return _append_history_rationale(
            scored_posting,
            (
                "Network first: this role has some alignment, but the match is not "
                "strong enough for a direct apply-first approach."
            ),
        )

    if recommended_action == "Tailor Resume":
        return _append_history_rationale(
            scored_posting,
            (
                "Tailor resume: the role is worth reviewing, but the current resume "
                f"match is {resume_match.lower()} and hiring probability is "
                f"{hiring_probability.lower()}."
            ),
        )

    if recommended_action == "Hold":
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
            "a prior blocker."
        )

    if scored_posting.history_risk_level == "caution":
        return (
            "Use caution because prior similar applications did not convert "
            "despite strong technical alignment."
        )

    return None


def _is_actionable_posting(scored_posting: ScoredPosting) -> bool:
    return _get_recommended_action(scored_posting) != "Pass"


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
        risks.append("hard location mismatch")
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
        risks.append("hard location mismatch")
    elif scored_posting.location_status in {"mixed", "conditional", "unknown"}:
        risks.append("location needs confirmation")

    if _has_any_title_keyword(title_text, ROLE_FAMILY_MISMATCH_TITLE_KEYWORDS):
        risks.append("role family mismatch")

    if any(
        keyword in company_text for keyword in HIGH_COMPETITION_COMPANY_KEYWORDS
    ):
        risks.append("high competition employer")

    if _has_any_title_keyword(title_text, ["support", "technical support", "analyst"]):
        risks.append("support role")

    if _has_any_title_keyword(title_text, ["architect"]) and not _has_any_title_keyword(
        title_text,
        ["engineer", "administrator", "operations", "sre", "site reliability"],
    ):
        risks.append("role family mismatch")

    if _has_any_title_keyword(title_text, ["manager"]):
        risks.append("role family mismatch")

    if _has_any_title_keyword(title_text, ["lead"]):
        risks.append("leadership ambiguity risk")

    if _has_any_title_keyword(
        title_text,
        ["security engineer", "infrastructure security"],
    ):
        risks.append("security-domain translation risk")

    if _has_any_title_keyword(
        title_text,
        ["software engineer", "frontend", "full stack", "platform engineer"],
    ):
        risks.append("software-heavy translation risk")

    if "kubernetes" in positive_labels or "k8s" in positive_labels:
        risks.append("production Kubernetes translation risk")

    if (
        scored_posting.location_status == "allowed"
        and "remote" in positive_labels
        and _get_technical_match_label(scored_posting) != "Very Strong"
    ):
        risks.append("generic remote competition")

    if _get_compensation_label(scored_posting) == "Below floor":
        risks.append("below compensation floor")

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
