import argparse
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, send_from_directory, url_for

from job_radar.scan_lock import ScanAlreadyRunningError
from job_radar.scan_service import handle_scan
from job_radar.company_config_service import (
    build_company_config_views,
    build_company_source_summaries,
    filter_company_config_views,
    get_company_config_view,
)
from job_radar.config import ConfigError, load_settings
from job_radar.email_sender import get_email_readiness
from job_radar.profile_service import build_candidate_profile_view, save_uploaded_resume
from job_radar.report_snapshot import (
    ReportSnapshotCollectorError,
    ReportSnapshotJob,
    load_report_snapshot,
)
from job_radar.runtime_paths import (
    DEFAULT_COMPANY_CONFIG_PATH,
    DEFAULT_EMAIL_PREVIEW_PATH,
    DEFAULT_REPORT_PATH,
    DEFAULT_SCORING_CONFIG_PATH,
    RuntimePaths,
)
from job_radar.storage import (
    fetch_included_job_history_records,
    initialize_database,
)
from job_radar.tracker.tracker_ids import build_manual_job_radar_id
from job_radar.tracker.tracker_models import ApplicationRecord
from job_radar.tracker.tracker_service import (
    delete_history_record,
    delete_tracker_application,
    get_application_workflow_state,
    get_history_record,
    update_history_record_workflow,
    update_tracker_application_workflow,
)
from job_radar.tracker.tracker_storage import (
    get_application,
    list_applications,
    upsert_application,
)


TRACKER_NEEDS_ACTION_WORKFLOW_STATES = {
    "follow_up_due",
    "needs_date_review",
    "active_pipeline",
}

TRACKER_NEEDS_REVIEW_WORKFLOW_STATES = {
    "needs_date_review",
    "dormant",
    "stale",
    "presumed_closed",
}

TRACKER_ACTIVE_WORKFLOW_STATES = {
    "follow_up_due",
    "needs_date_review",
    "active_pipeline",
    "follow_up_scheduled",
    "waiting",
    "dormant",
    "stale",
    "presumed_closed",
}

TRACKER_FILTERS = {
    "all": None,
    "needs_action": TRACKER_NEEDS_ACTION_WORKFLOW_STATES,
    "needs_review": TRACKER_NEEDS_REVIEW_WORKFLOW_STATES,
    "active": TRACKER_ACTIVE_WORKFLOW_STATES,
    "closed": {"closed"},
}

TRACKER_SORT_OPTIONS = {
    "workflow": "Workflow priority",
    "applied_desc": "Applied date newest first",
    "applied_asc": "Applied date oldest first",
    "company": "Company A-Z",
    "role": "Role A-Z",
    "status": "Status A-Z",
    "outcome": "Outcome A-Z",
}

HISTORY_SORT_OPTIONS = {
    "event_desc": "Date newest first",
    "event_asc": "Date oldest first",
    "company": "Company A-Z",
    "role": "Role A-Z",
    "status": "Decision A-Z",
    "outcome": "Outcome A-Z",
}

HISTORY_QUICK_FILTERS = {
    "all": {
        "decision_filter": "",
        "outcome_filter": "",
    },
    "applied": {
        "decision_filter": "Applied",
        "outcome_filter": "",
    },
    "passed": {
        "decision_filter": "Passed",
        "outcome_filter": "",
    },
    "rejected": {
        "decision_filter": "",
        "outcome_filter": "Rejected",
    },
    "withdrawn": {
        "decision_filter": "",
        "outcome_filter": "Withdrawn",
    },
    "closed_before_application": {
        "decision_filter": "",
        "outcome_filter": "Closed Before Application",
    },
}

CANONICAL_DECISION_FILTER_OPTIONS = (
    "Applied",
    "Passed",
    "Withdrawn",
    "Revisit",
)

TRACKER_OUTCOME_FILTER_OPTIONS = (
    "Pending / In Progress",
    "Interview Scheduled",
    "Interview Completed",
    "Waiting For Feedback",
    "Offer",
    "Dormant",
    "N/A",
)

HISTORY_OUTCOME_FILTER_OPTIONS = (
    "Closed Before Application",
    "Rejected - No Interview",
    "Rejected - After Interview",
    "Withdrawn",
    "N/A",
)

TRACKER_TERMINAL_OUTCOME_OPTIONS = (
    "Closed Before Application",
    "Rejected - No Interview",
    "Rejected - After Interview",
    "Withdrawn",
)

TRACKER_WORKFLOW_PRIORITY = {
    "follow_up_due": 10,
    "needs_date_review": 20,
    "active_pipeline": 30,
    "follow_up_scheduled": 40,
    "waiting": 50,
    "dormant": 60,
    "stale": 70,
    "presumed_closed": 80,
    "closed": 90,
}

TRACKER_WORKFLOW_LABELS = {
    "follow_up_due": "Follow-up Due",
    "needs_date_review": "Needs Date Review",
    "active_pipeline": "Active Pipeline",
    "follow_up_scheduled": "Follow-up Scheduled",
    "waiting": "Waiting",
    "dormant": "Dormant",
    "stale": "Stale",
    "presumed_closed": "Presumed Closed",
    "closed": "Closed",
}

TRACKER_STATUS_OPTIONS = (
    "Applied",
)

TRACKER_OUTCOME_OPTIONS = (
    "Pending / In Progress",
    "Interview Scheduled",
    "Interview Completed",
    "Waiting For Feedback",
    "Offer",
    "Dormant",
    "N/A",
)

TRACKER_EDIT_OUTCOME_OPTIONS = TRACKER_OUTCOME_OPTIONS + TRACKER_TERMINAL_OUTCOME_OPTIONS

HISTORY_QUICK_ACTIONS = {
    "restore_to_tracker": {
        "label": "Restore to Active Applications",
        "status": "Applied",
        "outcome": "Pending / In Progress",
    },
}

