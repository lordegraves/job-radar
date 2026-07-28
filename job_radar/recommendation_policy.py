"""Apply the eligibility rules that decide where scored jobs may be displayed."""

import re
from typing import Any

from job_radar.models import JobPosting
from job_radar.normalize import clean_text
from job_radar.resume_match import ResumeMatchResult


def evaluate_top_match_eligibility(
    posting: JobPosting,
    score: int,
    score_reasons: list[str],
    location_status: str,
    scoring_config: dict[str, Any],
    resume_match: ResumeMatchResult | None = None,
) -> tuple[bool, list[str]]:
    if resume_match is not None:
        if resume_match.has_critical_gap:
            return False, ["critical_required_qualification_gap"]
        # Preserve the supported CLI/YAML workflow when no résumé is configured.
        # RC6's résumé gate applies only when Junior actually has résumé evidence
        # to evaluate; an Unknown result must continue through the legacy rules.
        if resume_match.label not in {"Unknown", "Strong", "Very Strong"}:
            return False, [f"resume_match_not_strong:{resume_match.label}"]
        if len(resume_match.gaps) > 1:
            return False, ["more_than_one_resume_gap"]

    allowed_top_match_location_statuses = [
        "allowed",
        "allowed_with_travel",
    ]

    if location_status not in allowed_top_match_location_statuses:
        return False, [f"location_not_allowed:{location_status}"]

    min_score = scoring_config["top_matches"]["min_score"]

    if score < min_score:
        return False, [f"score_below_top_match_threshold:{score}<{min_score}"]

    if _has_negative_title_match(score_reasons):
        return False, ["negative_title_match"]

    excluded_keyword = _find_excluded_title_keyword(posting, scoring_config)
    if excluded_keyword:
        return False, [f"excluded_title_keyword:{excluded_keyword}"]

    strong_signal = _find_configured_signal(
        score_reasons,
        scoring_config["top_matches"]["strong_signals"],
    )
    if strong_signal is None:
        return False, ["missing_strong_signal"]

    review_signal = _find_major_review_signal(
        posting,
        scoring_config["top_matches"].get("review_signals", []),
    )
    if review_signal is not None:
        return False, [f"needs_review_signal:{review_signal}"]

    return True, [
        f"score {score} meets top-match threshold {min_score}",
        f"location fit is acceptable: {location_status}",
        f"strong signal matched: {strong_signal}",
    ]


def evaluate_potential_top_match_eligibility(
    posting: JobPosting,
    score: int,
    score_reasons: list[str],
    location_status: str,
    scoring_config: dict[str, Any],
    resume_match: ResumeMatchResult | None = None,
) -> bool:
    """Allow only unresolved location facts through the strict role-fit gate."""

    if location_status not in {"conditional", "mixed", "unknown"}:
        return False

    eligible_without_location, _reasons = evaluate_top_match_eligibility(
        posting=posting,
        score=score,
        score_reasons=score_reasons,
        location_status="allowed",
        scoring_config=scoring_config,
        resume_match=resume_match,
    )
    return eligible_without_location


def evaluate_review_needed_eligibility(
    score: int,
    score_reasons: list[str],
    location_status: str,
    top_match_eligible: bool,
    scoring_config: dict[str, Any],
    resume_match: ResumeMatchResult | None = None,
) -> bool:
    review_needed_config = scoring_config["review_needed"]

    if top_match_eligible:
        return False

    if resume_match is not None and resume_match.has_critical_gap:
        return False

    if score < review_needed_config["min_score"]:
        return False

    if location_status in review_needed_config["excluded_location_statuses"]:
        return False

    return _has_configured_signal(
        score_reasons,
        review_needed_config["strong_signals"],
    )


def _has_negative_title_match(score_reasons: list[str]) -> bool:
    for reason in score_reasons:
        if reason.startswith("-") and "title:" in reason:
            return True

    return False


def _find_excluded_title_keyword(
    posting: JobPosting,
    scoring_config: dict[str, Any],
) -> str | None:
    title = clean_text(posting.title).lower()
    excluded_title_keywords = scoring_config["top_matches"]["excluded_title_keywords"]

    for keyword in excluded_title_keywords:
        if keyword in title:
            return keyword

    return None


def _find_major_review_signal(
    posting: JobPosting,
    configured_signals: list[str],
) -> str | None:
    title_text = clean_text(posting.title).lower()
    body_text = _build_body_text(posting)

    responsibility_markers = (
        "own",
        "owns",
        "owning",
        "operate",
        "operates",
        "operating",
        "manage",
        "manages",
        "managing",
        "administer",
        "administers",
        "administering",
        "lead",
        "leading",
        "responsible for",
        "accountable for",
    )

    body_sections = re.split(r"[.!?;\n]+", body_text)

    for raw_signal in configured_signals:
        signal = clean_text(raw_signal).lower()
        if not signal:
            continue

        if _contains_phrase(title_text, signal):
            return signal

        for section in body_sections:
            if not _contains_phrase(section, signal):
                continue

            if any(
                _contains_phrase(section, marker)
                for marker in responsibility_markers
            ):
                return signal

    return None


def _contains_phrase(text: str, phrase: str) -> bool:
    pattern = rf"(?<!\w){re.escape(phrase)}(?!\w)"
    return re.search(pattern, text) is not None


def _has_strong_technical_signal(
    score_reasons: list[str],
    scoring_config: dict[str, Any],
) -> bool:
    return _has_configured_signal(
        score_reasons,
        scoring_config["top_matches"]["strong_signals"],
    )


def _has_configured_signal(
    score_reasons: list[str],
    configured_signals: list[str],
) -> bool:
    return _find_configured_signal(score_reasons, configured_signals) is not None


def _find_configured_signal(
    score_reasons: list[str],
    configured_signals: list[str],
) -> str | None:
    for reason in score_reasons:
        for signal in configured_signals:
            if signal in reason:
                return signal

    return None


def _build_body_text(posting: JobPosting) -> str:
    parts = [
        posting.remote_status,
        posting.salary_text,
        posting.description,
    ]

    return clean_text(" ".join(part for part in parts if part)).lower()
