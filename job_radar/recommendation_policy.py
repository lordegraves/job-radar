"""Apply the eligibility rules that decide where scored jobs may be displayed."""

from typing import Any

from job_radar.models import JobPosting
from job_radar.normalize import clean_text


def evaluate_top_match_eligibility(
    posting: JobPosting,
    score: int,
    score_reasons: list[str],
    location_status: str,
    scoring_config: dict[str, Any],
) -> tuple[bool, list[str]]:
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

    if _has_production_kubernetes_primary_risk(posting):
        return False, ["production_kubernetes_primary_risk"]

    return True, [
        f"score {score} meets top-match threshold {min_score}",
        f"location fit is acceptable: {location_status}",
        f"strong signal matched: {strong_signal}",
    ]


def evaluate_review_needed_eligibility(
    score: int,
    score_reasons: list[str],
    location_status: str,
    top_match_eligible: bool,
    scoring_config: dict[str, Any],
) -> bool:
    review_needed_config = scoring_config["review_needed"]

    if top_match_eligible:
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


def _has_production_kubernetes_primary_risk(posting: JobPosting) -> bool:
    title_text = clean_text(posting.title).lower()
    body_text = _build_body_text(posting)
    combined_text = f"{title_text} {body_text}"

    # Kubernetes is useful adjacent experience, but roles centered on owning
    # production Kubernetes platforms have been a weak direct-apply fit.
    # Do not treat a casual Kubernetes mention as enough to demote Top Match.
    kubernetes_primary_markers = [
        "production kubernetes",
        "production k8s",
        "kubernetes platform",
        "k8s platform",
        "kubernetes clusters",
        "k8s clusters",
        "kubernetes control plane",
        "own kubernetes",
        "operate kubernetes",
        "manage kubernetes",
        "administer kubernetes",
    ]

    title_primary_markers = [
        "kubernetes",
        "k8s",
    ]

    has_title_primary_marker = any(
        marker in title_text for marker in title_primary_markers
    )
    has_body_primary_marker = any(
        marker in combined_text for marker in kubernetes_primary_markers
    )

    if not has_title_primary_marker and not has_body_primary_marker:
        return False

    return not _has_strong_infrastructure_counterevidence(combined_text)


def _has_strong_infrastructure_counterevidence(text: str) -> bool:
    counterevidence_markers = [
        "hpc",
        "slurm",
        "gpu",
        "datacenter",
        "data center",
        "bare metal",
        "hardware",
        "cluster systems",
        "linux systems",
        "research computing",
        "scientific computing",
        "storage",
    ]

    matched_markers = [
        marker for marker in counterevidence_markers if marker in text
    ]

    return len(matched_markers) >= 2


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