TRACKER_QUICK_ACTIONS = {
    "refresh_activity_today": {
        "label": "Refresh activity today",
        "status": "Applied",
        "outcome": "Pending / In Progress",
        "last_activity_on": "today",
    },
    "follow_up_next_week": {
        "label": "Schedule follow-up next week",
        "status": "Applied",
        "outcome": "Pending / In Progress",
        "follow_up_on": "today+7",
        "last_activity_on": "today",
    },
    "follow_up_due": {
        "label": "Mark follow-up due",
        "status": "Applied",
        "outcome": "Pending / In Progress",
        "follow_up_on": "today",
    },
    "dormant": {
        "label": "Mark dormant",
        "status": "Applied",
        "outcome": "Dormant",
    },
    "interview_scheduled": {
        "label": "Mark interview scheduled",
        "status": "Applied",
        "outcome": "Interview Scheduled",
    },
    "waiting_for_feedback": {
        "label": "Mark waiting for feedback",
        "status": "Applied",
        "outcome": "Waiting For Feedback",
    },
    "offer": {
        "label": "Mark offer",
        "status": "Applied",
        "outcome": "Offer",
    },
    "rejected_no_interview": {
        "label": "Move to history: rejected - no interview",
        "status": "Applied",
        "outcome": "Rejected - No Interview",
    },
    "withdrawn": {
        "label": "Move to history: withdrawn",
        "status": "Applied",
        "outcome": "Withdrawn",
    },
}

REPORT_FILE_EXTENSIONS = {".html", ".htm", ".md", ".txt"}

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
        "description": "Latest HTML scan report. Open this first.",
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

DEFAULT_REPORT_FILE_DESCRIPTION = "Additional file in the reports directory."

DEFAULT_SCAN_CONFIG_PATH = DEFAULT_COMPANY_CONFIG_PATH
DEFAULT_SCAN_SCORING_PATH = DEFAULT_SCORING_CONFIG_PATH
DEFAULT_SCAN_REPORT_PATH = DEFAULT_REPORT_PATH
DEFAULT_SCAN_EMAIL_PREVIEW_PATH = DEFAULT_EMAIL_PREVIEW_PATH


@dataclass(frozen=True)
class TrackerApplicationView:
    application: ApplicationRecord
    workflow_state: str
    workflow_label: str


@dataclass(frozen=True)
class TrackerSummaryView:
    total: int
    needs_action: int
    needs_review: int
    active: int
    closed: int


@dataclass(frozen=True)
class LatestReportSummaryView:
    generated_at: str | None
    html_report_name: str
    html_report_exists: bool
    top_matches: int
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
    tracker_add_url: str


@dataclass(frozen=True)
class ReportCollectorErrorView:
    company_key: str
    company_name: str
    source_type: str
    message: str


@dataclass(frozen=True)
class HistorySummaryView:
    total: int
    applied: int
    passed: int
    withdrawn: int
    closed_before_application: int
    rejected: int


@dataclass(frozen=True)
class ReportFileView:
    name: str
    size_bytes: int
    modified_at: str
    description: str
    is_primary: bool
    sort_order: int


@dataclass(frozen=True)
class SettingsView:
    settings_path: str
    database_path: str
    reports_path: str
    logs_path: str
    candidate_profile_path: str | None
    retention_items: list[tuple[str, object]]
    scan_config_path: str
    scan_settings_path: str
    scan_scoring_path: str
    scan_report_path: str
    scan_email_preview_path: str
    email_status: str


