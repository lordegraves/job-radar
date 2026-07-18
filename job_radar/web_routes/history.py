"""Serve archived job decisions, filtering, editing, and deletion workflows."""

from collections.abc import Callable
from dataclasses import dataclass

from flask import Flask, abort, redirect, render_template, request, url_for

from job_radar.storage import fetch_included_job_history_records
from job_radar.tracker.tracker_service import (
    delete_history_record,
    get_history_record,
    update_history_record_workflow,
)
from job_radar.web_routes.common import (
    matches_filter_value,
    normalize_optional_form_value,
    parse_sort_date,
)

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

HISTORY_OUTCOME_FILTER_OPTIONS = (
    "Closed Before Application",
    "Rejected - No Interview",
    "Rejected - After Interview",
    "Withdrawn",
    "N/A",
)

HISTORY_QUICK_ACTIONS = {
    "restore_to_tracker": {
        "label": "Restore to Active Applications",
        "status": "Applied",
        "outcome": "Pending / In Progress",
    },
}


@dataclass(frozen=True)
class HistorySummaryView:
    total: int
    applied: int
    passed: int
    withdrawn: int
    closed_before_application: int
    rejected: int


def register_history_routes(
    app: Flask,
    *,
    get_database_path: Callable[[], str],
    decision_options: tuple[str, ...],
    tracker_edit_outcome_options: tuple[str, ...],
) -> None:
    """Register application-history viewing and editing routes."""

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

        database_path = get_database_path()
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
            decision_filter_options=decision_options,
            outcome_filter_options=HISTORY_OUTCOME_FILTER_OPTIONS,
            sort_options=HISTORY_SORT_OPTIONS,
        )

    @app.get("/history/<path:import_key>/edit")
    def edit_history_record(import_key: str) -> str:
        database_path = get_database_path()
        record = get_history_record(database_path, import_key)

        if record is None:
            abort(404)

        return render_template(
            "history_edit.html",
            record=record,
            decision_options=decision_options,
            outcome_options=tracker_edit_outcome_options,
            quick_actions=HISTORY_QUICK_ACTIONS,
        )

    @app.post("/history/<path:import_key>/edit")
    def update_history_record(import_key: str):
        database_path = get_database_path()
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
        outcome = normalize_optional_form_value("outcome")
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
            source=normalize_optional_form_value("source"),
            event_date=normalize_optional_form_value("event_date"),
            status=status,
            outcome=outcome,
            recruiter_contact=normalize_optional_form_value(
                "recruiter_contact"
            ),
            notes=normalize_optional_form_value("notes"),
        )

        if result == "missing":
            abort(404)

        if result == "moved_to_tracker":
            return redirect(url_for("tracker", filter="all"))

        return redirect(url_for("history"))


def _build_history_summary(records: list) -> HistorySummaryView:
    # These counts summarize the archive itself, not only the current filtered
    # table. That keeps the page useful as a dashboard while search narrows rows.
    return HistorySummaryView(
        total=len(records),
        applied=sum(
            1
            for record in records
            if matches_filter_value(record.status, "Applied")
        ),
        passed=sum(
            1
            for record in records
            if matches_filter_value(record.status, "Passed")
        ),
        withdrawn=sum(
            1
            for record in records
            if matches_filter_value(record.status, "Withdrawn")
            or matches_filter_value(record.outcome_category, "Withdrawn")
        ),
        closed_before_application=sum(
            1
            for record in records
            if matches_filter_value(
                record.outcome_category,
                "Closed Before Application",
            )
        ),
        rejected=sum(
            1
            for record in records
            if matches_filter_value(
                record.outcome_category,
                "Rejected - No Interview",
            )
            or matches_filter_value(
                record.outcome_category,
                "Rejected - After Interview",
            )
        ),
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
            if matches_filter_value(record.status, decision_filter)
        ]

    if outcome_filter:
        filtered_records = [
            record
            for record in filtered_records
            if _matches_history_outcome_filter(record, outcome_filter)
        ]

    return filtered_records


def _matches_history_outcome_filter(record, outcome_filter: str) -> bool:
    if outcome_filter.casefold() == "rejected":
        return matches_filter_value(
            record.outcome_category,
            "Rejected - No Interview",
        ) or matches_filter_value(
            record.outcome_category,
            "Rejected - After Interview",
        )

    if outcome_filter.casefold() == "withdrawn":
        return matches_filter_value(
            record.status,
            "Withdrawn",
        ) or matches_filter_value(
            record.outcome_category,
            "Withdrawn",
        )

    return matches_filter_value(record.outcome_category, outcome_filter)


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


def _get_history_event_date_desc_sort_key(
    record,
) -> tuple[bool, int, str, str]:
    event_date = parse_sort_date(record.event_date)

    return (
        event_date is None,
        -(event_date.toordinal() if event_date else 0),
        record.company.lower(),
        record.role.lower(),
    )


def _get_history_event_date_asc_sort_key(
    record,
) -> tuple[bool, int, str, str]:
    event_date = parse_sort_date(record.event_date)

    return (
        event_date is None,
        event_date.toordinal() if event_date else 0,
        record.company.lower(),
        record.role.lower(),
    )
