"""Write a privacy-safe explanation of how every collected job was handled."""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import os
from pathlib import Path
import tempfile
import json
from urllib.parse import urlsplit, urlunsplit

from job_radar import __build__, __version__
from job_radar.report_view_model import (
    is_potential_top_match_report_posting,
    is_review_needed_report_posting,
    is_top_match_report_posting,
)
from job_radar.scored_posting import ScoredPosting


EVALUATION_AUDIT_NAME = "job-evaluation-audit.txt"
TARGETED_EVALUATION_AUDIT_NAME = "targeted-job-evaluation-audit.txt"


def evaluation_audit_download_name(
    modified_timestamp: float,
    *,
    targeted: bool = False,
) -> str:
    """Build a readable, timestamped filename for a downloaded audit."""

    timestamp = datetime.fromtimestamp(modified_timestamp).strftime(
        "%Y-%m-%d-%H%M"
    )
    prefix = (
        "junior-targeted-job-evaluation-audit"
        if targeted
        else "junior-job-evaluation-audit"
    )
    return f"{prefix}-{timestamp}.txt"


@dataclass(frozen=True)
class EvaluationAuditSummary:
    """Return safe totals for scan diagnostics and tests."""

    jobs_evaluated: int
    outcome_counts: dict[str, int]
    reason_counts: dict[str, int]