def create_app(
    settings_path: str | Path | None = None,
    *,
    base_directory: str | Path | None = None,
) -> Flask:
    app = Flask(__name__)
    runtime_paths = (
        RuntimePaths.from_settings(
            settings_path=settings_path,
            base_directory=base_directory,
        )
        if settings_path is not None and base_directory is not None
        else RuntimePaths.from_settings_argument(settings_path)
    )
    app.config["JOB_RADAR_RUNTIME_PATHS"] = runtime_paths
    app.config["JOB_RADAR_SETTINGS_PATH"] = str(runtime_paths.settings_path)

    @app.get("/")
    def index() -> str:
        database_path = _get_database_path(app)
        applications = _get_tracker_application_views(database_path)
        tracker_summary = _build_tracker_summary(applications)
        attention_applications = _get_dashboard_attention_applications(applications)
        latest_report = _build_latest_report_summary(app)

        return render_template(
            "index.html",
            tracker_summary=tracker_summary,
            attention_applications=attention_applications,
            latest_report=latest_report,
        )

    @app.get("/settings")
    def settings() -> str:
        settings_view = _build_settings_view(app)

        return render_template(
            "settings.html",
            settings_view=settings_view,
        )

    @app.get("/companies")
    def companies() -> str:
        company_config_path = str(
            _get_runtime_paths(app).company_config_path
        )
        company_views = build_company_config_views(company_config_path)
        selected_status = request.args.get("status", "")
        selected_source_type = request.args.get("source_type", "")
        search_query = request.args.get("q", "").strip()
        filtered_companies = filter_company_config_views(
            company_views,
            selected_status=selected_status,
            selected_source_type=selected_source_type,
            search_query=search_query,
        )
        source_summaries = build_company_source_summaries(company_views)

        return render_template(
            "companies.html",
            companies=filtered_companies,
            source_summaries=source_summaries,
            company_config_path=company_config_path,
            total_companies=len(company_views),
            enabled_companies=sum(1 for company in company_views if company.enabled),
            disabled_companies=sum(1 for company in company_views if not company.enabled),
            selected_status=selected_status,
            selected_source_type=selected_source_type,
            search_query=search_query,
            filtered_company_count=len(filtered_companies),
        )

    @app.get("/companies/<company_key>")
    def company_detail(company_key: str) -> str:
        company_config_path = str(
            _get_runtime_paths(app).company_config_path
        )
        company_view = get_company_config_view(
            company_config_path,
            company_key,
        )

        if company_view is None:
            abort(404)

        return render_template(
            "company_detail.html",
            company=company_view,
            company_config_path=company_config_path,
        )

    @app.get("/profile")
    def profile() -> str:
        runtime_paths = _get_runtime_paths(app)
        profile_view = build_candidate_profile_view(
            app.config["JOB_RADAR_SETTINGS_PATH"],
            base_directory=str(runtime_paths.base_directory),
        )

        return render_template(
            "profile.html",
            profile=profile_view,
            upload_result=request.args.get("upload_result", "").strip(),
            upload_error=request.args.get("upload_error", "").strip(),
        )

    @app.post("/profile/resume")
    def upload_resume():
        uploaded_file = request.files.get("resume_file")

        if uploaded_file is None or not uploaded_file.filename:
            return redirect(
                url_for(
                    "profile",
                    upload_result="error",
                    upload_error="Choose a resume file to upload.",
                )
            )

        try:
            runtime_paths = _get_runtime_paths(app)
            save_uploaded_resume(
                app.config["JOB_RADAR_SETTINGS_PATH"],
                uploaded_file.filename,
                uploaded_file.read(),
                base_directory=str(runtime_paths.base_directory),
            )
        except ConfigError as error:
            return redirect(
                url_for(
                    "profile",
                    upload_result="error",
                    upload_error=str(error),
                )
            )

        return redirect(url_for("profile", upload_result="success"))

    @app.get("/history")
    def history() -> str:
        sort_name = request.args.get("sort", "event_desc")
        search_query = request.args.get("q", "").strip()
        decision_filter = request.args.get("decision_filter", "").strip()
        outcome_filter = request.args.get("outcome_filter", "").strip()
        quick_filter = request.args.get("quick_filter", "").strip()

        if quick_filter:
            quick_filter_values = HISTORY_QUICK_FILTERS.get(quick_filter)

            if quick_filter_values is None:
                abort(404)

            decision_filter = quick_filter_values["decision_filter"]
            outcome_filter = quick_filter_values["outcome_filter"]

        if sort_name not in HISTORY_SORT_OPTIONS:
            abort(404)

        database_path = _get_database_path(app)
        all_records = fetch_included_job_history_records(database_path)
        searched_records = _search_history_records(all_records, search_query)
        filtered_records = _filter_history_records(
            searched_records,
            decision_filter,
            outcome_filter,
        )
        sorted_records = _sort_history_records(
            filtered_records,
            sort_name,
        )
        history_summary = _build_history_summary(all_records)

        return render_template(
            "history.html",
            database_path=database_path,
            records=sorted_records,
            history_summary=history_summary,
            active_sort=sort_name,
            search_query=search_query,
            active_decision_filter=decision_filter,
            active_outcome_filter=outcome_filter,
            active_quick_filter=quick_filter,
            decision_filter_options=CANONICAL_DECISION_FILTER_OPTIONS,
            outcome_filter_options=HISTORY_OUTCOME_FILTER_OPTIONS,
            sort_options=HISTORY_SORT_OPTIONS,
        )

    @app.get("/history/<path:import_key>/edit")
    def edit_history_record(import_key: str) -> str:
        database_path = _get_database_path(app)
        record = get_history_record(database_path, import_key)

        if record is None:
            abort(404)

        return render_template(
            "history_edit.html",
            record=record,
            decision_options=CANONICAL_DECISION_FILTER_OPTIONS,
            outcome_options=TRACKER_EDIT_OUTCOME_OPTIONS,
            quick_actions=HISTORY_QUICK_ACTIONS,
        )

    @app.post("/history/<path:import_key>/edit")
    def update_history_record(import_key: str):
        database_path = _get_database_path(app)
        record = get_history_record(database_path, import_key)

        if record is None:
            abort(404)

        action = request.form.get("action", "save").strip()

        if action == "delete":
            deleted = delete_history_record(database_path, import_key)

            if not deleted:
                abort(404)

            return redirect(url_for("history"))

        status = request.form["status"].strip()
        outcome = _normalize_optional_form_value("outcome")
        quick_action = request.form.get("quick_action", "").strip()

        if quick_action:
            quick_action_values = HISTORY_QUICK_ACTIONS.get(quick_action)

            if quick_action_values is None:
                abort(400)

            status = quick_action_values["status"]
            outcome = quick_action_values["outcome"]

        result = update_history_record_workflow(
            database_path,
            import_key=import_key,
            company=request.form["company"].strip(),
            role=request.form["role"].strip(),
            source=_normalize_optional_form_value("source"),
            event_date=_normalize_optional_form_value("event_date"),
            status=status,
            outcome=outcome,
            recruiter_contact=_normalize_optional_form_value("recruiter_contact"),
            notes=_normalize_optional_form_value("notes"),
        )

        if result == "missing":
            abort(404)

        if result == "moved_to_tracker":
            return redirect(url_for("tracker", filter="all"))

        return redirect(url_for("history"))

    @app.get("/scan")
    def scan() -> str:
        runtime_paths = _get_runtime_paths(app)
        settings_path = str(runtime_paths.settings_path)
        company_config_path = str(runtime_paths.company_config_path)
        scoring_config_path = str(runtime_paths.scoring_config_path)
        report_path = str(runtime_paths.resolve(DEFAULT_SCAN_REPORT_PATH))
        email_preview_path = str(
            runtime_paths.resolve(DEFAULT_SCAN_EMAIL_PREVIEW_PATH)
        )
        scan_command = (
            "python -m job_radar scan "
            f"--config {company_config_path} "
            f"--settings {settings_path} "
            f"--report {report_path} "
            f"--email-preview {email_preview_path}"
        )

        return render_template(
            "scan.html",
            scan_command=scan_command,
            scan_config_path=company_config_path,
            scan_settings_path=settings_path,
            scan_scoring_path=scoring_config_path,
            scan_report_path=report_path,
            scan_email_preview_path=email_preview_path,
            scan_result=request.args.get("scan_result"),
            scan_error=request.args.get("scan_error", "").strip(),
        )

    @app.post("/scan/run")
    def run_scan():
        runtime_paths = _get_runtime_paths(app)

        try:
            handle_scan(
                config_path=str(runtime_paths.company_config_path),
                settings_path=str(runtime_paths.settings_path),
                report_path=str(
                    runtime_paths.resolve(DEFAULT_SCAN_REPORT_PATH)
                ),
                scoring_path=str(runtime_paths.scoring_config_path),
                email_preview_path=str(
                    runtime_paths.resolve(DEFAULT_SCAN_EMAIL_PREVIEW_PATH)
                ),
                send_email=False,
                base_directory=str(runtime_paths.base_directory),
            )
        except ScanAlreadyRunningError:
            return redirect(url_for("scan", scan_result="busy"))
        except Exception as error:
            return redirect(
                url_for(
                    "scan",
                    scan_result="error",
                    scan_error=str(error),
                )
            )

        return redirect(url_for("scan", scan_result="success"))

    @app.get("/reports/section/<section_name>")
    def report_section_view(section_name: str) -> str:
        section_details = REPORT_SECTION_DETAILS.get(section_name)

        if section_details is None:
            abort(404)

        reports_path = Path(_get_reports_path(app)).resolve()
        snapshot_path = reports_path / "target-scan.json"
        html_report_name = "target-scan.html"
        html_report_path = reports_path / html_report_name

        if not snapshot_path.is_file():
            abort(404)

        snapshot = load_report_snapshot(snapshot_path)
        job_cards: list[ReportJobCardView] = []
        collector_errors: list[ReportCollectorErrorView] = []

        if section_name == "collector_errors":
            collector_errors = [
                _build_report_collector_error_view(error)
                for error in snapshot.collector_errors
            ]
        else:
            snapshot_jobs = getattr(snapshot, section_name)
            job_cards = [
                _build_report_job_card(job)
                for job in snapshot_jobs
            ]

        return render_template(
            "report_section.html",
            section_name=section_name,
            section_title=section_details["page_title"],
            section_description=section_details["description"],
            empty_message=section_details["empty_message"],
            job_cards=job_cards,
            collector_errors=collector_errors,
            html_report_name=html_report_name,
            html_report_exists=html_report_path.is_file(),
        )

    @app.get("/reports")
    def reports() -> str:
        reports_path = _get_reports_path(app)
        report_files = _get_report_file_views(reports_path)
        primary_report_files = sorted(
            [report for report in report_files if report.is_primary],
            key=lambda report: report.sort_order,
        )
        other_report_files = [
            report for report in report_files if not report.is_primary
        ]

        return render_template(
            "reports.html",
            reports_path=reports_path,
            report_files=report_files,
            primary_report_files=primary_report_files,
            other_report_files=other_report_files,
        )

    @app.get("/reports/view/<path:report_name>")
    def report_view(report_name: str) -> str:
        reports_path = Path(_get_reports_path(app)).resolve()
        report_path = _validate_report_path(reports_path, report_name)
        report_kind = "html" if report_path.suffix.lower() in {".html", ".htm"} else "text"
        report_content = _read_report_view_content(report_path, report_kind)

        return render_template(
            "report_view.html",
            report_name=report_name,
            report_content=report_content,
            report_kind=report_kind,
            is_email_preview="email" in report_name.lower(),
        )

    @app.get("/reports/<path:report_name>")
    def report_file(report_name: str):
        reports_path = Path(_get_reports_path(app)).resolve()
        _validate_report_path(reports_path, report_name)

        return send_from_directory(reports_path, report_name)

    @app.get("/tracker/")
    def tracker_trailing_slash():
        return redirect(url_for("tracker", **request.args))

    @app.get("/tracker")
    def tracker() -> str:
        filter_name = request.args.get("filter", "all")
        sort_name = request.args.get("sort", "applied_desc")
        search_query = request.args.get("q", "").strip()
        status_filter = request.args.get("status_filter", "").strip()
        outcome_filter = request.args.get("outcome_filter", "").strip()

        if filter_name not in TRACKER_FILTERS:
            abort(404)

        if sort_name not in TRACKER_SORT_OPTIONS:
            abort(404)

        database_path = _get_database_path(app)
        applications = _get_tracker_application_views(database_path)
        tracker_summary = _build_tracker_summary(applications)
        workflow_filtered_applications = _filter_tracker_applications(
            applications,
            filter_name,
        )
        searched_applications = _search_tracker_applications(
            workflow_filtered_applications,
            search_query,
        )
        field_filtered_applications = _filter_tracker_applications_by_fields(
            searched_applications,
            status_filter,
            outcome_filter,
        )
        sorted_applications = _sort_tracker_applications(
            field_filtered_applications,
            sort_name,
        )

        return render_template(
            "tracker.html",
            database_path=database_path,
            applications=sorted_applications,
            tracker_summary=tracker_summary,
            active_filter=filter_name,
            active_sort=sort_name,
            search_query=search_query,
            active_status_filter=status_filter,
            active_outcome_filter=outcome_filter,
            status_filter_options=CANONICAL_DECISION_FILTER_OPTIONS,
            outcome_filter_options=TRACKER_OUTCOME_FILTER_OPTIONS,
            filters=TRACKER_FILTERS,
            sort_options=TRACKER_SORT_OPTIONS,
        )

    @app.get("/tracker/add")
    def add_tracker_application() -> str:
        prefill_values = {
            "job_radar_id": request.args.get("job_radar_id", "").strip(),
            "company_name": request.args.get("company_name", "").strip(),
            "role_title": request.args.get("role_title", "").strip(),
            "source_url": request.args.get("source_url", "").strip(),
            "status": request.args.get("status", "Applied").strip() or "Applied",
            "outcome": (
                request.args.get("outcome", "Pending / In Progress").strip()
                or "Pending / In Progress"
            ),
            "applied_on": request.args.get("applied_on", "").strip(),
            "follow_up_on": request.args.get("follow_up_on", "").strip(),
            "last_activity_on": request.args.get("last_activity_on", "").strip(),
        }

        return render_template(
            "tracker_add.html",
            status_options=TRACKER_STATUS_OPTIONS,
            outcome_options=TRACKER_OUTCOME_OPTIONS,
            prefill_values=prefill_values,
        )

    @app.post("/tracker/add")
    def save_new_tracker_application():
        database_path = _get_database_path(app)

        company_name = request.form["company_name"].strip()
        role_title = request.form["role_title"].strip()
        source_url = _normalize_optional_form_value("source_url")

        job_radar_id = request.form.get("job_radar_id", "").strip()

        if not job_radar_id:
            job_radar_id = build_manual_job_radar_id(
                company_name=company_name,
                role_title=role_title,
                source_url=source_url,
            )

        upsert_application(
            database_path,
            ApplicationRecord(
                job_radar_id=job_radar_id,
                company_name=company_name,
                role_title=role_title,
                source_url=source_url,
                status=request.form["status"].strip(),
                follow_up_on=_normalize_optional_form_value("follow_up_on"),
                applied_on=_normalize_optional_form_value("applied_on"),
                last_activity_on=_normalize_optional_form_value("last_activity_on"),
                outcome=_normalize_optional_form_value("outcome"),
                notes=_normalize_optional_form_value("notes"),
            ),
        )

        return redirect(
            url_for(
                "edit_tracker_application",
                job_radar_id=job_radar_id,
                filter="all",
                tracked="created",
            )
        )


    @app.get("/tracker/<path:job_radar_id>/edit")
    def edit_tracker_application(job_radar_id: str) -> str:
        database_path = _get_database_path(app)
        application = get_application(database_path, job_radar_id)

        if application is None:
            abort(404)

        workflow_state = get_application_workflow_state(application)
        return_filter = request.args.get("filter", "all")

        if return_filter not in TRACKER_FILTERS:
            return_filter = "all"

        return render_template(
            "tracker_edit.html",
            application=application,
            workflow_state=workflow_state,
            workflow_label=TRACKER_WORKFLOW_LABELS.get(
                workflow_state,
                workflow_state.replace("_", " ").title(),
            ),
            return_filter=return_filter,
            status_options=TRACKER_STATUS_OPTIONS,
            outcome_options=TRACKER_EDIT_OUTCOME_OPTIONS,
            quick_actions=TRACKER_QUICK_ACTIONS,
            tracker_notice=request.args.get("tracked", "").strip(),
            next_action_message=_build_tracker_next_action_message(
                application,
                workflow_state,
            ),
        )

    @app.post("/tracker/<path:job_radar_id>/edit")
    def update_tracker_application(job_radar_id: str):
        database_path = _get_database_path(app)

        action = request.form.get("action", "save").strip()

        if action == "delete":
            deleted = delete_tracker_application(database_path, job_radar_id)

            if not deleted:
                abort(404)

            return redirect(url_for("tracker", filter="all"))

        status = request.form["status"].strip()
        follow_up_on = _normalize_optional_form_value("follow_up_on")
        applied_on = _normalize_optional_form_value("applied_on")
        last_activity_on = _normalize_optional_form_value("last_activity_on")
        outcome = _normalize_optional_form_value("outcome")
        notes = _normalize_optional_form_value("notes")
        quick_action = request.form.get("quick_action", "").strip()

        if quick_action:
            quick_action_values = TRACKER_QUICK_ACTIONS.get(quick_action)

            if quick_action_values is None:
                abort(400)

            status = quick_action_values["status"]
            outcome = quick_action_values["outcome"]
            follow_up_on = _resolve_quick_action_date(
                quick_action_values.get("follow_up_on"),
                follow_up_on,
            )
            last_activity_on = _resolve_quick_action_date(
                quick_action_values.get("last_activity_on"),
                last_activity_on,
            )

        result = update_tracker_application_workflow(
            database_path,
            job_radar_id=job_radar_id,
            status=status,
            follow_up_on=follow_up_on,
            applied_on=applied_on,
            last_activity_on=last_activity_on,
            outcome=outcome,
            notes=notes,
        )

        if result == "missing":
            abort(404)

        return_filter = request.form.get("return_filter", "all")

        if return_filter not in TRACKER_FILTERS:
            return_filter = "all"

        return redirect(url_for("tracker", filter=return_filter))

    return app


