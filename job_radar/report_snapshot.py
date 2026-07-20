"""Save and reload a stable report snapshot that the GUI can display later."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from job_radar.html_report import (
    PASSED_JOBS_REPORT_LIMIT,
    _get_omitted_postings,
    _get_ordered_omitted_postings,
)
from job_radar.report_models import ScanReport
from job_radar.report_view_model import build_report_view_model
from job_radar.report_view_model import build_job_output_view_model
from job_radar.scored_posting import ScoredPosting


REPORT_SNAPSHOT_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class ReportSnapshotJob:
    title: str
    url: str | None
    company: str
    location: str | None
    compensation: str | None
    hiring_probability: str
    recommended_action: str
    action_rationale: str
    why_matched: str
    technical_match: str
    resume_match: str
    resume_evidence: str
    resume_gaps: str
    hiring_risks: str
    history_context: str
    history_risk: str | None
    job_radar_id: str
    eligibility_status: str | None = None
    eligibility_reasons: list[str] | None = None


@dataclass(frozen=True)
class ReportSnapshotCollectorError:
    company_key: str
    company_name: str
    source_type: str
    message: str


@dataclass(frozen=True)
class ReportSnapshotSummary:
    generated_at: str | None
    top_matches: int
    review_needed: int
    tracked_applications: int
    new_jobs: int
    collector_errors: int


@dataclass(frozen=True)
class ReportSnapshot:
    schema_version: int
    summary: ReportSnapshotSummary
    top_matches: list[ReportSnapshotJob]
    review_needed: list[ReportSnapshotJob]
    tracked_applications: list[ReportSnapshotJob]
    new_jobs: list[ReportSnapshotJob]
    passed_not_recommended: list[ReportSnapshotJob]
    collector_errors: list[ReportSnapshotCollectorError]


def build_report_snapshot(report: ScanReport) -> ReportSnapshot:
    view_model = build_report_view_model(
        scored_postings=report.scored_postings,
        omitted_scored_postings=report.omitted_scored_postings,
    )
    new_jobs = list(report.new_scored_postings or [])
    omitted_postings = _get_omitted_postings(view_model.report_scored_postings)
    passed_not_recommended = _get_ordered_omitted_postings(
        omitted_postings
    )[:PASSED_JOBS_REPORT_LIMIT]

    collector_errors = [
        ReportSnapshotCollectorError(
            company_key=error.company_key,
            company_name=error.company_name,
            source_type=error.source_type,
            message=error.message,
        )
        for error in report.collector_errors
    ]

    return ReportSnapshot(
        schema_version=REPORT_SNAPSHOT_SCHEMA_VERSION,
        summary=ReportSnapshotSummary(
            generated_at=report.generated_at,
            top_matches=len(view_model.top_matches),
            review_needed=len(view_model.review_needed),
            tracked_applications=len(view_model.tracked_applications),
            new_jobs=report.jobs_new,
            collector_errors=len(collector_errors),
        ),
        top_matches=_build_snapshot_jobs(view_model.top_matches),
        review_needed=_build_snapshot_jobs(view_model.review_needed),
        tracked_applications=_build_snapshot_jobs(
            view_model.tracked_applications
        ),
        new_jobs=_build_snapshot_jobs(new_jobs),
        passed_not_recommended=_build_snapshot_jobs(
            passed_not_recommended
        ),
        collector_errors=collector_errors,
    )


def write_report_snapshot(
    snapshot_path: str | Path,
    report: ScanReport,
) -> Path:
    path = Path(snapshot_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = build_report_snapshot(report)
    path.write_text(
        json.dumps(asdict(snapshot), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return path


def load_report_snapshot(snapshot_path: str | Path) -> ReportSnapshot:
    path = Path(snapshot_path)
    raw_snapshot = json.loads(path.read_text(encoding="utf-8"))

    return ReportSnapshot(
        schema_version=int(raw_snapshot["schema_version"]),
        summary=ReportSnapshotSummary(**raw_snapshot["summary"]),
        top_matches=_load_snapshot_jobs(raw_snapshot["top_matches"]),
        review_needed=_load_snapshot_jobs(raw_snapshot["review_needed"]),
        tracked_applications=_load_snapshot_jobs(
            raw_snapshot["tracked_applications"]
        ),
        new_jobs=_load_snapshot_jobs(raw_snapshot["new_jobs"]),
        passed_not_recommended=_load_snapshot_jobs(
            raw_snapshot["passed_not_recommended"]
        ),
        collector_errors=[
            ReportSnapshotCollectorError(**collector_error)
            for collector_error in raw_snapshot["collector_errors"]
        ],
    )


def _build_snapshot_jobs(
    scored_postings: list[ScoredPosting],
) -> list[ReportSnapshotJob]:
    return [
        _build_snapshot_job(scored_posting)
        for scored_posting in scored_postings
    ]


def _build_snapshot_job(
    scored_posting: ScoredPosting,
) -> ReportSnapshotJob:
    posting = scored_posting.posting
    job = build_job_output_view_model(scored_posting)

    return ReportSnapshotJob(
        title=posting.title,
        url=posting.source_url,
        company=posting.company_name,
        location=posting.location,
        compensation=_clean_optional_value(
            job.compensation_range
        ),
        hiring_probability=job.hiring_probability,
        recommended_action=job.recommended_action,
        action_rationale=job.action_rationale,
        why_matched=job.why_matched,
        technical_match=job.technical_match,
        resume_match=job.resume_match,
        resume_evidence=job.resume_evidence,
        resume_gaps=job.resume_gaps,
        hiring_risks=job.hiring_risks,
        history_context=job.history_context,
        history_risk=None if job.history_risk == "None" else job.history_risk,
        job_radar_id=posting.job_radar_id,
        eligibility_status=job.eligibility_status,
        eligibility_reasons=(
            list(job.eligibility_reasons)
            if job.eligibility_status is not None
            else None
        ),
    )


def _clean_optional_value(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned_value = value.strip()

    if cleaned_value.lower() in {"", "unknown", "none", "n/a"}:
        return None

    return cleaned_value


def _load_snapshot_jobs(
    raw_jobs: list[dict],
) -> list[ReportSnapshotJob]:
    jobs: list[ReportSnapshotJob] = []

    for raw_job in raw_jobs:
        compatible_job = dict(raw_job)
        compatible_job.setdefault("eligibility_status", None)
        compatible_job.setdefault("eligibility_reasons", None)
        jobs.append(ReportSnapshotJob(**compatible_job))

    return jobs
