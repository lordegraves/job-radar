"""Serve the candidate profile page and safe resume-replacement workflow."""

from flask import Flask, redirect, render_template, request, url_for

from job_radar.config import ConfigError
from job_radar.profile_management import (
    archive_managed_profile,
    build_profile_management_view,
    create_managed_profile,
    save_managed_profile_resume,
    select_managed_profile,
    update_managed_profile_from_form,
)
from job_radar.profile_storage import ProfileStorageError
from job_radar.profile_service import (
    build_candidate_profile_view,
    save_uploaded_resume,
)


def register_profile_routes(
    app: Flask,
    *,
    settings_path: str,
    base_directory: str,
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
