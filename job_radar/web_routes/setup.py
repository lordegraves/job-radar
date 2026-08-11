"""Guide a new installation into profile setup without writing partial data."""

from collections.abc import Callable
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for

from job_radar.first_run_service import needs_first_run_setup
from job_radar.company_workspace_service import build_company_workspace
from job_radar.profile_storage import get_active_profile
from job_radar.profile_fit_service import build_profile_fit_board
from job_radar.setup_progress_service import (
    FIT,
    REVIEW,
    advance_setup,
    complete_setup,
    get_setup_progress,
    incomplete_setup_destination,
    start_setup,
)
from job_radar.setup_validation_service import validate_first_run_setup


def register_setup_routes(
    app: Flask,
    *,
    get_database_path: Callable[[], str],
    get_base_directory: Callable[[], str],
) -> None:
    """Register the first-run welcome boundary."""

    @app.get("/setup")
    def setup_welcome() -> str:
        destination = incomplete_setup_destination(get_database_path())
        if destination is not None:
            return redirect(url_for(destination, setup="1"))
        if not needs_first_run_setup(get_database_path()):
            return redirect(url_for("profile"))
        return render_template("setup_welcome.html")

    @app.post("/setup/start")
    def setup_start():
        start_setup(get_database_path())
        return redirect(url_for("new_profile_page", setup="1"))

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
        untested_sources = sum(
            company.connection_health.state == "not_tested"
            for company in workspace.companies
        )
        return render_template(
            "setup_companies.html",
            workspace=workspace,
            untested_sources=untested_sources,
        )

    @app.get("/setup/job-fit")
    def setup_job_fit() -> str:
        profile = get_active_profile(get_database_path())
        if profile is None:
            return redirect(url_for("setup_welcome"))
        managed_profile, fit_signals = build_profile_fit_board(
            get_database_path(),
            profile.profile_id,
            base_directory=get_base_directory(),
        )
        return render_template(
            "profile_fit_board.html",
            managed_profile=managed_profile,
            fit_signals=fit_signals,
            fit_error="",
            setup_mode=True,
        )

    @app.post("/setup/skip-resume")
    def setup_skip_resume():
        advance_setup(get_database_path(), FIT)
        return redirect(url_for("setup_job_fit"))

    @app.post("/setup/review")
    def setup_begin_review():
        advance_setup(get_database_path(), REVIEW)
        return redirect(url_for("setup_review"))

    @app.get("/setup/review")
    def setup_review() -> str:
        workspace = build_company_workspace(get_database_path())
        if workspace.active_profile is None:
            return redirect(url_for("setup_welcome"))
        return render_template(
            "setup_review.html",
            profile=workspace.active_profile,
            workspace=workspace,
            data_location=Path(get_database_path()).parent,
            progress=get_setup_progress(get_database_path()),
        )

    @app.post("/setup/validate")
    def setup_validate():
        result = validate_first_run_setup(get_database_path())
        flash(result.message, "success" if result.passed else "error")
        for issue in result.issues:
            flash(issue, "error")
        for company in result.companies:
            if not company.connected:
                flash(f"{company.name}: {company.message}", "error")
        return redirect(url_for("setup_review"))

    @app.post("/setup/complete")
    def setup_complete():
        try:
            complete_setup(
                get_database_path(),
                confirmation=request.form.get("confirmation", ""),
            )
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("setup_review"))
        flash("Setup complete. Junior is ready for your review.", "success")
        return redirect(url_for("index"))
