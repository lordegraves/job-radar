"""Guide a new installation into profile setup without writing partial data."""

from collections.abc import Callable

from flask import Flask, redirect, render_template, url_for

from job_radar.first_run_service import needs_first_run_setup
from job_radar.company_workspace_service import build_company_workspace
from job_radar.profile_storage import get_active_profile


def register_setup_routes(
    app: Flask,
    *,
    get_database_path: Callable[[], str],
) -> None:
    """Register the first-run welcome boundary."""

    @app.get("/setup")
    def setup_welcome() -> str:
        if not needs_first_run_setup(get_database_path()):
            return redirect(url_for("profile"))
        return render_template("setup_welcome.html")

    @app.get("/setup/resume")
    def setup_resume() -> str:
        profile = get_active_profile(get_database_path())
        if profile is None:
            return redirect(url_for("setup_welcome"))
        return render_template("setup_resume.html", profile=profile)

    @app.get("/setup/companies")
    def setup_companies() -> str:
        workspace = build_company_workspace(get_database_path())
        if workspace.active_profile is None:
            return redirect(url_for("setup_welcome"))
        return render_template("setup_companies.html", workspace=workspace)

    @app.get("/setup/review")
    def setup_review() -> str:
        workspace = build_company_workspace(get_database_path())
        if workspace.active_profile is None:
            return redirect(url_for("setup_welcome"))
        return render_template(
            "setup_review.html",
            profile=workspace.active_profile,
            workspace=workspace,
        )
