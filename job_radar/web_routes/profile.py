"""Serve the candidate profile page and safe resume-replacement workflow."""

from flask import Flask, jsonify, make_response, redirect, render_template, request, url_for

from job_radar.config import ConfigError
from job_radar.company_workspace_service import build_company_workspace
from job_radar.profile_management import (
    MAX_MANAGED_PROFILES,
    build_profile_management_view,
    create_managed_profile,
    delete_managed_profile,
    save_managed_profile_resume,
    save_managed_search_profile,
    select_managed_profile,
    update_managed_profile_from_form,
)
from job_radar.profile_fit import build_initial_fit_signals
from job_radar.profile_fit_service import (
    build_profile_fit_board,
    save_profile_fit_board,
)
from job_radar.profile_storage import ProfileStorageError
from job_radar.role_discovery_service import (
    list_role_suggestions,
    record_role_feedback,
    refresh_role_suggestions,
)
from job_radar.preference_reference import (
    cities_within_radius,
    suggest_locations,
    suggest_occupations,
)
from job_radar.profile_service import (
    build_candidate_profile_view,
    save_uploaded_resume,
)
from job_radar.profile_configuration_report import (
    build_profile_configuration_report,
)
from job_radar.profile_transfer_service import (
    export_profile,
    import_profile,
)
from job_radar.profile_storage import get_profile
from job_radar.scoring_preferences import (
    build_effective_scoring_preferences_view,
)
from job_radar.setup_progress_service import COMPANIES, RESUME, advance_setup