def _build_settings_view(app: Flask) -> SettingsView:
    settings_path = app.config["JOB_RADAR_SETTINGS_PATH"]
    settings = load_settings(settings_path)
    retention = settings.get("retention", {})
    email_readiness = get_email_readiness(settings.email)

    return SettingsView(
        settings_path=settings_path,
        database_path=settings["database_path"],
        reports_path=settings["reports_path"],
        logs_path=settings["logs_path"],
        candidate_profile_path=settings.get("candidate_profile_path"),
        retention_items=(
            sorted(retention.items())
            if isinstance(retention, dict)
            else []
        ),
        scan_config_path=DEFAULT_SCAN_CONFIG_PATH,
        scan_settings_path=settings_path,
        scan_scoring_path=DEFAULT_SCAN_SCORING_PATH,
        scan_report_path=DEFAULT_SCAN_REPORT_PATH,
        scan_email_preview_path=DEFAULT_SCAN_EMAIL_PREVIEW_PATH,
        email_status=email_readiness.message,
    )


def _get_runtime_paths(app: Flask) -> RuntimePaths:
    return app.config["JOB_RADAR_RUNTIME_PATHS"]


def _get_database_path(app: Flask) -> str:
    database_path = _get_runtime_paths(app).database_path
    initialize_database(database_path)
    return str(database_path)


