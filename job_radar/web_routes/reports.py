"""Serve saved reports and structured sections from the latest scan snapshot."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from job_radar.job_decision_service import (
    DECISION_PASSED,
    DECISION_SAVED,
    PASS_REASONS,
    delete_job_decision,
    list_job_decisions,
    save_job_decision,
    save_job_decisions_bulk,
)
from job_radar.report_snapshot import (
    ReportSnapshotCollectorError,
    ReportSnapshotJob,
    load_report_snapshot,
)
from job_radar.retention_service import list_retained_report_runs
from job_radar.tracker.tracker_storage import list_applications

REPORT_FILE_EXTENSIONS = {".html", ".htm", ".md", ".txt"}
JOB_DECISION_SECTIONS = {
    "passed_not_recommended",
    "top_matches",
    "potential_top_matches",
    "review_needed",
    "new_jobs",
}
REPORT_JOBS_PER_PAGE = 20
COMPACT_REPORT_JOBS_PER_PAGE = 50

REPORT_HTML_BODY_PATTERN = re.compile(
    r"<body\b[^>]*>(.*?)</body>",
    flags=re.IGNORECASE | re.DOTALL,
)

REPORT_HTML_STYLE_PATTERN = re.compile(
    r"<style\b[^>]*>.*?</style>",
    flags=re.IGNORECASE | re.DOTALL,
)

PRIMARY_REPORT_FILE_DETAILS = {
    "target-scan.html": {
        "description": "Read-only HTML export of the latest scan.",
        "sort_order": 10,
    },
    "target-email-preview.txt": {
        "description": "Latest plain-text email preview.",
        "sort_order": 20,
    },
}

REPORT_SECTION_DETAILS = {
    "top_matches": {
        "title": "Top Matches",
        "page_title": "Top Matches",
        "description": "Cleanest roles from the latest scan. These should be the fastest apply/review decisions.",
        "empty_message": "No Top Matches were found in the latest scan.",
    },
    "potential_top_matches": {
        "title": "Potential Top Matches",
        "page_title": "Potential Top Matches",
        "description": (
            "Strong role fits that may be excellent opportunities once the "
            "listed practical details are confirmed."
        ),
        "empty_message": (
            "No Potential Top Matches were found in the latest scan."
        ),
    },
    "review_needed": {
        "title": "Review Needed",
        "page_title": "Review Needed",
        "description": "Relevant roles that need a closer look before deciding whether to apply, network, or pass.",
        "empty_message": "No Review Needed roles were found in the latest scan.",
    },
    "tracked_applications": {
        "title": "Tracked Applications",
        "page_title": "Tracked Applications",
        "description": "Roles from the latest scan that are already in the application tracker.",
        "empty_message": "No tracked applications were found in the latest scan.",
    },
    "new_jobs": {
        "title": "New Jobs",
        "page_title": "New Jobs",
        "description": "Actionable roles first discovered during the latest scan.",
        "empty_message": "No new actionable jobs were found in the latest scan.",
    },
    "collector_errors": {
        "title": "Collector Errors",
        "page_title": "Collector Errors",
        "description": "Company sources that could not be collected successfully during the latest scan.",
        "empty_message": "No collector errors were reported in the latest scan.",
    },
    "passed_not_recommended": {
        "title": "Passed / Not Recommended",
        "page_title": "Passed / Not Recommended",
        "description": "Jobs the scan did not recommend, including the subset most worth reviewing.",
        "empty_message": "No passed or not-recommended jobs were found in the latest scan.",
    },
}

@dataclass(frozen=True)
class LatestReportSummaryView:
    generated_at: str | None
    html_report_name: str
    html_report_exists: bool
    top_matches: int
    potential_top_matches: int
    review_needed: int
    tracked_applications: int
    new_jobs: int
    collector_errors: int


@dataclass(frozen=True)
class ReportJobCardView:
    title: str
    url: str | None
    company: str | None
    location: str | None
    workplace_arrangement: str
    compensation: str | None
    hiring_probability: str | None
    recommended_action: str | None
    action_rationale: str | None
    why_matched: str | None
    technical_match: str | None
    resume_match: str | None
    resume_evidence: str | None
    resume_gaps: str | None
    hiring_risks: str | None
    history_context: str | None
    history_risk: str | None
    job_radar_id: str | None
    eligibility_status: str | None
    eligibility_label: str
    eligibility_reasons: tuple[str, ...]
    tracker_add_url: str
    tracker_edit_url: str | None
    is_tracked: bool
    review_state: str


@dataclass(frozen=True)
class ReportCollectorErrorView:
    company_key: str
    company_name: str
    source_type: str
    message: str


@dataclass(frozen=True)
class ReportFileView:
    name: str
    size_bytes: int
    modified_at: str
    modified_timestamp: float
    description: str
    is_primary: bool
    sort_order: int


def register_report_routes(
    app: Flask,
    *,
    get_reports_path: Callable[[], str],
    get_database_path: Callable[[], str],
    get_profile_id: Callable[[], str | None],
) -> None:
    """Register report listing, viewing, and download routes."""

    @app.get("/reports/section/<section_name>")
    def report_section_view(section_name: str) -> str:
        section_details = REPORT_SECTION_DETAILS.get(section_name)

        if section_details is None:
            abort(404)

        reports_path = Path(get_reports_path()).resolve()
        snapshot_path = reports_path / "target-scan.json"
        html_report_name = "target-scan.html"
        html_report_path = reports_path / html_report_name

        if not snapshot_path.is_file():
            abort(404)

        snapshot = load_report_snapshot(snapshot_path)
        job_cards: list[ReportJobCardView] = []
        collector_errors: list[ReportCollectorErrorView] = []
        eligibility_counts: dict[str, int] = {}
        current_page = 1
        total_pages = 1
        total_jobs = 0
        page_start_index = 0
        page_end_index = 0
        view_mode = (
            "compact"
            if section_name == "review_needed"
            and request.args.get("view") == "compact"
            else "full"
        )
        jobs_per_page = (
            COMPACT_REPORT_JOBS_PER_PAGE
            if view_mode == "compact"
            else REPORT_JOBS_PER_PAGE
        )
        requested_page = max(
            request.args.get("page", 1, type=int) or 1,
            1,
        )

        if section_name == "collector_errors":
            collector_errors = [
                _build_report_collector_error_view(error)
                for error in snapshot.collector_errors
            ]
        else:
            snapshot_jobs = getattr(snapshot, section_name)
            database_path = get_database_path()
            profile_id = get_profile_id()
            decisions = list_job_decisions(
                database_path,
                profile_id=profile_id,
            )
            decisions_by_job_id = {
                decision.job_radar_id: decision.decision
                for decision in decisions
            }
            decided_job_ids = set(decisions_by_job_id)
            tracked_job_ids = {
                application.job_radar_id
                for application in list_applications(
                    database_path,
                    profile_id=profile_id,
                )
            }
            all_job_cards = [
                _build_report_job_card(
                    job,
                    is_tracked=job.job_radar_id in tracked_job_ids,
                    decision=decisions_by_job_id.get(job.job_radar_id),
                    return_section=section_name,
                    return_page=requested_page,
                    return_view=view_mode,
                )
                for job in snapshot_jobs
                if (
                    section_name == "potential_top_matches"
                    or (
                        job.job_radar_id not in decided_job_ids
                        and job.job_radar_id not in tracked_job_ids
                    )
                )
            ]
            if section_name == "potential_top_matches":
                # Preserve the scan's full Potential Top Matches list while
                # keeping jobs that still need a decision at the front.
                all_job_cards.sort(
                    key=lambda card: {
                        "needs_review": 0,
                        "saved": 1,
                        "applied": 2,
                        "passed": 3,
                    }.get(card.review_state, 4)
                )
            eligibility_counts = _count_eligibility_labels(all_job_cards)
            total_jobs = len(all_job_cards)
            total_pages = max(
                1,
                (total_jobs + jobs_per_page - 1)
                // jobs_per_page,
            )
            current_page = min(
                requested_page,
                total_pages,
            )
            page_start_index = (current_page - 1) * jobs_per_page
            page_end_index = min(
                page_start_index + jobs_per_page,
                total_jobs,
            )
            job_cards = all_job_cards[page_start_index:page_end_index]

        return render_template(
            "report_section.html",
            section_name=section_name,
            section_title=section_details["page_title"],
            section_description=section_details["description"],
            empty_message=section_details["empty_message"],
            job_cards=job_cards,
            collector_errors=collector_errors,
            eligibility_counts=eligibility_counts,
            html_report_name=html_report_name,
            html_report_exists=html_report_path.is_file(),
            pass_reasons=PASS_REASONS,
            decisions_enabled=section_name in JOB_DECISION_SECTIONS,
            current_page=current_page,
            total_pages=total_pages,
            total_jobs=total_jobs,
            page_start=page_start_index + 1 if total_jobs else 0,
            page_end=page_end_index,
            view_mode=view_mode,
            view_query="compact" if view_mode == "compact" else None,
            today_iso=date.today().isoformat(),
        )

    @app.get("/reports")
    def reports() -> str:
        reports_path = get_reports_path()
        primary_report_files = _get_report_file_views(reports_path)

        return render_template(
            "reports.html",
            reports_path=reports_path,
            latest_report=build_latest_report_summary(reports_path),
            potential_top_progress=_build_potential_top_progress(
                reports_path,
                get_database_path(),
                profile_id=get_profile_id(),
            ),
            primary_report_files=primary_report_files,
            retained_report_runs=list_retained_report_runs(reports_path),
        )

    @app.post("/reports/jobs/<path:job_radar_id>/decision")
    def save_report_job_decision(job_radar_id: str):
        profile_id = get_profile_id()
        if profile_id is None:
            abort(400)
        section_name = request.form.get("section_name", "review_needed")
        return_page = max(request.form.get("page", 1, type=int) or 1, 1)
        view_mode = _validated_view_mode(
            section_name,
            request.form.get("view"),
        )
        if section_name not in JOB_DECISION_SECTIONS:
            abort(400)
        decision = request.form.get("decision", "")
        if decision not in {DECISION_SAVED, DECISION_PASSED}:
            abort(400)
        snapshot = _load_latest_snapshot(get_reports_path())
        job = _find_snapshot_job(
            snapshot,
            job_radar_id,
            section_name=section_name,
        )
        if job is None:
            abort(404)
        save_job_decision(
            get_database_path(),
            profile_id=profile_id,
            job_radar_id=job.job_radar_id,
            decision=decision,
            company=job.company,
            title=job.title,
            source_url=job.url,
            location=job.location,
            notes=request.form.get("notes"),
            decision_reason=(
                request.form.get("decision_reason")
                if decision == DECISION_PASSED
                else None
            ),
        )
        flash(
            (
                f"{job.title} was saved for later."
                if decision == DECISION_SAVED
                else f"{job.title} was marked reviewed and passed."
            ),
            "success",
        )
        return redirect(
            url_for(
                "report_section_view",
                section_name=section_name,
                page=return_page,
                view="compact" if view_mode == "compact" else None,
            )
        )

    @app.post("/reports/section/<section_name>/bulk-decision")
    def save_bulk_report_job_decisions(section_name: str):
        profile_id = get_profile_id()
        if profile_id is None:
            abort(400)
        if section_name not in JOB_DECISION_SECTIONS:
            abort(400)
        return_page = max(request.form.get("page", 1, type=int) or 1, 1)
        view_mode = _validated_view_mode(
            section_name,
            request.form.get("view"),
        )
        decision = request.form.get("decision", "")
        if decision not in {DECISION_SAVED, DECISION_PASSED}:
            abort(400)
        selected_ids = tuple(
            dict.fromkeys(
                value.strip()
                for value in request.form.getlist("job_radar_id")
                if value.strip()
            )
        )
        if not selected_ids:
            flash("Select at least one job first.", "error")
            return redirect(
                url_for(
                    "report_section_view",
                    section_name=section_name,
                    page=return_page,
                    view="compact" if view_mode == "compact" else None,
                )
            )

        snapshot = _load_latest_snapshot(get_reports_path())
        jobs = [
            _find_snapshot_job(snapshot, job_id, section_name=section_name)
            for job_id in selected_ids
        ]
        if any(job is None for job in jobs):
            abort(409)
        verified_jobs = [job for job in jobs if job is not None]
        save_job_decisions_bulk(
            get_database_path(),
            profile_id=profile_id,
            decision=decision,
            decision_reason=request.form.get("decision_reason"),
            jobs=[
                {
                    "job_radar_id": job.job_radar_id,
                    "company": job.company,
                    "title": job.title,
                    "source_url": job.url,
                    "location": job.location,
                }
                for job in verified_jobs
            ],
        )
        action = "saved for later" if decision == DECISION_SAVED else "passed"
        flash(f"{len(verified_jobs)} selected jobs were {action}.", "success")
        return redirect(
            url_for(
                "report_section_view",
                section_name=section_name,
                page=return_page,
                view="compact" if view_mode == "compact" else None,
            )
        )

    @app.get("/job-decisions")
    def job_decisions() -> str:
        profile_id = get_profile_id()
        if profile_id is None:
            abort(400)
        return render_template(
            "job_decisions.html",
            saved_jobs=list_job_decisions(
                get_database_path(),
                profile_id=profile_id,
                decision=DECISION_SAVED,
            ),
            passed_jobs=list_job_decisions(
                get_database_path(),
                profile_id=profile_id,
                decision=DECISION_PASSED,
            ),
            pass_reasons=PASS_REASONS,
        )

    @app.post("/job-decisions/<path:job_radar_id>")
    def update_job_decision(job_radar_id: str):
        profile_id = get_profile_id()
        if profile_id is None:
            abort(400)
        action = request.form.get("action", "")
        decisions = list_job_decisions(
            get_database_path(),
            profile_id=profile_id,
        )
        existing = next(
            (item for item in decisions if item.job_radar_id == job_radar_id),
            None,
        )
        if existing is None:
            abort(404)
        if action == "pass":
            save_job_decision(
                get_database_path(),
                profile_id=profile_id,
                job_radar_id=existing.job_radar_id,
                decision=DECISION_PASSED,
                company=existing.company,
                title=existing.title,
                source_url=existing.source_url,
                location=existing.location,
                notes=existing.notes,
                decision_reason=request.form.get("decision_reason"),
            )
            flash(f"{existing.title} was moved to Reviewed Jobs.", "success")
        elif action == "save_details":
            save_job_decision(
                get_database_path(),
                profile_id=profile_id,
                job_radar_id=existing.job_radar_id,
                decision=existing.decision,
                company=existing.company,
                title=existing.title,
                source_url=existing.source_url,
                location=existing.location,
                notes=request.form.get("notes"),
                decision_reason=request.form.get("decision_reason"),
            )
            flash(f"Details for {existing.title} were saved.", "success")
        elif action == "remove":
            delete_job_decision(
                get_database_path(),
                profile_id=profile_id,
                job_radar_id=existing.job_radar_id,
            )
            flash(
                f"{existing.title} can appear in a future scan again.",
                "success",
            )
        else:
            abort(400)
        return redirect(url_for("job_decisions"))

    @app.get("/reports/view/<path:report_name>")
    def report_view(report_name: str) -> str:
        reports_path = Path(get_reports_path()).resolve()
        report_path = _validate_report_path(reports_path, report_name)
        report_kind = (
            "html"
            if report_path.suffix.lower() in {".html", ".htm"}
            else "text"
        )
        report_content = _read_report_view_content(
            report_path,
            report_kind,
        )

        return render_template(
            "report_view.html",
            report_name=report_name,
            report_content=report_content,
            report_kind=report_kind,
            is_email_preview="email" in report_name.lower(),
        )

    @app.get("/reports/<path:report_name>")
    def report_file(report_name: str):
        reports_path = Path(get_reports_path()).resolve()
        _validate_report_path(reports_path, report_name)

        return send_from_directory(reports_path, report_name)


def build_latest_report_summary(
    reports_path: str | Path,
) -> LatestReportSummaryView:
    reports_path = Path(reports_path)
    snapshot_path = reports_path / "target-scan.json"
    html_report_name = "target-scan.html"
    html_report_path = reports_path / html_report_name

    if not snapshot_path.is_file():
        return LatestReportSummaryView(
            generated_at=None,
            html_report_name=html_report_name,
            html_report_exists=html_report_path.is_file(),
            top_matches=0,
            potential_top_matches=0,
            review_needed=0,
            tracked_applications=0,
            new_jobs=0,
            collector_errors=0,
        )

    snapshot = load_report_snapshot(snapshot_path)

    return LatestReportSummaryView(
        generated_at=_format_snapshot_generated_at(
            snapshot.summary.generated_at
        ),
        html_report_name=html_report_name,
        html_report_exists=html_report_path.is_file(),
        top_matches=snapshot.summary.top_matches,
        potential_top_matches=snapshot.summary.potential_top_matches,
        review_needed=snapshot.summary.review_needed,
        tracked_applications=snapshot.summary.tracked_applications,
        new_jobs=snapshot.summary.new_jobs,
        collector_errors=snapshot.summary.collector_errors,
    )


def _load_latest_snapshot(reports_path: str | Path):
    snapshot_path = Path(reports_path).resolve() / "target-scan.json"
    if not snapshot_path.is_file():
        abort(404)
    return load_report_snapshot(snapshot_path)


def _find_snapshot_job(
    snapshot,
    job_radar_id: str,
    *,
    section_name: str,
) -> ReportSnapshotJob | None:
    section = getattr(snapshot, section_name)
    return next(
        (
            job
            for job in section
            if job.job_radar_id == job_radar_id
        ),
        None,
    )


def _read_report_view_content(
    report_path: Path,
    report_kind: str,
) -> str:
    report_content = report_path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    if report_kind != "html":
        return report_content

    # Generated report HTML may include its own light-theme CSS and full document
    # shell. The GUI viewer owns page styling, so only embed the report body.
    report_content = REPORT_HTML_STYLE_PATTERN.sub("", report_content)
    body_match = REPORT_HTML_BODY_PATTERN.search(report_content)

    if body_match is None:
        return report_content

    return body_match.group(1).strip()


def _validate_report_path(
    reports_path: Path,
    report_name: str,
) -> Path:
    report_path = (reports_path / report_name).resolve()

    if reports_path not in report_path.parents:
        abort(404)

    if not report_path.is_file():
        abort(404)

    if report_path.suffix.lower() not in REPORT_FILE_EXTENSIONS:
        abort(404)

    return report_path


def _get_report_file_views(
    reports_path: str,
) -> list[ReportFileView]:
    reports_dir = Path(reports_path)

    if not reports_dir.exists():
        return []

    report_files: list[ReportFileView] = []

    for report_name, report_details in PRIMARY_REPORT_FILE_DETAILS.items():
        path = reports_dir / report_name

        if not path.is_file():
            continue

        stat = path.stat()

        report_files.append(
            ReportFileView(
                name=path.name,
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(
                    stat.st_mtime
                ).strftime("%Y-%m-%d %I:%M %p"),
                modified_timestamp=stat.st_mtime,
                description=report_details["description"],
                is_primary=True,
                sort_order=report_details["sort_order"],
            )
        )

    return sorted(
        report_files,
        key=lambda report: report.sort_order,
    )


def _format_snapshot_generated_at(
    generated_at: str | None,
) -> str | None:
    if generated_at is None:
        return None

    try:
        parsed_timestamp = datetime.fromisoformat(generated_at)
    except ValueError:
        return generated_at

    timezone_name = "UTC"

    if parsed_timestamp.tzinfo is None:
        timezone_name = "local"

    return f"{parsed_timestamp:%Y-%m-%d %H:%M} {timezone_name}"


def _build_report_collector_error_view(
    error: ReportSnapshotCollectorError,
) -> ReportCollectorErrorView:
    return ReportCollectorErrorView(
        company_key=error.company_key,
        company_name=error.company_name,
        source_type=error.source_type,
        message=error.message,
    )


def _format_eligibility_label(eligibility_status: str | None) -> str:
    if eligibility_status is None:
        return "Not Evaluated"

    return {
        "eligible": "Eligible",
        "needs_review": "Needs Review",
        "not_eligible": "Not Eligible",
    }.get(eligibility_status, eligibility_status)


def _count_eligibility_labels(
    job_cards: list[ReportJobCardView],
) -> dict[str, int]:
    counts = {
        "Eligible": 0,
        "Needs Review": 0,
        "Not Eligible": 0,
        "Not Evaluated": 0,
    }

    for job_card in job_cards:
        label = job_card.eligibility_label
        counts[label] = counts.get(label, 0) + 1

    return {
        label: count
        for label, count in counts.items()
        if count > 0
    }


def _validated_view_mode(section_name: str, value: str | None) -> str:
    if section_name == "review_needed" and value == "compact":
        return "compact"
    return "full"


def _build_report_job_card(
    job: ReportSnapshotJob,
    *,
    is_tracked: bool = False,
    decision: str | None = None,
    return_section: str | None = None,
    return_page: int = 1,
    return_view: str = "full",
) -> ReportJobCardView:
    return ReportJobCardView(
        title=job.title,
        url=job.url,
        company=job.company,
        location=job.location,
        workplace_arrangement=job.workplace_arrangement,
        compensation=job.compensation,
        hiring_probability=job.hiring_probability,
        # Existing snapshots may retain the retired RC5 label. Translate it
        # at the GUI boundary so users do not need to rerun a scan.
        recommended_action=(
            "Needs your review"
            if job.recommended_action == "Hold"
            else job.recommended_action
        ),
        action_rationale=job.action_rationale,
        why_matched=job.why_matched,
        technical_match=job.technical_match,
        resume_match=job.resume_match,
        resume_evidence=job.resume_evidence,
        resume_gaps=job.resume_gaps,
        hiring_risks=job.hiring_risks,
        history_context=job.history_context,
        history_risk=job.history_risk,
        job_radar_id=job.job_radar_id,
        eligibility_status=job.eligibility_status,
        eligibility_label=_format_eligibility_label(job.eligibility_status),
        eligibility_reasons=tuple(job.eligibility_reasons or []),
        tracker_add_url=url_for(
            "add_tracker_application",
            job_radar_id=job.job_radar_id,
            company_name=job.company,
            role_title=job.title,
            source_url=job.url or "",
            status="Applied",
            outcome="Pending / In Progress",
            applied_on=date.today().isoformat(),
            return_section=return_section,
            return_page=return_page,
            return_view=return_view,
        ),
        tracker_edit_url=(
            url_for(
                "edit_tracker_application",
                job_radar_id=job.job_radar_id,
                filter="all",
            )
            if is_tracked and job.job_radar_id
            else None
        ),
        is_tracked=is_tracked,
        review_state=(
            "applied"
            if is_tracked
            else decision or "needs_review"
        ),
    )


def _build_potential_top_progress(
    reports_path: str | Path,
    database_path: str | Path,
    *,
    profile_id: str | None,
) -> dict[str, int]:
    snapshot_path = Path(reports_path) / "target-scan.json"
    progress = {
        "needs_review": 0,
        "saved": 0,
        "applied": 0,
        "passed": 0,
    }
    if not snapshot_path.is_file():
        return progress

    snapshot = load_report_snapshot(snapshot_path)
    decisions_by_job_id = (
        {
            decision.job_radar_id: decision.decision
            for decision in list_job_decisions(
                database_path,
                profile_id=profile_id,
            )
        }
        if profile_id is not None
        else {}
    )
    tracked_job_ids = {
        application.job_radar_id
        for application in list_applications(
            database_path,
            profile_id=profile_id,
        )
    }

    for job in snapshot.potential_top_matches:
        if job.job_radar_id in tracked_job_ids:
            progress["applied"] += 1
        elif decisions_by_job_id.get(job.job_radar_id) == DECISION_SAVED:
            progress["saved"] += 1
        elif decisions_by_job_id.get(job.job_radar_id) == DECISION_PASSED:
            progress["passed"] += 1
        else:
            progress["needs_review"] += 1

    return progress