def register_profile_routes(
    app: Flask,
    *,
    settings_path: str,
    base_directory: str,
    database_path: str,
    scoring_path: str,
) -> None:
    """Register profile viewing and resume replacement routes."""

    def _profile_page_context(
        *,
        create_new: bool = False,
        profile_id: str | None = None,
    ) -> dict[str, object]:
        profile_view = build_candidate_profile_view(
            settings_path,
            base_directory=base_directory,
            profile_id=profile_id,
        )
        management_view = build_profile_management_view(
            settings_path,
            base_directory=base_directory,
        )
        active_managed_profile = next(
            (
                managed
                for managed in management_view.profiles
                if managed.profile_id
                == (profile_id or management_view.active_profile_id)
            ),
            None,
        )
        if create_new:
            active_managed_profile = None

        fit_signals = (
            build_initial_fit_signals(active_managed_profile)
            if active_managed_profile is not None
            else ()
        )
        fit_summary = {
            category: tuple(
                signal for signal in fit_signals if signal.category == category
            )
            for category in ("strong", "review", "avoid", "ignored")
        }

        saved_preferences = (
            active_managed_profile.preferences
            if active_managed_profile is not None
            else None
        )
        occupation_selections: list[dict[str, object]] = []
        location_selections: list[dict[str, object]] = []
        if saved_preferences is not None:
            occupation_selections = [
                {"value": item.value, "label": item.label}
                for item in saved_preferences.occupation_selections
            ] or [
                {"value": f"custom:{role.casefold()}", "label": role}
                for role in saved_preferences.target_roles
            ]
            location_selections = [
                {
                    "value": item.value,
                    "label": item.label,
                    "latitude": item.latitude,
                    "longitude": item.longitude,
                    "radius": item.radius_miles,
                }
                for item in saved_preferences.location_selections
            ] or [
                {
                    "value": f"legacy:{location.casefold()}",
                    "label": location,
                    "latitude": None,
                    "longitude": None,
                    "radius": 25,
                }
                for location in saved_preferences.preferred_locations
            ]

        return {
            "profile": profile_view,
            "profile_management": management_view,
            "active_managed_profile": active_managed_profile,
            "fit_summary": fit_summary,
            "has_profile": (
                active_managed_profile is not None
                or profile_view.candidate_profile_exists
            ),
            "scoring_preferences": build_effective_scoring_preferences_view(
                database_path,
                scoring_path,
            ),
            "preference_error": request.args.get(
                "preference_error", ""
            ).strip(),
            "saved_preferences": saved_preferences,
            "occupation_selections": occupation_selections,
            "location_selections": location_selections,
            "create_new": create_new,
            "profile_limit_reached": (
                len(management_view.profiles) >= MAX_MANAGED_PROFILES
            ),
            "company_workspace": build_company_workspace(database_path),
        }

    @app.get("/profile")
    def profile() -> str:
        context = _profile_page_context()
        return render_template(
            "profile.html",
            **context,
            profile_result=request.args.get("profile_result", "").strip(),
            profile_error=request.args.get("profile_error", "").strip(),
            upload_result=request.args.get("upload_result", "").strip(),
            upload_error=request.args.get("upload_error", "").strip(),
            import_company_count=request.args.get("import_company_count", "").strip(),
            import_missing_count=request.args.get("import_missing_count", "").strip(),
        )

    @app.post("/profile/export")
    def export_profile_configuration():
        profile_id = request.form.get("profile_id", "").strip()
        selected = get_profile(database_path, profile_id)
        if selected is None or selected.archived:
            return _profile_redirect(
                "error",
                "Choose an available saved profile to export.",
            )
        filename, content = export_profile(database_path, profile_id)
        response = make_response(content)
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        response.headers["Content-Disposition"] = (
            f'attachment; filename="{filename}"'
        )
        return response

    @app.post("/profile/import")
    def import_profile_configuration():
        uploaded = request.files.get("profile_file")
        if uploaded is None or not uploaded.filename:
            return _profile_redirect("error", "Choose a Junior profile file to import.")
        try:
            result = import_profile(database_path, uploaded.read())
        except (ConfigError, ProfileStorageError, ValueError) as error:
            return _profile_redirect("error", str(error))
        return redirect(
            url_for(
                "profile",
                profile_result="imported",
                import_company_count=result.imported_company_count,
                import_missing_count=len(result.unavailable_companies),
            )
        )

    @app.get("/profile/configuration-report")
    def profile_configuration_report_page():
        report = build_profile_configuration_report(
            database_path,
            scoring_path,
        )
        if report is None:
            return _profile_redirect(
                "error",
                "Create or select a profile before generating its configuration report.",
            )
        return render_template(
            "profile_configuration_report.html",
            report=report,
        )

    @app.get("/profile/configuration-report/download")
    def profile_configuration_report_download():
        report = build_profile_configuration_report(
            database_path,
            scoring_path,
        )
        if report is None:
            return _profile_redirect(
                "error",
                "Create or select a profile before generating its configuration report.",
            )
        response = make_response(
            render_template(
                "profile_configuration_report_download.html",
                report=report,
            )
        )
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        response.headers["Content-Disposition"] = (
            'attachment; filename="junior-profile-configuration-report.html"'
        )
        return response

    @app.get("/profile/new")
    def new_profile_page() -> str:
        management_view = build_profile_management_view(
            settings_path,
            base_directory=base_directory,
        )
        if len(management_view.profiles) >= MAX_MANAGED_PROFILES:
            return _profile_redirect(
                "error",
                "junior supports up to five profiles. Delete a profile before creating another one.",
            )
        return render_template(
            "profile_form.html",
            **_profile_page_context(create_new=True),
            setup_mode=request.args.get("setup") == "1",
        )

    @app.get("/profile/<profile_id>/edit")
    def edit_profile_page(profile_id: str):
        context = _profile_page_context(profile_id=profile_id)
        selected = context["active_managed_profile"]
        if selected is None or selected.archived:
            return _profile_redirect(
                "error", "The selected profile is not available for editing."
            )
        return render_template("profile_form.html", **context)

    @app.get("/profile/<profile_id>/fit")
    def profile_fit_board_page(profile_id: str):
        try:
            managed_profile, fit_signals = build_profile_fit_board(
                database_path,
                profile_id,
            )
        except (ConfigError, ProfileStorageError, ValueError) as error:
            return _profile_redirect("error", str(error))

        return render_template(
            "profile_fit_board.html",
            managed_profile=managed_profile,
            fit_signals=fit_signals,
            fit_error=request.args.get("fit_error", "").strip(),
        )

    @app.get("/profile/<profile_id>/roles")
    def role_discovery_page(profile_id: str):
        management = build_profile_management_view(
            settings_path,
            base_directory=base_directory,
        )
        if management.active_profile_id != profile_id:
            return _profile_redirect(
                "error",
                "Select this profile before reviewing its role suggestions.",
            )
        selected = next(
            (
                profile
                for profile in management.profiles
                if profile.profile_id == profile_id and not profile.archived
            ),
            None,
        )
        if selected is None:
            return _profile_redirect(
                "error", "The selected profile is not available."
            )
        return render_template(
            "role_discovery.html",
            managed_profile=selected,
            suggestions=list_role_suggestions(
                database_path,
                profile_id=profile_id,
            ),
            role_result=request.args.get("role_result", "").strip(),
            role_error=request.args.get("role_error", "").strip(),
        )

    @app.post("/profile/<profile_id>/roles/refresh")
    def refresh_role_discovery(profile_id: str):
        management = build_profile_management_view(
            settings_path,
            base_directory=base_directory,
        )
        if management.active_profile_id != profile_id:
            return _profile_redirect(
                "error",
                "Select this profile before refreshing role suggestions.",
            )
        try:
            refresh_role_suggestions(
                database_path,
                profile_id=profile_id,
                base_directory=base_directory,
            )
        except (ConfigError, ProfileStorageError, ValueError) as error:
            return redirect(
                url_for(
                    "role_discovery_page",
                    profile_id=profile_id,
                    role_error=str(error),
                )
            )
        return redirect(
            url_for(
                "role_discovery_page",
                profile_id=profile_id,
                role_result="refreshed",
            )
        )

    @app.post("/profile/<profile_id>/roles/<int:suggestion_id>/feedback")
    def save_role_discovery_feedback(profile_id: str, suggestion_id: int):
        management = build_profile_management_view(
            settings_path,
            base_directory=base_directory,
        )
        if management.active_profile_id != profile_id:
            return _profile_redirect(
                "error",
                "Select this profile before changing role suggestions.",
            )
        try:
            record_role_feedback(
                database_path,
                profile_id=profile_id,
                suggestion_id=suggestion_id,
                feedback_state=request.form.get("feedback_state", ""),
            )
        except (ConfigError, ProfileStorageError, ValueError) as error:
            return redirect(
                url_for(
                    "role_discovery_page",
                    profile_id=profile_id,
                    role_error=str(error),
                )
            )
        return redirect(
            url_for(
                "role_discovery_page",
                profile_id=profile_id,
                role_result="feedback_saved",
            )
        )

    @app.get("/profile/legacy/edit")
    def edit_legacy_profile_page():
        context = _profile_page_context()
        if (
            context["active_managed_profile"] is not None
            or not context["profile"].candidate_profile_exists
        ):
            return _profile_redirect(
                "error", "The earlier file-based profile is not active."
            )
        return render_template("legacy_profile_form.html", **context)

    @app.get("/preferences")
    def preferences():
        """Keep older bookmarks working after preferences moved into Profile."""

        return redirect(
            url_for(
                "profile",
                profile_result=request.args.get("profile_result") or None,
                preference_error=request.args.get("preference_error") or None,
            )
        )

    @app.post("/preferences")
    def save_preferences():
        try:
            saved_profile, created = save_managed_search_profile(
                settings_path,
                display_name=request.form.get("display_name", ""),
                create_new=request.form.get("profile_mode", "") == "create",
                profile_id=request.form.get("profile_id", "").strip() or None,
                occupation_selections_json=request.form.get(
                    "occupation_selections_json", "[]"
                ),
                location_selections_json=request.form.get(
                    "location_selections_json", "[]"
                ),
                seniority_levels=request.form.getlist("responsibility-level"),
                employment_types=request.form.getlist("employment-type"),
                work_arrangements=request.form.getlist("workplace-arrangement"),
                schedule_preference=request.form.get("schedule_preference", ""),
                on_call_preference=request.form.get(
                    "on_call_preference", "Review each job"
                ),
                clearance_preference=request.form.get(
                    "clearance_preference", "Review each job"
                ),
                compensation_floor_usd=request.form.get(
                    "compensation_floor_usd", ""
                ),
                travel_percentage=request.form.get("travel_percentage", ""),
                exclusions=request.form.get("exclusions", ""),
                include_strong_location_outliers=(
                    request.form.get("include_strong_location_outliers") == "1"
                ),
                base_directory=base_directory,
            )
        except (ConfigError, ProfileStorageError, ValueError) as error:
            create_mode = request.form.get("profile_mode", "") == "create"
            if create_mode:
                return redirect(
                    url_for("new_profile_page", preference_error=str(error))
                )
            requested_profile_id = request.form.get("profile_id", "").strip()
            if requested_profile_id:
                return redirect(
                    url_for(
                        "edit_profile_page",
                        profile_id=requested_profile_id,
                        preference_error=str(error),
                    )
                )
            return redirect(
                url_for(
                    "profile",
                    preference_error=str(error),
                )
            )
        if created:
            if request.form.get("setup_mode") == "1":
                advance_setup(
                    database_path,
                    RESUME,
                    profile_id=saved_profile.profile_id,
                )
                return redirect(
                    url_for(
                        "setup_resume",
                        profile_id=saved_profile.profile_id,
                    )
                )
            return redirect(url_for("profile", profile_result="created"))
        return redirect(url_for("profile", profile_result="preferences_saved"))

    @app.get("/preferences/occupation-suggestions")
    def occupation_suggestions():
        return jsonify(suggest_occupations(request.args.get("q", "")))

    @app.get("/preferences/location-suggestions")
    def location_suggestions():
        return jsonify(suggest_locations(request.args.get("q", "")))

    @app.get("/preferences/location-radius")
    def location_radius():
        try:
            result = cities_within_radius(
                float(request.args.get("latitude", "")),
                float(request.args.get("longitude", "")),
                int(request.args.get("miles", "")),
            )
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify(result)

    @app.post("/profile/create")
    def create_profile_route():
        try:
            create_managed_profile(
                settings_path,
                request.form.get("display_name", ""),
                base_directory=base_directory,
            )
        except (ConfigError, ProfileStorageError, ValueError) as error:
            return _profile_redirect("error", str(error))
        return _profile_redirect("created")

    @app.post("/profile/select")
    def select_profile_route():
        profile_id = request.form.get("profile_id", "").strip() or None
        try:
            select_managed_profile(
                settings_path,
                profile_id,
                base_directory=base_directory,
            )
        except (ConfigError, ProfileStorageError, ValueError) as error:
            return _profile_redirect("error", str(error))
        return _profile_redirect("selected")

    @app.post("/profile/<profile_id>/edit")
    def edit_profile_route(profile_id: str):
        try:
            update_managed_profile_from_form(
                settings_path,
                profile_id,
                request.form.to_dict(),
                base_directory=base_directory,
            )
        except (ConfigError, ProfileStorageError, ValueError) as error:
            return _profile_redirect("error", str(error))
        return _profile_redirect("updated")

    @app.post("/profile/<profile_id>/fit")
    def save_profile_fit_board_route(profile_id: str):
        try:
            save_profile_fit_board(
                database_path,
                scoring_path,
                profile_id,
                request.form.get("fit_signals_json", "[]"),
            )
        except (ConfigError, ProfileStorageError, ValueError) as error:
            return redirect(
                url_for(
                    "profile_fit_board_page",
                    profile_id=profile_id,
                    fit_error=str(error),
                )
            )

        return redirect(url_for("profile", profile_result="fit_preferences_saved"))

    @app.post("/profile/delete")
    def delete_profile_route():
        profile_id = request.form.get("profile_id", "").strip()
        try:
            delete_managed_profile(
                settings_path,
                profile_id,
                base_directory=base_directory,
            )
        except (ConfigError, ProfileStorageError, ValueError) as error:
            return _profile_redirect("error", str(error))
        return _profile_redirect("deleted")

    @app.post("/profile/<profile_id>/resume")
    def upload_managed_resume(profile_id: str):
        return _save_resume_upload(profile_id=profile_id)

    @app.post("/profile/resume")
    def upload_resume():
        return _save_resume_upload()

    def _save_resume_upload(*, profile_id: str | None = None):
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
            management_view = build_profile_management_view(
                settings_path,
                base_directory=base_directory,
            )
            if profile_id is not None or management_view.active_profile_id is not None:
                save_managed_profile_resume(
                    settings_path,
                    uploaded_file.filename,
                    uploaded_file.read(),
                    profile_id=profile_id,
                    base_directory=base_directory,
                )
            else:
                save_uploaded_resume(
                    settings_path,
                    uploaded_file.filename,
                    uploaded_file.read(),
                    base_directory=base_directory,
                )
        except (ConfigError, ProfileStorageError, ValueError) as error:
            return redirect(
                url_for(
                    "profile",
                    upload_result="error",
                    upload_error=str(error),
                )
            )

        if request.form.get("setup_mode") == "1":
            advance_setup(
                database_path,
                COMPANIES,
                profile_id=profile_id,
            )
            return redirect(url_for("setup_companies"))
        return redirect(url_for("profile", upload_result="success"))

    def _profile_redirect(result: str, error: str = ""):
        return redirect(
            url_for(
                "profile",
                profile_result=result,
                profile_error=error,
            )
        )