def _get_reports_path(app: Flask) -> str:
    return str(_get_runtime_paths(app).reports_path)


def _read_report_view_content(report_path: Path, report_kind: str) -> str:
    report_content = report_path.read_text(encoding="utf-8", errors="replace")

    if report_kind != "html":
        return report_content

    # Generated report HTML may include its own light-theme CSS and full document
    # shell. The GUI viewer owns page styling, so only embed the report body.
    report_content = REPORT_HTML_STYLE_PATTERN.sub("", report_content)
    body_match = REPORT_HTML_BODY_PATTERN.search(report_content)

    if body_match is None:
        return report_content

    return body_match.group(1).strip()


def _validate_report_path(reports_path: Path, report_name: str) -> Path:
    report_path = (reports_path / report_name).resolve()

    if reports_path not in report_path.parents:
        abort(404)

    if not report_path.is_file():
        abort(404)

    if report_path.suffix.lower() not in REPORT_FILE_EXTENSIONS:
        abort(404)

    return report_path


def _get_report_file_views(reports_path: str) -> list[ReportFileView]:
    reports_dir = Path(reports_path)

    if not reports_dir.exists():
        return []

    report_files: list[ReportFileView] = []

    for path in reports_dir.iterdir():
        if not path.is_file():
            continue

        if path.name.startswith("."):
            continue

        if path.suffix.lower() not in REPORT_FILE_EXTENSIONS:
            continue

        stat = path.stat()
        primary_details = PRIMARY_REPORT_FILE_DETAILS.get(path.name)

        report_files.append(
            ReportFileView(
                name=path.name,
                size_bytes=stat.st_size,
                modified_at=date.fromtimestamp(stat.st_mtime).isoformat(),
                description=(
                    primary_details["description"]
                    if primary_details
                    else DEFAULT_REPORT_FILE_DESCRIPTION
                ),
                is_primary=primary_details is not None,
                sort_order=(
                    primary_details["sort_order"]
                    if primary_details
                    else 999
                ),
            )
        )

    return sorted(report_files, key=lambda report: report.modified_at, reverse=True)


