import argparse
from dataclasses import dataclass
from datetime import date

from flask import Flask, abort, redirect, render_template, request, url_for

from job_radar.config import load_settings
from job_radar.storage import fetch_included_job_history_records, initialize_database
from job_radar.tracker.models import ApplicationRecord
from job_radar.tracker.service import get_application_workflow_state
from job_radar.tracker.storage import (
    get_application,
    list_applications,
    update_application_status,
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
}

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

TRACKER_STATUS_OPTIONS = (
    "applied",
    "follow_up_due",
    "interviewing",
    "offer",
    "dormant",
    "rejected",
    "withdrawn",
)

TRACKER_OUTCOME_OPTIONS = (
    "",
    "Pending / In Progress",
    "Interviewing",
    "Offer",
    "Dormant",
    "Rejected - No Interview",
    "Rejected - After Interview",
    "Withdrawn",
    "Closed Before Application",
    "Alive Until Declared Dead",
)

TRACKER_QUICK_ACTIONS = {
    "follow_up_due": {
        "label": "Mark follow-up due",
        "status": "follow_up_due",
        "outcome": "Pending / In Progress",
    },
    "dormant": {
        "label": "Mark dormant",
        "status": "dormant",
        "outcome": "Dormant",
    },
    "rejected": {
        "label": "Mark rejected",
        "status": "rejected",
        "outcome": "Rejected - No Interview",
    },
    "withdrawn": {
        "label": "Mark withdrawn",
        "status": "withdrawn",
        "outcome": "Withdrawn",
    },
}


@dataclass(frozen=True)
class TrackerApplicationView:
    application: ApplicationRecord
    workflow_state: str


def create_app(settings_path: str = "config/settings.yaml") -> Flask:
    app = Flask(__name__)
    app.config["JOB_RADAR_SETTINGS_PATH"] = settings_path

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/history")
    def history() -> str:
        database_path = _get_database_path(app)
        records = fetch_included_job_history_records(database_path)

        return render_template(
            "history.html",
            database_path=database_path,
            records=records,
        )

    @app.get("/tracker")
    def tracker() -> str:
        filter_name = request.args.get("filter", "all")
        sort_name = request.args.get("sort", "applied_desc")
        search_query = request.args.get("q", "").strip()

        if filter_name not in TRACKER_FILTERS:
            abort(404)

        if sort_name not in TRACKER_SORT_OPTIONS:
            abort(404)

        database_path = _get_database_path(app)
        applications = _get_tracker_application_views(database_path)
        filtered_applications = _filter_tracker_applications(
            applications,
            filter_name,
        )
        searched_applications = _search_tracker_applications(
            filtered_applications,
            search_query,
        )
        sorted_applications = _sort_tracker_applications(
            searched_applications,
            sort_name,
        )

        return render_template(
            "tracker.html",
            database_path=database_path,
            applications=sorted_applications,
            active_filter=filter_name,
            active_sort=sort_name,
            search_query=search_query,
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

        upsert_application(
            database_path,
            ApplicationRecord(
                job_radar_id=request.form["job_radar_id"].strip(),
                company_name=request.form["company_name"].strip(),
                role_title=request.form["role_title"].strip(),
                source_url=_normalize_optional_form_value("source_url"),
                status=request.form["status"].strip(),
                follow_up_on=_normalize_optional_form_value("follow_up_on"),
                applied_on=_normalize_optional_form_value("applied_on"),
                last_activity_on=_normalize_optional_form_value("last_activity_on"),
                outcome=_normalize_optional_form_value("outcome"),
                notes=_normalize_optional_form_value("notes"),
            ),
        )

        return redirect(url_for("tracker", filter="all"))


    @app.get("/tracker/<job_radar_id>/edit")
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
            outcome_options=TRACKER_OUTCOME_OPTIONS,
            quick_actions=TRACKER_QUICK_ACTIONS,
        )

    @app.post("/tracker/<job_radar_id>/edit")
    def update_tracker_application(job_radar_id: str):
        database_path = _get_database_path(app)

        status = request.form["status"].strip()
        outcome = _normalize_optional_form_value("outcome")
        quick_action = request.form.get("quick_action", "").strip()

        if quick_action:
            quick_action_values = TRACKER_QUICK_ACTIONS.get(quick_action)

            if quick_action_values is None:
                abort(400)

            status = quick_action_values["status"]
            outcome = quick_action_values["outcome"]

        updated = update_application_status(
            database_path,
            job_radar_id=job_radar_id,
            status=status,
            follow_up_on=_normalize_optional_form_value("follow_up_on"),
            applied_on=_normalize_optional_form_value("applied_on"),
            last_activity_on=_normalize_optional_form_value("last_activity_on"),
            outcome=outcome,
            notes=_normalize_optional_form_value("notes"),
        )

        if not updated:
            abort(404)

        return_filter = request.form.get("return_filter", "all")

        if return_filter not in TRACKER_FILTERS:
            return_filter = "all"

        return redirect(url_for("tracker", filter=return_filter))

    return app


def _get_database_path(app: Flask) -> str:
    settings = load_settings(app.config["JOB_RADAR_SETTINGS_PATH"])
    database_path = settings["database_path"]
    initialize_database(database_path)
    return database_path


def _get_tracker_application_views(database_path: str) -> list[TrackerApplicationView]:
    return [
        TrackerApplicationView(
            application=application,
            workflow_state=get_application_workflow_state(application),
        )
        for application in list_applications(database_path)
    ]


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


def _parse_tracker_sort_date(value: str | None) -> date | None:
    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


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