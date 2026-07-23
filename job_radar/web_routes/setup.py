"""Guide a new installation into profile setup without writing partial data."""

from collections.abc import Callable

from flask import Flask, redirect, render_template, url_for

from job_radar.first_run_service import needs_first_run_setup


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