def _get_tracker_application_views(database_path: str) -> list[TrackerApplicationView]:
    application_views: list[TrackerApplicationView] = []

    for application in list_applications(database_path):
        workflow_state = get_application_workflow_state(application)
        application_views.append(
            TrackerApplicationView(
                application=application,
                workflow_state=workflow_state,
                workflow_label=TRACKER_WORKFLOW_LABELS.get(
                    workflow_state,
                    workflow_state,
                ),
            )
        )

    return application_views

def _build_tracker_summary(
    applications: list[TrackerApplicationView],
) -> TrackerSummaryView:
    return TrackerSummaryView(
        total=len(applications),
        needs_action=sum(
            1
            for application in applications
            if application.workflow_state in TRACKER_NEEDS_ACTION_WORKFLOW_STATES
        ),
        needs_review=sum(
            1
            for application in applications
            if application.workflow_state in TRACKER_NEEDS_REVIEW_WORKFLOW_STATES
        ),
        active=sum(
            1
            for application in applications
            if application.workflow_state in TRACKER_ACTIVE_WORKFLOW_STATES
        ),
        closed=sum(
            1
            for application in applications
            if application.workflow_state == "closed"
        ),
    )


def _get_dashboard_attention_applications(
    applications: list[TrackerApplicationView],
) -> list[TrackerApplicationView]:
    attention_states = {
        "follow_up_due",
        "needs_date_review",
        "dormant",
        "stale",
        "presumed_closed",
    }

    return [
        application
        for application in sorted(applications, key=_get_tracker_application_sort_key)
        if application.workflow_state in attention_states
    ][:5]


def _build_latest_report_summary(app: Flask) -> LatestReportSummaryView:
    reports_path = Path(_get_reports_path(app))
    snapshot_path = reports_path / "target-scan.json"
    html_report_name = "target-scan.html"
    html_report_path = reports_path / html_report_name

    if not snapshot_path.is_file():
        return LatestReportSummaryView(
            generated_at=None,
            html_report_name=html_report_name,
            html_report_exists=html_report_path.is_file(),
            top_matches=0,
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
        review_needed=snapshot.summary.review_needed,
        tracked_applications=snapshot.summary.tracked_applications,
        new_jobs=snapshot.summary.new_jobs,
        collector_errors=snapshot.summary.collector_errors,
    )


def _format_snapshot_generated_at(generated_at: str | None) -> str | None:
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


def _build_report_job_card(
    job: ReportSnapshotJob,
) -> ReportJobCardView:
    return ReportJobCardView(
        title=job.title,
        url=job.url,
        company=job.company,
        location=job.location,
        compensation=job.compensation,
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
        history_risk=job.history_risk,
        job_radar_id=job.job_radar_id,
        tracker_add_url=url_for(
            "add_tracker_application",
            job_radar_id=job.job_radar_id,
            company_name=job.company,
            role_title=job.title,
            source_url=job.url or "",
            status="Applied",
            outcome="Pending / In Progress",
            applied_on=date.today().isoformat(),
        ),
    )


def _build_history_summary(records: list) -> HistorySummaryView:
    # These counts summarize the archive itself, not only the current filtered
    # table. That keeps the page useful as a dashboard while search narrows rows.
    return HistorySummaryView(
        total=len(records),
        applied=sum(
            1
            for record in records
            if _matches_filter_value(record.status, "Applied")
        ),
        passed=sum(
            1
            for record in records
            if _matches_filter_value(record.status, "Passed")
        ),
        withdrawn=sum(
            1
            for record in records
            if _matches_filter_value(record.status, "Withdrawn")
            or _matches_filter_value(record.outcome_category, "Withdrawn")
        ),
        closed_before_application=sum(
            1
            for record in records
            if _matches_filter_value(
                record.outcome_category,
                "Closed Before Application",
            )
        ),
        rejected=sum(
            1
            for record in records
            if _matches_filter_value(record.outcome_category, "Rejected - No Interview")
            or _matches_filter_value(record.outcome_category, "Rejected - After Interview")
        ),
    )


