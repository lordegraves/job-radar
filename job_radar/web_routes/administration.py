"""Serve the session-scoped Administration access boundary."""

from collections.abc import Callable

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from job_radar.admin_access import (
    administration_required,
    is_admin_unlocked,
    lock_admin_session,
    safe_local_path,
    unlock_admin_session,
)
from job_radar.config import SUPPORTED_SOURCE_TYPES
from job_radar.employer_admin_service import (
    EmployerAdminError,
    create_employer,
    form_source_config,
    get_admin_employer,
    list_admin_employers,
    list_employer_audit,
    set_employer_lifecycle,
    source_fields,
    update_employer,
    validate_employer,
)


def register_administration_routes(
    app: Flask,
    *,
    get_database_path: Callable[[], str],
) -> None:
    """Register the guarded Administration shell and employer catalog."""

    @app.context_processor
    def administration_context() -> dict[str, bool]:
        return {"admin_mode_active": is_admin_unlocked()}

    @app.get("/administration")
    @administration_required
    def administration() -> str:
        return render_template("administration/index.html")

    @app.get("/administration/employers")
    @administration_required
    def administration_employers() -> str:
        filters = {
            "search": request.args.get("search", ""),
            "source_type": request.args.get("source_type", ""),
            "configuration": request.args.get("configuration", ""),
            "availability": request.args.get("availability", ""),
            "assignment": request.args.get("assignment", ""),
            "validation": request.args.get("validation", ""),
        }
        return render_template(
            "administration/employers.html",
            employers=list_admin_employers(get_database_path(), **filters),
            source_types=sorted(SUPPORTED_SOURCE_TYPES),
            filters=filters,
        )

    @app.get("/administration/employers/new")
    @administration_required
    def administration_employer_new() -> str:
        selected_source = request.args.get("source_type", "greenhouse")
        if selected_source not in SUPPORTED_SOURCE_TYPES:
            selected_source = "greenhouse"
        return render_template(
            "administration/employer_form.html",
            employer_record=None,
            source_types=sorted(SUPPORTED_SOURCE_TYPES),
            selected_source=selected_source,
            fields=source_fields(selected_source),
            field_values={},
            form_action=url_for("administration_employer_new_submit"),
        )

    @app.post("/administration/employers/new")
    @administration_required
    def administration_employer_new_submit():
        source_type = request.form.get("source_type", "")
        try:
            record = create_employer(
                get_database_path(),
                name=request.form.get("name", ""),
                source_type=source_type,
                source_config=dict(request.form),
                notes=request.form.get("notes", ""),
            )
        except EmployerAdminError as error:
            flash(str(error), "error")
            return redirect(
                url_for(
                    "administration_employer_new",
                    source_type=source_type,
                )
            )
        flash("Employer created. Validate it before enabling it.", "success")
        return redirect(
            url_for(
                "administration_employer_detail",
                employer_id=record.employer.employer_id,
            )
        )

    @app.get("/administration/employers/<employer_id>")
    @administration_required
    def administration_employer_detail(employer_id: str) -> str:
        record = get_admin_employer(get_database_path(), employer_id)
        if record is None:
            return "Employer not found.", 404
        return render_template(
            "administration/employer_detail.html",
            record=record,
            audit=list_employer_audit(get_database_path(), employer_id),
        )

    @app.get("/administration/employers/<employer_id>/edit")
    @administration_required
    def administration_employer_edit(employer_id: str) -> str:
        record = get_admin_employer(get_database_path(), employer_id)
        if record is None:
            return "Employer not found.", 404
        return render_template(
            "administration/employer_form.html",
            employer_record=record,
            source_types=sorted(SUPPORTED_SOURCE_TYPES),
            selected_source=record.employer.source_type,
            fields=source_fields(record.employer.source_type),
            field_values=form_source_config(record.employer),
            form_action=url_for(
                "administration_employer_edit_submit",
                employer_id=employer_id,
            ),
        )

    @app.post("/administration/employers/<employer_id>/edit")
    @administration_required
    def administration_employer_edit_submit(employer_id: str):
        try:
            update_employer(
                get_database_path(),
                employer_id,
                name=request.form.get("name", ""),
                source_type=request.form.get("source_type", ""),
                source_config=dict(request.form),
                notes=request.form.get("notes", ""),
            )
        except EmployerAdminError as error:
            flash(str(error), "error")
            return redirect(
                url_for(
                    "administration_employer_edit",
                    employer_id=employer_id,
                )
            )
        flash("Employer settings saved. Validate them before enabling.", "success")
        return redirect(
            url_for(
                "administration_employer_detail",
                employer_id=employer_id,
            )
        )

    @app.post("/administration/employers/<employer_id>/validate")
    @administration_required
    def administration_employer_validate(employer_id: str):
        try:
            record = validate_employer(get_database_path(), employer_id)
            message = (
                "Validation passed."
                if record.validation_state == "valid"
                else "Validation found setup issues."
            )
            flash(message, "success" if record.validation_state == "valid" else "error")
        except EmployerAdminError as error:
            flash(str(error), "error")
        return redirect(
            url_for("administration_employer_detail", employer_id=employer_id)
        )

    def _lifecycle_response(employer_id: str, operation: str):
        try:
            record = set_employer_lifecycle(
                get_database_path(), employer_id, operation
            )
            flash(
                f"{record.employer.name} is now "
                f"{record.availability_label.lower()}.",
                "success",
            )
        except EmployerAdminError as error:
            flash(str(error), "error")
        return redirect(
            url_for("administration_employer_detail", employer_id=employer_id)
        )

    @app.post("/administration/employers/<employer_id>/disable")
    @administration_required
    def administration_employer_disable(employer_id: str):
        return _lifecycle_response(employer_id, "disable")

    @app.post("/administration/employers/<employer_id>/enable")
    @administration_required
    def administration_employer_enable(employer_id: str):
        return _lifecycle_response(employer_id, "enable")

    @app.post("/administration/employers/<employer_id>/retire")
    @administration_required
    def administration_employer_retire(employer_id: str):
        return _lifecycle_response(employer_id, "retire")

    @app.get("/administration/unlock")
    def administration_unlock() -> str:
        next_path = safe_local_path(request.args.get("next"))
        if is_admin_unlocked():
            return redirect(next_path or url_for("administration"))

        return render_template(
            "administration/unlock.html",
            next_path=next_path or "",
            unlock_error=request.args.get("error") == "invalid",
        )

    @app.post("/administration/unlock")
    def administration_unlock_submit():
        next_path = safe_local_path(request.form.get("next"))
        if request.form.get("confirmation", "").strip() != "ADMIN":
            return redirect(
                url_for(
                    "administration_unlock",
                    next=next_path,
                    error="invalid",
                )
            )

        unlock_admin_session()
        return redirect(next_path or url_for("administration"))

    @app.post("/administration/lock")
    def administration_lock():
        lock_admin_session()
        return redirect(safe_local_path(request.form.get("next")) or url_for("index"))
