"""Serve the candidate profile page and safe resume-replacement workflow."""

from flask import Flask, jsonify, redirect, render_template, request, url_for

from job_radar.config import ConfigError
from job_radar.profile_management import (
    archive_managed_profile,
    build_profile_management_view,
    create_managed_profile,
    save_managed_profile_resume,
    select_managed_profile,
    update_managed_profile_from_form,
    update_managed_search_preferences,
)
from job_radar.profile_storage import ProfileStorageError
from job_radar.preference_reference import (
    cities_within_radius,
    suggest_locations,
    suggest_occupations,
)
from job_radar.profile_service import (
    build_candidate_profile_view,
    save_uploaded_resume,
)
from job_radar.scoring_preferences import build_scoring_preferences_view


def register_profile_routes(
    app: Flask,
    *,
    settings_path: str,
    base_directory: str,
    scoring_path: str,
) -> None:
    """Register profile viewing and resume replacement routes."""

    @app.get("/profile")
    def profile() -> str:
        profile_view = build_candidate_profile_view(
            settings_path,
            base_directory=base_directory,
        )
        management_view = build_profile_management_view(
            settings_path,
            base_directory=base_directory,
        )
        return render_template(
            "profile.html",
            profile=profile_view,
            profile_management=management_view,
            profile_result=request.args.get("profile_result", "").strip(),
            profile_error=request.args.get("profile_error", "").strip(),
            upload_result=request.args.get("upload_result", "").strip(),
            upload_error=request.args.get("upload_error", "").strip(),
        )

    @app.get("/preferences")
    def preferences() -> str:
        profile_view = build_candidate_profile_view(
            settings_path,
            base_directory=base_directory,
        )
        management_view = build_profile_management_view(
            settings_path,
            base_directory=base_directory,
        )
        active_managed_profile = next(
            (
                managed
                for managed in management_view.profiles
                if managed.profile_id == management_view.active_profile_id
            ),
            None,
        )
        saved_preferences = (
            active_managed_profile.preferences
            if active_managed_profile is not None
            else None
        )
        occupation_selections = []
        location_selections = []
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

        return render_template(
            "preferences.html",
            profile=profile_view,
            active_managed_profile=active_managed_profile,
            scoring_preferences=build_scoring_preferences_view(scoring_path),
            preference_result=request.args.get("preference_result", "").strip(),
            preference_error=request.args.get("preference_error", "").strip(),
            saved_preferences=saved_preferences,
            occupation_selections=occupation_selections,
            location_selections=location_selections,
        )

    @app.post("/preferences")
    def save_preferences():
        try:
            update_managed_search_preferences(
                settings_path,
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
                compensation_floor_usd=request.form.get(
                    "compensation_floor_usd", ""
                ),
                travel_percentage=request.form.get("travel_percentage", ""),
                base_directory=base_directory,
            )
        except (ConfigError, ProfileStorageError, ValueError) as error:
            return redirect(
                url_for(
                    "preferences",
                    preference_result="error",
                    preference_error=str(error),
                )
            )
        return redirect(url_for("preferences", preference_result="saved"))

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

    @app.post("/profile/<profile_id>/archive")
    def archive_profile_route(profile_id: str):
        try:
            archive_managed_profile(
                settings_path,
                profile_id,
                archived=True,
                base_directory=base_directory,
            )
        except (ConfigError, ProfileStorageError, ValueError) as error:
            return _profile_redirect("error", str(error))
        return _profile_redirect("archived")

    @app.post("/profile/<profile_id>/restore")
    def restore_profile_route(profile_id: str):
        try:
            archive_managed_profile(
                settings_path,
                profile_id,
                archived=False,
                base_directory=base_directory,
            )
        except (ConfigError, ProfileStorageError, ValueError) as error:
            return _profile_redirect("error", str(error))
        return _profile_redirect("restored")

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
            management_view = build_profile_management_view(
                settings_path,
                base_directory=base_directory,
            )
            if management_view.active_profile_id is not None:
                save_managed_profile_resume(
                    settings_path,
                    uploaded_file.filename,
                    uploaded_file.read(),
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

        return redirect(url_for("profile", upload_result="success"))

    def _profile_redirect(result: str, error: str = ""):
        return redirect(
            url_for(
                "profile",
                profile_result=result,
                profile_error=error,
            )
        )