def _get_tracker_application_sort_key(
    application_view: TrackerApplicationView,
) -> tuple[int, str, str]:
    application = application_view.application

    return (
        TRACKER_WORKFLOW_PRIORITY.get(application_view.workflow_state, 999),
        application.company_name.lower(),
        application.role_title.lower(),
    )


def _filter_tracker_applications(
    applications: list[TrackerApplicationView],
    filter_name: str,
) -> list[TrackerApplicationView]:
    workflow_states = TRACKER_FILTERS[filter_name]

    if workflow_states is None:
        return applications

    return [
        application
        for application in applications
        if application.workflow_state in workflow_states
    ]


def _filter_tracker_applications_by_fields(
    applications: list[TrackerApplicationView],
    status_filter: str,
    outcome_filter: str,
) -> list[TrackerApplicationView]:
    # Workflow filters answer "what needs attention"; raw field filters answer
    # spreadsheet-style review questions such as "show rejected" or "show dormant".
    filtered_applications = applications

    if status_filter:
        filtered_applications = [
            application_view
            for application_view in filtered_applications
            if _matches_filter_value(application_view.application.status, status_filter)
        ]

    if outcome_filter:
        filtered_applications = [
            application_view
            for application_view in filtered_applications
            if _matches_filter_value(application_view.application.outcome, outcome_filter)
        ]

    return filtered_applications


def _search_tracker_applications(
    applications: list[TrackerApplicationView],
    search_query: str,
) -> list[TrackerApplicationView]:
    if not search_query:
        return applications

    normalized_query = search_query.lower()

    return [
        application_view
        for application_view in applications
        if normalized_query in _get_tracker_application_search_text(application_view)
    ]


def _get_tracker_application_search_text(
    application_view: TrackerApplicationView,
) -> str:
    application = application_view.application

    # Keep search intentionally simple and local. The tracker GUI should make
    # stored application context easier to find without becoming a second index.
    searchable_values = (
        application.company_name,
        application.role_title,
        application.status,
        application_view.workflow_state,
        application.outcome,
        application.job_radar_id,
        application.source_url,
        application.notes,
    )

    return " ".join(value or "" for value in searchable_values).lower()


def _sort_tracker_applications(
    applications: list[TrackerApplicationView],
    sort_name: str,
) -> list[TrackerApplicationView]:
    if sort_name == "applied_desc":
        return sorted(applications, key=_get_applied_date_desc_sort_key)

    if sort_name == "applied_asc":
        return sorted(applications, key=_get_applied_date_asc_sort_key)

    if sort_name == "company":
        return sorted(
            applications,
            key=lambda row: (
                row.application.company_name.lower(),
                row.application.role_title.lower(),
            ),
        )

    if sort_name == "role":
        return sorted(
            applications,
            key=lambda row: (
                row.application.role_title.lower(),
                row.application.company_name.lower(),
            ),
        )

    if sort_name == "status":
        return sorted(
            applications,
            key=lambda row: (
                row.application.status.lower(),
                row.application.company_name.lower(),
                row.application.role_title.lower(),
            ),
        )

    if sort_name == "outcome":
        return sorted(
            applications,
            key=lambda row: (
                (row.application.outcome or "").lower(),
                row.application.company_name.lower(),
                row.application.role_title.lower(),
            ),
        )

    return sorted(applications, key=_get_tracker_application_sort_key)


def _get_applied_date_desc_sort_key(
    application_view: TrackerApplicationView,
) -> tuple[bool, int, str, str]:
    application = application_view.application
    applied_date = _parse_tracker_sort_date(application.applied_on)

    return (
        applied_date is None,
        -(applied_date.toordinal() if applied_date else 0),
        application.company_name.lower(),
        application.role_title.lower(),
    )


def _get_applied_date_asc_sort_key(
    application_view: TrackerApplicationView,
) -> tuple[bool, int, str, str]:
    application = application_view.application
    applied_date = _parse_tracker_sort_date(application.applied_on)

    return (
        applied_date is None,
        applied_date.toordinal() if applied_date else 0,
        application.company_name.lower(),
        application.role_title.lower(),
    )


def _search_history_records(
    records: list,
    search_query: str,
) -> list:
    if not search_query:
        return records

    normalized_query = search_query.lower()

    return [
        record
        for record in records
        if normalized_query in _get_history_record_search_text(record)
    ]


def _get_history_record_search_text(record) -> str:
    # Search covers the human workbook-review fields so the archive can replace
    # spreadsheet filtering for normal history lookup.
    searchable_values = (
        record.company,
        record.role,
        record.status,
        record.outcome_category,
        record.source,
        record.lead_source,
        record.recruiter_contact,
        record.import_key,
        record.notes,
        record.history_type,
    )

    return " ".join(value or "" for value in searchable_values).lower()


def _filter_history_records(
    records: list,
    decision_filter: str,
    outcome_filter: str,
) -> list:
    filtered_records = records

    if decision_filter:
        filtered_records = [
            record
            for record in filtered_records
            if _matches_filter_value(record.status, decision_filter)
        ]

    if outcome_filter:
        filtered_records = [
            record
            for record in filtered_records
            if _matches_history_outcome_filter(record, outcome_filter)
        ]

    return filtered_records


def _matches_filter_value(value: str | None, selected_filter: str) -> bool:
    if value is None:
        return False

    return value.strip().casefold() == selected_filter.strip().casefold()


