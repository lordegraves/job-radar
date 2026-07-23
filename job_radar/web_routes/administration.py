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
    list_employer_profile_assignments,
    permanently_delete_employer,
    set_employer_lifecycle,
    set_employer_profile_assignment,
    source_fields,
    update_employer,
    validate_employer,
)
from job_radar.employer_connection_service import (
    EmployerConnectionError,
    get_employer_connection_health,
    test_employer_connection,
)
from job_radar.employer_review_service import (
    EmployerReviewError,
    PENDING,
    REVIEW_STATUSES,
    assign_resolved_employer,
    get_review_request,
    list_review_audit,
    list_review_requests,
    mark_configured_new,
    mark_review_status,
    resolve_to_existing_employer,
)
from job_radar.employer_storage import list_employer_sources
from job_radar.profile_storage import list_profiles
from job_radar.recommendation_admin_service import (
    ELIGIBILITY_OPTIONS,
    RecommendationAdminError,
    list_recommendation_audit,
    load_recommendation_diagnostic,
    load_recommendation_metadata,
    rebuild_recommendations,
    reset_recommendation_feedback,
    update_recommendation_metadata,
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

    @app.get("/administration/recommendations")
    @administration_required
    def administration_recommendations() -> str:
        employers = list_employer_sources(get_database_path())
        profiles = list_profiles(get_database_path())
        employer_id = request.args.get("employer_id", "")
        profile_id = request.args.get("profile_id", "")
        employer_ids = {item.employer_id for item in employers}
        profile_ids = {item.profile_id for item in profiles}
        if employer_id not in employer_ids:
            employer_id = employers[0].employer_id if employers else ""
        if profile_id not in profile_ids:
            profile_id = profiles[0].profile_id if profiles else ""
        return render_template(
            "administration/recommendations.html",
            employers=employers,
            profiles=profiles,
            employer_id=employer_id,
            profile_id=profile_id,
            metadata=(
                load_recommendation_metadata(
                    get_database_path(), employer_id
                )
                if employer_id
                else None
            ),
            diagnostic=(
                load_recommendation_diagnostic(
                    get_database_path(), profile_id, employer_id
                )
                if employer_id and profile_id
                else None
            ),
            audit=(
                list_recommendation_audit(
                    get_database_path(), employer_id
                )
                if employer_id
                else ()
            ),
            eligibility_options=ELIGIBILITY_OPTIONS,
        )

    def _recommendation_redirect(employer_id: str, profile_id: str):
        return redirect(
            url_for(
                "administration_recommendations",
                employer_id=employer_id,
                profile_id=profile_id,
            )
        )

    @app.post("/administration/recommendations/metadata")
    @administration_required
    def administration_recommendation_metadata():
        employer_id = request.form.get("employer_id", "")
        profile_id = request.form.get("profile_id", "")
        try:
            update_recommendation_metadata(
                get_database_path(),
                employer_id,
                aliases=request.form.get("aliases", ""),
                industries=request.form.get("industries", ""),
                occupation_families=request.form.get(
                    "occupation_families", ""
                ),
                employer_type=request.form.get("employer_type", ""),
                geographic_presence=request.form.get(
                    "geographic_presence", ""
                ),
                remote_hiring_metadata=request.form.get(
                    "remote_hiring_metadata", ""
                ),
                eligibility=request.form.get("eligibility", ""),
            )
            flash("Recommendation metadata saved.", "success")
        except RecommendationAdminError as error:
            flash(str(error), "error")
        return _recommendation_redirect(employer_id, profile_id)

    @app.post("/administration/recommendations/rebuild")
    @administration_required
    def administration_recommendation_rebuild():
        employer_id = request.form.get("employer_id", "")
        profile_id = request.form.get("profile_id", "")
        scope = request.form.get("scope", "")
        try:
            count = rebuild_recommendations(
                get_database_path(),
                profile_id=profile_id if scope == "profile" else None,
                employer_id=employer_id if scope == "employer" else None,
                all_profiles_confirmation=request.form.get(
                    "confirmation", ""
                ),
            )
            flash(
                f"Recommendation rebuild completed for {count} profile(s).",
                "success",
            )
        except RecommendationAdminError as error:
            flash(str(error), "error")
        return _recommendation_redirect(employer_id, profile_id)

    @app.post("/administration/recommendations/reset-feedback")
    @administration_required
    def administration_recommendation_reset_feedback():
        employer_id = request.form.get("employer_id", "")
        profile_id = request.form.get("profile_id", "")
        try:
            reset_recommendation_feedback(
                get_database_path(),
                profile_id,
                employer_id,
                confirmation=request.form.get("confirmation", ""),
            )
            flash("Recommendation feedback reset for this profile only.", "success")
        except RecommendationAdminError as error:
            flash(str(error), "error")
        return _recommendation_redirect(employer_id, profile_id)

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
            field_values={
                "careers_url": request.args.get("careers_url", ""),
            },
            form_action=url_for("administration_employer_new_submit"),
            prefill_name=request.args.get("name", ""),
            prefill_careers_url=request.args.get("careers_url", ""),
            review_request_id=request.args.get("review_request_id", ""),
        )

    @app.post("/administration/employers/new")
    @administration_required
    def administration_employer_new_submit():
        source_type = request.form.get("source_type", "")
        review_request_id = request.form.get("review_request_id", "").strip()
        if review_request_id:
            review = get_review_request(get_database_path(), review_request_id)
            if review is None or review.status != PENDING:
                flash("That review request is no longer pending.", "error")
                return redirect(url_for("administration_employer_reviews"))
        try:
            record = create_employer(
                get_database_path(),
                name=request.form.get("name", ""),
                source_type=source_type,
                source_config=dict(request.form),
                notes=request.form.get("notes", ""),
            )
            if review_request_id:
                mark_configured_new(
                    get_database_path(),
                    review_request_id,
                    record.employer.employer_id,
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
            connection_health=get_employer_connection_health(
                get_database_path(), employer_id
            ),
            profile_assignments=list_employer_profile_assignments(
                get_database_path(), employer_id
            ),
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
            prefill_name="",
            prefill_careers_url="",
            review_request_id="",
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

    @app.post("/administration/employers/<employer_id>/test-connection")
    @administration_required
    def administration_employer_test_connection(employer_id: str):
        try:
            health = test_employer_connection(
                get_database_path(), employer_id
            )
            flash(
                health.message or "Connection test completed.",
                "success" if health.state == "success" else "error",
            )
        except EmployerConnectionError as error:
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

    @app.post("/administration/employers/<employer_id>/profiles/<profile_id>")
    @administration_required
    def administration_employer_profile_assignment(
        employer_id: str,
        profile_id: str,
    ):
        operation = request.form.get("operation", "")
        try:
            if operation not in {"assign", "remove"}:
                raise EmployerAdminError("Choose Assign or Remove.")
            assigned = operation == "assign"
            changed = set_employer_profile_assignment(
                get_database_path(),
                employer_id,
                profile_id,
                assigned=assigned,
            )
            flash(
                (
                    "Employer assigned to that profile."
                    if assigned
                    else "Employer removed from that profile."
                )
                if changed
                else "That profile assignment was already up to date.",
                "success",
            )
        except EmployerAdminError as error:
            flash(str(error), "error")
        return redirect(
            url_for("administration_employer_detail", employer_id=employer_id)
        )

    @app.post("/administration/employers/<employer_id>/delete")
    @administration_required
    def administration_employer_delete(employer_id: str):
        try:
            permanently_delete_employer(
                get_database_path(),
                employer_id,
                confirmation=request.form.get("confirmation", ""),
            )
        except EmployerAdminError as error:
            flash(str(error), "error")
            return redirect(
                url_for(
                    "administration_employer_detail",
                    employer_id=employer_id,
                )
            )
        flash("Unused employer permanently deleted.", "success")
        return redirect(url_for("administration_employers"))

    @app.get("/administration/employer-reviews")
    @administration_required
    def administration_employer_reviews() -> str:
        status = request.args.get("status", PENDING)
        if status not in REVIEW_STATUSES and status:
            status = PENDING
        return render_template(
            "administration/employer_reviews.html",
            reviews=list_review_requests(get_database_path(), status=status),
            selected_status=status,
            statuses=REVIEW_STATUSES,
        )

    @app.get("/administration/employer-reviews/<request_id>")
    @administration_required
    def administration_employer_review_detail(request_id: str) -> str:
        review = get_review_request(get_database_path(), request_id)
        if review is None:
            return "Employer review request not found.", 404
        return render_template(
            "administration/employer_review_detail.html",
            review=review,
            employers=list_employer_sources(get_database_path()),
            audit=list_review_audit(get_database_path(), request_id),
        )

    @app.post("/administration/employer-reviews/<request_id>/match")
    @administration_required
    def administration_employer_review_match(request_id: str):
        try:
            resolve_to_existing_employer(
                get_database_path(),
                request_id,
                request.form.get("employer_id", ""),
                assign_to_profile=request.form.get("assign_to_profile") == "yes",
            )
            flash("Review matched to the existing employer.", "success")
        except EmployerReviewError as error:
            flash(str(error), "error")
        return redirect(
            url_for(
                "administration_employer_review_detail",
                request_id=request_id,
            )
        )

    @app.post("/administration/employer-reviews/<request_id>/status")
    @administration_required
    def administration_employer_review_status(request_id: str):
        try:
            mark_review_status(
                get_database_path(),
                request_id,
                request.form.get("status", ""),
            )
            flash("Review status updated.", "success")
        except EmployerReviewError as error:
            flash(str(error), "error")
        return redirect(
            url_for(
                "administration_employer_review_detail",
                request_id=request_id,
            )
        )

    @app.post("/administration/employer-reviews/<request_id>/assign")
    @administration_required
    def administration_employer_review_assign(request_id: str):
        try:
            created = assign_resolved_employer(
                get_database_path(),
                request_id,
            )
            flash(
                (
                    "Employer assigned to the requesting profile."
                    if created
                    else "The employer is already assigned to that profile."
                ),
                "success",
            )
        except EmployerReviewError as error:
            flash(str(error), "error")
        return redirect(
            url_for(
                "administration_employer_review_detail",
                request_id=request_id,
            )
        )

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
