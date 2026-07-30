"""Write a privacy-safe explanation of how every collected job was handled."""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import os
from pathlib import Path
import tempfile

from job_radar.report_view_model import (
    is_potential_top_match_report_posting,
    is_review_needed_report_posting,
    is_top_match_report_posting,
)
from job_radar.scored_posting import ScoredPosting


EVALUATION_AUDIT_NAME = "job-evaluation-audit.txt"


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
                f"Final outcome: {outcome}",
                f"Reason codes: {', '.join(reasons) if reasons else 'none'}",
                f"Score: {scored.score}",
                f"Location status: {scored.location_status}",
                f"Workplace: {posting.remote_status or 'Unknown'}",
                f"Location: {posting.location or 'Unknown'}",
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
                    f"{len(resume_match.evidence)} supported; "
                    f"{len(resume_match.gaps)} gaps; "
                    f"{len(resume_match.critical_gaps or [])} critical gaps"
                    if resume_match
                    else "Requirement comparison: Not evaluated"
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


def _reason_codes_for(
    scored: ScoredPosting,
    outcome: str,
) -> tuple[str, ...]:
    codes: set[str] = set()
    if scored.eligibility is not None:
        codes.update(reason.code for reason in scored.eligibility.reasons)
        codes.add(f"eligibility:{scored.eligibility.status}")
    if scored.resume_match is not None:
        codes.add(f"resume_match:{scored.resume_match.label.lower()}")
        if scored.resume_match.gaps:
            codes.add("resume_gaps_present")
        if scored.resume_match.critical_gaps:
            codes.add("critical_resume_gap")
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
