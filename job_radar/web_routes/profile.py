"""Serve the candidate profile page and safe resume-replacement workflow."""

from flask import Flask, redirect, render_template, request, url_for

from job_radar.config import ConfigError
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
                settings_path,
                uploaded_file.filename,
                uploaded_file.read(),
                base_directory=base_directory,
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
