from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from flask import Flask, abort, redirect, render_template, request, url_for

from job_radar.tracker.tracker_ids import build_manual_job_radar_id
from job_radar.tracker.tracker_models import ApplicationRecord
from job_radar.tracker.tracker_service import (
    delete_tracker_application,
    get_application_workflow_state,
    update_tracker_application_workflow,
)
from job_radar.tracker.tracker_storage import (
    get_application,
    list_applications,
    upsert_application,
)
from job_radar.web_routes.common import (
    matches_filter_value,
    normalize_optional_form_value,
    parse_sort_date,
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

TRACKER_EDIT_OUTCOME_OPTIONS = (
    TRACKER_OUTCOME_OPTIONS + TRACKER_TERMINAL_OUTCOME_OPTIONS
)

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


def register_tracker_routes(
    app: Flask,
    *,
    get_database_path: Callable[[], str],
    today_provider: Callable[[], date],
) -> None:
    """Register application-tracker viewing and editing routes."""

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

        database_path = get_database_path()
        applications = get_tracker_application_views(database_path)
        tracker_summary = build_tracker_summary(applications)
        workflow_filtered_applications = _filter_tracker_applications(
            applications,
            filter_name,
        )
        searched_applications = _search_tracker_applications(
            workflow_filtered_applications,
            search_query,
        )
        field_filtered_applications = (
            _filter_tracker_applications_by_fields(
                searched_applications,
                status_filter,
                outcome_filter,
            )
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
            "job_radar_id": request.args.get(
                "job_radar_id",
                "",
            ).strip(),
            "company_name": request.args.get(
                "company_name",
                "",
            ).strip(),
            "role_title": request.args.get(
                "role_title",
                "",
            ).strip(),
            "source_url": request.args.get(
                "source_url",
                "",
            ).strip(),
            "status": (
                request.args.get("status", "Applied").strip()
                or "Applied"
            ),
            "outcome": (
                request.args.get(
                    "outcome",
                    "Pending / In Progress",
                ).strip()
                or "Pending / In Progress"
            ),
            "applied_on": request.args.get(
                "applied_on",
                "",
            ).strip(),
            "follow_up_on": request.args.get(
                "follow_up_on",
                "",
            ).strip(),
            "last_activity_on": request.args.get(
                "last_activity_on",
                "",
            ).strip(),
        }

        return render_template(
            "tracker_add.html",
            status_options=TRACKER_STATUS_OPTIONS,
            outcome_options=TRACKER_OUTCOME_OPTIONS,
            prefill_values=prefill_values,
        )

    @app.post("/tracker/add")
    def save_new_tracker_application():
        database_path = get_database_path()

        company_name = request.form["company_name"].strip()
        role_title = request.form["role_title"].strip()
        source_url = normalize_optional_form_value("source_url")

        job_radar_id = request.form.get(
            "job_radar_id",
            "",
        ).strip()

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
                follow_up_on=normalize_optional_form_value(
                    "follow_up_on"
                ),
                applied_on=normalize_optional_form_value(
                    "applied_on"
                ),
                last_activity_on=normalize_optional_form_value(
                    "last_activity_on"
                ),
                outcome=normalize_optional_form_value("outcome"),
                notes=normalize_optional_form_value("notes"),
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
        database_path = get_database_path()
        application = get_application(
            database_path,
            job_radar_id,
        )

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
            tracker_notice=request.args.get(
                "tracked",
                "",
            ).strip(),
            next_action_message=_build_tracker_next_action_message(
                application,
                workflow_state,
                today=today_provider(),
            ),
        )

    @app.post("/tracker/<path:job_radar_id>/edit")
    def update_tracker_application(job_radar_id: str):
        database_path = get_database_path()

        action = request.form.get("action", "save").strip()

        if action == "delete":
            deleted = delete_tracker_application(
                database_path,
                job_radar_id,
            )

            if not deleted:
                abort(404)

            return redirect(url_for("tracker", filter="all"))

        status = request.form["status"].strip()
        follow_up_on = normalize_optional_form_value(
            "follow_up_on"
        )
        applied_on = normalize_optional_form_value("applied_on")
        last_activity_on = normalize_optional_form_value(
            "last_activity_on"
        )
        outcome = normalize_optional_form_value("outcome")
        notes = normalize_optional_form_value("notes")
        quick_action = request.form.get(
            "quick_action",
            "",
        ).strip()

        if quick_action:
            quick_action_values = TRACKER_QUICK_ACTIONS.get(
                quick_action
            )

            if quick_action_values is None:
                abort(400)

            today = today_provider()
            status = quick_action_values["status"]
            outcome = quick_action_values["outcome"]
            follow_up_on = _resolve_quick_action_date(
                quick_action_values.get("follow_up_on"),
                follow_up_on,
                today=today,
            )
            last_activity_on = _resolve_quick_action_date(
                quick_action_values.get("last_activity_on"),
                last_activity_on,
                today=today,
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

        return_filter = request.form.get(
            "return_filter",
            "all",
        )

        if return_filter not in TRACKER_FILTERS:
            return_filter = "all"

        return redirect(
            url_for(
                "tracker",
                filter=return_filter,
            )
        )


def get_tracker_application_views(
    database_path: str,
) -> list[TrackerApplicationView]:
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


def build_tracker_summary(
    applications: list[TrackerApplicationView],
) -> TrackerSummaryView:
    return TrackerSummaryView(
        total=len(applications),
        needs_action=sum(
            1
            for application in applications
            if application.workflow_state
            in TRACKER_NEEDS_ACTION_WORKFLOW_STATES
        ),
        needs_review=sum(
            1
            for application in applications
            if application.workflow_state
            in TRACKER_NEEDS_REVIEW_WORKFLOW_STATES
        ),
        active=sum(
            1
            for application in applications
            if application.workflow_state
            in TRACKER_ACTIVE_WORKFLOW_STATES
        ),
        closed=sum(
            1
            for application in applications
            if application.workflow_state == "closed"
        ),
    )


def get_dashboard_attention_applications(
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
        for application in sorted(
            applications,
            key=_get_tracker_application_sort_key,
        )
        if application.workflow_state in attention_states
    ][:5]


def _get_tracker_application_sort_key(
    application_view: TrackerApplicationView,
) -> tuple[int, str, str]:
    application = application_view.application

    return (
        TRACKER_WORKFLOW_PRIORITY.get(
            application_view.workflow_state,
            999,
        ),
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
            if matches_filter_value(
                application_view.application.status,
                status_filter,
            )
        ]

    if outcome_filter:
        filtered_applications = [
            application_view
            for application_view in filtered_applications
            if matches_filter_value(
                application_view.application.outcome,
                outcome_filter,
            )
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
        if normalized_query
        in _get_tracker_application_search_text(
            application_view
        )
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

    return " ".join(
        value or ""
        for value in searchable_values
    ).lower()


def _sort_tracker_applications(
    applications: list[TrackerApplicationView],
    sort_name: str,
) -> list[TrackerApplicationView]:
    if sort_name == "applied_desc":
        return sorted(
            applications,
            key=_get_applied_date_desc_sort_key,
        )

    if sort_name == "applied_asc":
        return sorted(
            applications,
            key=_get_applied_date_asc_sort_key,
        )

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

    return sorted(
        applications,
        key=_get_tracker_application_sort_key,
    )


def _get_applied_date_desc_sort_key(
    application_view: TrackerApplicationView,
) -> tuple[bool, int, str, str]:
    application = application_view.application
    applied_date = parse_sort_date(application.applied_on)

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
    applied_date = parse_sort_date(application.applied_on)

    return (
        applied_date is None,
        applied_date.toordinal() if applied_date else 0,
        application.company_name.lower(),
        application.role_title.lower(),
    )


def _format_tracker_action_date(
    value: str | None,
) -> str | None:
    parsed_date = parse_sort_date(value)

    if parsed_date is None:
        return None

    return (
        f"{parsed_date:%B} "
        f"{parsed_date.day}, "
        f"{parsed_date.year}"
    )


def _build_tracker_next_action_message(
    application: ApplicationRecord,
    workflow_state: str,
    *,
    today: date,
) -> str:
    follow_up_date = parse_sort_date(application.follow_up_on)
    formatted_follow_up_date = _format_tracker_action_date(
        application.follow_up_on
    )
    formatted_last_activity_date = _format_tracker_action_date(
        application.last_activity_on
    )

    if workflow_state == "needs_date_review":
        return (
            "The follow-up date needs review. "
            "Use the date picker or a quick action to repair it."
        )

    if workflow_state == "follow_up_due":
        if formatted_follow_up_date is not None:
            return (
                f"Follow-up was due on {formatted_follow_up_date}. "
                "Refresh activity today or schedule the next follow-up."
            )

        return (
            "Follow-up is due. "
            "Refresh activity today or schedule the next follow-up."
        )

    if workflow_state == "follow_up_scheduled":
        if formatted_follow_up_date is not None:
            return (
                f"Follow up on {formatted_follow_up_date}. "
                "Keep this page updated as the application moves "
                "through the pipeline."
            )

        return (
            "Follow-up is scheduled. Keep this page updated as "
            "the application moves through the pipeline."
        )

    if workflow_state == "active_pipeline":
        if formatted_last_activity_date is not None:
            return (
                "Last activity was recorded on "
                f"{formatted_last_activity_date}. "
                "Keep interview or recruiter notes current and "
                "record the next follow-up date."
            )

        return (
            "This application is active. Keep interview or recruiter "
            "notes current and record the next follow-up date."
        )

    if workflow_state == "waiting":
        if formatted_last_activity_date is not None:
            return (
                "Waiting for an update since "
                f"{formatted_last_activity_date}. "
                "Record the next follow-up date when appropriate."
            )

        return (
            "This application is waiting for an update. "
            "Record the next follow-up date when appropriate."
        )

    if workflow_state == "dormant":
        return (
            "This application is dormant. Decide whether to revive it, "
            "leave it dormant, or move it to history."
        )

    if workflow_state == "stale":
        if formatted_last_activity_date is not None:
            return (
                "No activity has been recorded since "
                f"{formatted_last_activity_date}. "
                "Refresh activity, schedule follow-up, or move it to "
                "history if it is effectively closed."
            )

        return (
            "This application has gone stale. Refresh activity, "
            "schedule follow-up, or move it to history if it is "
            "effectively closed."
        )

    if workflow_state == "presumed_closed":
        return (
            "This application is probably closed. Confirm the outcome "
            "and move it to history if there is no active path forward."
        )

    if workflow_state == "closed":
        return (
            "This application is closed. It should stay in history "
            "unless you need to correct the record."
        )

    if not application.follow_up_on:
        return (
            "No follow-up date is set. Schedule a follow-up so this "
            "application does not go stale."
        )

    if follow_up_date is None:
        return (
            "The follow-up date needs review. "
            "Use the date picker or a quick action to repair it."
        )

    if follow_up_date <= today:
        return (
            f"Follow-up was due on {formatted_follow_up_date}. "
            "Refresh activity today or schedule the next follow-up."
        )

    return (
        f"Follow up on {formatted_follow_up_date}. "
        "Keep this page updated as the application moves "
        "through the pipeline."
    )


def _resolve_quick_action_date(
    quick_action_value: str | None,
    current_value: str | None,
    *,
    today: date,
) -> str | None:
    if quick_action_value is None:
        return current_value

    if quick_action_value == "today":
        return today.isoformat()

    if quick_action_value == "today+7":
        return (today + timedelta(days=7)).isoformat()

    return quick_action_value