def _matches_history_outcome_filter(record, outcome_filter: str) -> bool:
    if outcome_filter.casefold() == "rejected":
        return _matches_filter_value(record.outcome_category, "Rejected - No Interview") or _matches_filter_value(
            record.outcome_category,
            "Rejected - After Interview",
        )

    if outcome_filter.casefold() == "withdrawn":
        return _matches_filter_value(record.status, "Withdrawn") or _matches_filter_value(
            record.outcome_category,
            "Withdrawn",
        )

    return _matches_filter_value(record.outcome_category, outcome_filter)


def _sort_history_records(
    records: list,
    sort_name: str,
) -> list:
    if sort_name == "event_asc":
        return sorted(records, key=_get_history_event_date_asc_sort_key)

    if sort_name == "company":
        return sorted(
            records,
            key=lambda record: (
                record.company.lower(),
                record.role.lower(),
            ),
        )

    if sort_name == "role":
        return sorted(
            records,
            key=lambda record: (
                record.role.lower(),
                record.company.lower(),
            ),
        )

    if sort_name == "status":
        return sorted(
            records,
            key=lambda record: (
                (record.status or "").lower(),
                record.company.lower(),
                record.role.lower(),
            ),
        )

    if sort_name == "outcome":
        return sorted(
            records,
            key=lambda record: (
                (record.outcome_category or "").lower(),
                record.company.lower(),
                record.role.lower(),
            ),
        )

    return sorted(records, key=_get_history_event_date_desc_sort_key)


def _get_history_event_date_desc_sort_key(record) -> tuple[bool, int, str, str]:
    event_date = _parse_tracker_sort_date(record.event_date)

    return (
        event_date is None,
        -(event_date.toordinal() if event_date else 0),
        record.company.lower(),
        record.role.lower(),
    )


def _get_history_event_date_asc_sort_key(record) -> tuple[bool, int, str, str]:
    event_date = _parse_tracker_sort_date(record.event_date)

    return (
        event_date is None,
        event_date.toordinal() if event_date else 0,
        record.company.lower(),
        record.role.lower(),
    )


def _parse_tracker_sort_date(value: str | None) -> date | None:
    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _format_tracker_action_date(value: str | None) -> str | None:
    parsed_date = _parse_tracker_sort_date(value)

    if parsed_date is None:
        return None

    return f"{parsed_date:%B} {parsed_date.day}, {parsed_date.year}"


def _build_tracker_next_action_message(
    application: ApplicationRecord,
    workflow_state: str,
) -> str:
    follow_up_date = _parse_tracker_sort_date(application.follow_up_on)
    formatted_follow_up_date = _format_tracker_action_date(application.follow_up_on)
    formatted_last_activity_date = _format_tracker_action_date(
        application.last_activity_on
    )

    if workflow_state == "needs_date_review":
        return "The follow-up date needs review. Use the date picker or a quick action to repair it."

    if workflow_state == "follow_up_due":
        if formatted_follow_up_date is not None:
            return (
                f"Follow-up was due on {formatted_follow_up_date}. "
                "Refresh activity today or schedule the next follow-up."
            )

        return "Follow-up is due. Refresh activity today or schedule the next follow-up."

    if workflow_state == "follow_up_scheduled":
        if formatted_follow_up_date is not None:
            return (
                f"Follow up on {formatted_follow_up_date}. "
                "Keep this page updated as the application moves through the pipeline."
            )

        return "Follow-up is scheduled. Keep this page updated as the application moves through the pipeline."

    if workflow_state == "active_pipeline":
        if formatted_last_activity_date is not None:
            return (
                f"Last activity was recorded on {formatted_last_activity_date}. "
                "Keep interview or recruiter notes current and record the next follow-up date."
            )

        return "This application is active. Keep interview or recruiter notes current and record the next follow-up date."

    if workflow_state == "waiting":
        if formatted_last_activity_date is not None:
            return (
                f"Waiting for an update since {formatted_last_activity_date}. "
                "Record the next follow-up date when appropriate."
            )

        return "This application is waiting for an update. Record the next follow-up date when appropriate."

    if workflow_state == "dormant":
        return "This application is dormant. Decide whether to revive it, leave it dormant, or move it to history."

    if workflow_state == "stale":
        if formatted_last_activity_date is not None:
            return (
                f"No activity has been recorded since {formatted_last_activity_date}. "
                "Refresh activity, schedule follow-up, or move it to history if it is effectively closed."
            )

        return "This application has gone stale. Refresh activity, schedule follow-up, or move it to history if it is effectively closed."

    if workflow_state == "presumed_closed":
        return "This application is probably closed. Confirm the outcome and move it to history if there is no active path forward."

    if workflow_state == "closed":
        return "This application is closed. It should stay in history unless you need to correct the record."

    if not application.follow_up_on:
        return "No follow-up date is set. Schedule a follow-up so this application does not go stale."

    if follow_up_date is None:
        return "The follow-up date needs review. Use the date picker or a quick action to repair it."

    if follow_up_date <= date.today():
        return (
            f"Follow-up was due on {formatted_follow_up_date}. "
            "Refresh activity today or schedule the next follow-up."
        )

    return (
        f"Follow up on {formatted_follow_up_date}. "
        "Keep this page updated as the application moves through the pipeline."
    )


def _resolve_quick_action_date(
    quick_action_value: str | None,
    current_value: str | None,
) -> str | None:
    if quick_action_value is None:
        return current_value

    today = date.today()

    if quick_action_value == "today":
        return today.isoformat()

    if quick_action_value == "today+7":
        return (today + timedelta(days=7)).isoformat()

    return quick_action_value


def _normalize_optional_form_value(field_name: str) -> str | None:
    value = request.form.get(field_name, "").strip()

    if not value:
        return None

    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="job_radar.web_app",
        description="Local Job Radar web interface",
    )
    parser.add_argument(
        "--settings",
        default=None,
        help="Optional explicit path to settings.yaml",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface for the local web app",
    )
    parser.add_argument(
        "--port",
        default=5000,
        type=int,
        help="Port for the local web app",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Run Flask in debug mode",
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()
    app = create_app(settings_path=args.settings)
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
