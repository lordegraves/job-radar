import argparse
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from threading import Lock

from flask import Flask, abort, redirect, render_template, request, send_from_directory, url_for

from job_radar.cli import handle_scan
from job_radar.config import ConfigError, load_settings
from job_radar.profile_service import build_candidate_profile_view, save_uploaded_resume
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
    "target-scan.md": {
        "description": "Latest Markdown scan report.",
        "sort_order": 20,
    },
    "target-email-preview.txt": {
        "description": "Latest plain-text email preview.",
        "sort_order": 30,
    },
}

DEFAULT_REPORT_FILE_DESCRIPTION = "Additional file in the reports directory."

DEFAULT_SCAN_CONFIG_PATH = "config/target-companies.yaml"
DEFAULT_SCAN_SCORING_PATH = "config/scoring.yaml"
DEFAULT_SCAN_REPORT_PATH = "reports/target-scan.md"
DEFAULT_SCAN_EMAIL_PREVIEW_PATH = "reports/target-email-preview.txt"

SCAN_RUN_LOCK = Lock()


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


def create_app(settings_path: str = "config/settings.yaml") -> Flask:
    app = Flask(__name__)
    app.config["JOB_RADAR_SETTINGS_PATH"] = settings_path

    @app.get("/")
    def index() -> str:
        database_path = _get_database_path(app)
        applications = _get_tracker_application_views(database_path)
        tracker_summary = _build_tracker_summary(applications)

        return render_template(
            "index.html",
            tracker_summary=tracker_summary,
        )

    @app.get("/settings")
    def settings() -> str:
        settings_view = _build_settings_view(app)

        return render_template(
            "settings.html",
            settings_view=settings_view,
        )

    @app.get("/profile")
    def profile() -> str:
        profile_view = build_candidate_profile_view(
            app.config["JOB_RADAR_SETTINGS_PATH"]
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
            save_uploaded_resume(
                app.config["JOB_RADAR_SETTINGS_PATH"],
                uploaded_file.filename,
                uploaded_file.read(),
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

        result = update_history_record_workflow(
            database_path,
            import_key=import_key,
            company=request.form["company"].strip(),
            role=request.form["role"].strip(),
            source=_normalize_optional_form_value("source"),
            event_date=_normalize_optional_form_value("event_date"),
            status=request.form["status"].strip(),
            outcome=_normalize_optional_form_value("outcome"),
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
        settings_path = app.config["JOB_RADAR_SETTINGS_PATH"]
        scan_command = (
            "python -m job_radar scan "
            f"--config {DEFAULT_SCAN_CONFIG_PATH} "
            f"--settings {settings_path} "
            f"--report {DEFAULT_SCAN_REPORT_PATH} "
            f"--email-preview {DEFAULT_SCAN_EMAIL_PREVIEW_PATH}"
        )

        return render_template(
            "scan.html",
            scan_command=scan_command,
            scan_config_path=DEFAULT_SCAN_CONFIG_PATH,
            scan_settings_path=settings_path,
            scan_scoring_path=DEFAULT_SCAN_SCORING_PATH,
            scan_report_path=DEFAULT_SCAN_REPORT_PATH,
            scan_email_preview_path=DEFAULT_SCAN_EMAIL_PREVIEW_PATH,
            scan_result=request.args.get("scan_result"),
            scan_error=request.args.get("scan_error", "").strip(),
        )

    @app.post("/scan/run")
    def run_scan():
        settings_path = app.config["JOB_RADAR_SETTINGS_PATH"]

        if not SCAN_RUN_LOCK.acquire(blocking=False):
            return redirect(url_for("scan", scan_result="busy"))

        try:
            handle_scan(
                config_path=DEFAULT_SCAN_CONFIG_PATH,
                settings_path=settings_path,
                report_path=DEFAULT_SCAN_REPORT_PATH,
                scoring_path=DEFAULT_SCAN_SCORING_PATH,
                email_preview_path=DEFAULT_SCAN_EMAIL_PREVIEW_PATH,
                send_email=False,
            )
        except Exception as error:
            return redirect(
                url_for(
                    "scan",
                    scan_result="error",
                    scan_error=str(error),
                )
            )
        finally:
            SCAN_RUN_LOCK.release()

        return redirect(url_for("scan", scan_result="success"))

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
        return render_template(
            "tracker_add.html",
            status_options=TRACKER_STATUS_OPTIONS,
            outcome_options=TRACKER_OUTCOME_OPTIONS,
        )

    @app.post("/tracker/add")
    def save_new_tracker_application():
        database_path = _get_database_path(app)

        company_name = request.form["company_name"].strip()
        role_title = request.form["role_title"].strip()
        source_url = _normalize_optional_form_value("source_url")

        upsert_application(
            database_path,
            ApplicationRecord(
                job_radar_id=build_manual_job_radar_id(
                    company_name=company_name,
                    role_title=role_title,
                    source_url=source_url,
                ),
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

        return redirect(url_for("tracker", filter="all"))


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
            return_filter=return_filter,
            status_options=TRACKER_STATUS_OPTIONS,
            outcome_options=TRACKER_EDIT_OUTCOME_OPTIONS,
            quick_actions=TRACKER_QUICK_ACTIONS,
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
    email_settings = settings.get("email", {})

    email_status = "Disabled or not configured"

    if isinstance(email_settings, dict) and email_settings.get("enabled"):
        email_status = "Enabled"

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
        email_status=email_status,
    )


def _get_database_path(app: Flask) -> str:
    settings = load_settings(app.config["JOB_RADAR_SETTINGS_PATH"])
    database_path = settings["database_path"]
    initialize_database(database_path)
    return database_path


def _get_reports_path(app: Flask) -> str:
    settings = load_settings(app.config["JOB_RADAR_SETTINGS_PATH"])
    return settings["reports_path"]


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
        default="config/settings.yaml",
        help="Path to settings.yaml",
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