def write_evaluation_audit(
    path: str | Path,
    scored_postings: list[ScoredPosting] | tuple[ScoredPosting, ...],
    *,
    decided_job_ids: set[str] | None = None,
    generated_at: str | None = None,
    scan_kind: str = "full",
    scan_run_id: int | None = None,
) -> EvaluationAuditSummary:
    """Write one readable, bounded record per job without private document text."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    decided_ids = decided_job_ids or set()
    generated = generated_at or datetime.now(UTC).isoformat()

    records: list[tuple[ScoredPosting, str, tuple[str, ...]]] = []
    outcome_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    for scored in scored_postings:
        outcome = _outcome_for(scored, decided_ids)
        reasons = _reason_codes_for(scored, outcome)
        records.append((scored, outcome, reasons))
        outcome_counts[outcome] += 1
        reason_counts.update(reasons)

    lines = [
        "Junior job evaluation audit",
        f"Generated: {generated}",
        f"Scan kind: {scan_kind}",
        f"Scan run ID: {scan_run_id if scan_run_id is not None else 'Unknown'}",
        f"Jobs evaluated: {len(records)}",
        "",
        "Outcome summary",
    ]
    lines.extend(
        f"- {label}: {count}"
        for label, count in sorted(outcome_counts.items())
    )
    lines.extend(("", "Reason-code summary"))
    lines.extend(
        f"- {label}: {count}"
        for label, count in sorted(reason_counts.items())
    )

    for index, (scored, outcome, reasons) in enumerate(records, start=1):
        posting = scored.posting
        resume_match = scored.resume_match
        compensation = scored.compensation
        eligibility = scored.eligibility
        lines.extend(
            (
                "",
                f"[{index}] {posting.company_name} - {posting.title}",
                f"Junior job ID: {posting.job_radar_id}",
                f"Public posting: {posting.source_url or 'Not available'}",
                f"Source type: {posting.source_type}",
                f"Final outcome: {outcome}",
                f"Reason codes: {', '.join(reasons) if reasons else 'none'}",
                f"Score: {scored.score}",
                f"Location status: {scored.location_status}",
                f"Workplace: {posting.remote_status or 'Unknown'}",
                f"Location: {posting.location or 'Unknown'}",
                _normalization_audit_line(posting),
                _detail_retrieval_audit_line(posting),
                (
                    "Compensation: "
                    f"{compensation.label} ({compensation.range_label})"
                    if compensation
                    else "Compensation: Not evaluated"
                ),
                (
                    f"Practical eligibility: {eligibility.status}"
                    if eligibility
                    else "Practical eligibility: Not evaluated"
                ),
                (
                    f"Resume match: {resume_match.label}"
                    if resume_match
                    else "Resume match: Not evaluated"
                ),
                (
                    "Requirement comparison: "
                    f"{len(resume_match.requirements_reviewed or [])} reviewed; "
                    f"{len(resume_match.supported_requirements or [])} supported; "
                    f"{len(resume_match.gaps)} gaps; "
                    f"{len(resume_match.critical_gaps or [])} critical gaps"
                    if resume_match
                    else "Requirement comparison: Not evaluated"
                ),
                (
                    "LLM advisory: "
                    f"{scored.llm_review.provider}; "
                    f"model={scored.llm_review.model}; "
                    f"prompt={scored.llm_review.prompt_version}; "
                    f"fit={scored.llm_review.fit_assessment}"
                    if scored.llm_review
                    else "LLM advisory: Not used"
                ),
            )
        )

    content = "\n".join(lines).rstrip() + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            temporary_path = Path(stream.name)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    return EvaluationAuditSummary(
        jobs_evaluated=len(records),
        outcome_counts=dict(sorted(outcome_counts.items())),
        reason_counts=dict(sorted(reason_counts.items())),
    )


def write_evaluation_trace_log(
    logs_path: str | Path,
    scored_postings: list[ScoredPosting] | tuple[ScoredPosting, ...],
    *,
    scan_run_id: int,
    decided_job_ids: set[str] | None = None,
    generated_at: str | None = None,
) -> Path | None:
    """Write a structured per-job decision trace without private documents."""

    generated = generated_at or datetime.now(UTC).isoformat()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = (
        Path(logs_path)
        / f"junior-evaluation-run-{scan_run_id}-{stamp}.log"
    )
    decided_ids = decided_job_ids or set()
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8", newline="\n") as stream:
            for scored in scored_postings:
                outcome = _outcome_for(scored, decided_ids)
                match = scored.resume_match
                eligibility = scored.eligibility
                payload = {
                "timestamp": generated,
                "schema_version": 1,
                "application_version": __version__,
                "application_build": __build__,
                "subsystem": "evaluation",
                "severity": "info",
                "event": "job_evaluation_completed",
                "scan_run_id": scan_run_id,
                "job_id": scored.posting.job_radar_id,
                "company": scored.posting.company_name,
                "title": scored.posting.title,
                "source_type": scored.posting.source_type,
                "public_posting": _sanitized_public_url(
                    scored.posting.source_url
                ),
                "normalization_state": scored.posting.normalization_state,
                "normalization_issues": list(
                    scored.posting.normalization_issues
                ),
                "detail_retrieval_state": (
                    scored.posting.detail_retrieval_state
                ),
                "location_status": scored.location_status,
                "workplace": scored.posting.remote_status,
                "location": scored.posting.location,
                "score": scored.score,
                "eligibility_status": (
                    eligibility.status if eligibility else "not_evaluated"
                ),
                "eligibility_reason_codes": (
                    [reason.code for reason in eligibility.reasons]
                    if eligibility
                    else []
                ),
                "resume_match": match.label if match else "not_evaluated",
                "requirements_reviewed": len(
                    match.requirements_reviewed or []
                ) if match else 0,
                "requirements_supported": len(
                    match.supported_requirements or []
                ) if match else 0,
                "material_gaps": _bounded_diagnostic_labels(
                    match.gaps if match else []
                ),
                "critical_gaps": _bounded_diagnostic_labels(
                    (match.critical_gaps or []) if match else []
                ),
                "reason_codes": list(_reason_codes_for(scored, outcome)),
                "final_outcome": outcome,
                }
                stream.write(json.dumps(payload, sort_keys=True) + "\n")
    except OSError:
        # A troubleshooting aid must never turn a completed evaluation into a
        # failed scan when a log directory is temporarily unavailable.
        return None
    return destination


def _bounded_diagnostic_labels(values: list[str] | tuple[str, ...]) -> list[str]:
    """Keep concise derived explanations, never entire qualification sections."""

    return [" ".join(value.split())[:240] for value in values[:8] if value.strip()]


def _sanitized_public_url(value: str | None) -> str | None:
    """Keep a public job path while removing query strings and fragments."""

    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _outcome_for(scored: ScoredPosting, decided_job_ids: set[str]) -> str:
    if scored.posting.job_radar_id in decided_job_ids:
        return "previously decided"
    if scored.application is not None:
        return "tracked application"
    if is_top_match_report_posting(scored):
        return "top match"
    if is_potential_top_match_report_posting(scored):
        return "potential top match"
    if scored.location_outlier_eligible:
        return "location outlier"
    if is_review_needed_report_posting(scored):
        return "needs review"
    return "omitted"


def _detail_retrieval_audit_line(posting) -> str:
    if posting.detail_retrieval_state == "skipped_unrelated":
        return "Detail retrieval: Skipped after conservative listing review"
    if posting.detail_retrieval_state == "unavailable":
        return "Detail retrieval: Unavailable; evaluated conservatively"
    if posting.detail_retrieval_state == "cached_source_fallback":
        return "Detail retrieval: Complete cached detail used after source outage"
    if posting.detail_retrieval_state == "cached_source_fallback_incomplete":
        return "Detail retrieval: Cached fallback remained incomplete; visibly withheld"
    if posting.detail_retrieval_state == "cached_detail_reuse":
        return "Detail retrieval: Reused recently verified job detail"
    if "incomplete_description" in posting.normalization_issues:
        return "Detail retrieval: Incomplete after collection"
    return "Detail retrieval: Complete or not required"


def _normalization_audit_line(posting) -> str:
    state = posting.normalization_state or "not recorded"
    issues = ", ".join(posting.normalization_issues) or "none"
    return f"Normalization: {state}; issues: {issues}"


def _reason_codes_for(
    scored: ScoredPosting,
    outcome: str,
) -> tuple[str, ...]:
    codes: set[str] = set()
    if scored.posting.normalization_state == "incomplete":
        codes.add("normalization_incomplete")
    codes.update(
        f"normalization:{issue}"
        for issue in scored.posting.normalization_issues
    )
    if scored.posting.detail_retrieval_state == "skipped_unrelated":
        codes.add("detail_retrieval_skipped")
    elif scored.posting.detail_retrieval_state == "unavailable":
        codes.add("detail_retrieval_unavailable")
    elif scored.posting.detail_retrieval_state == "cached_source_fallback":
        codes.add("source_cache_fallback")
    elif scored.posting.detail_retrieval_state == "cached_detail_reuse":
        codes.add("detail_cache_reused")
    if scored.eligibility is not None:
        codes.update(reason.code for reason in scored.eligibility.reasons)
        codes.add(f"eligibility:{scored.eligibility.status}")
    if scored.resume_match is not None:
        codes.add(f"resume_match:{scored.resume_match.label.lower()}")
        if scored.resume_match.gaps:
            codes.add("resume_gaps_present")
        if scored.resume_match.critical_gaps:
            codes.add("critical_resume_gap")
    if scored.llm_review is not None:
        codes.add("llm_advisory_used")
        codes.add(f"llm_fit:{scored.llm_review.fit_assessment}")
    if scored.profile_avoid_matches:
        codes.add("profile_avoid_match")
    if scored.history_risk_level:
        codes.add(f"history_risk:{scored.history_risk_level.lower()}")
    if scored.location_status:
        codes.add(f"location:{scored.location_status.lower()}")
    if outcome == "previously decided":
        codes.add("prior_user_decision")
    elif outcome == "tracked application":
        codes.add("tracked_application")
    elif outcome == "omitted":
        codes.add("not_actionable")
    return tuple(sorted(codes))
