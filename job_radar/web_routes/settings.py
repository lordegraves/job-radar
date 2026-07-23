"""Prepare and serve normal-user settings and application information."""

from dataclasses import dataclass

from collections.abc import Callable

from flask import Flask, render_template

from job_radar.application_info_service import build_application_info
from job_radar.config import load_settings
from job_radar.email_sender import get_email_readiness
from job_radar.runtime_paths import (
    DEFAULT_COMPANY_CONFIG_PATH,
    DEFAULT_EMAIL_PREVIEW_PATH,
    DEFAULT_REPORT_PATH,
    DEFAULT_SCORING_CONFIG_PATH,
    RuntimePaths,
)


@dataclass(frozen=True)
class SettingsView:
    settings_path: str
    database_path: str
    reports_path: str
    logs_path: str
    candidate_profile_path: str | None
    report_history_policy: str
    report_replacement_behavior: str
    scan_config_path: str
    scan_settings_path: str
    scan_scoring_path: str
    scan_report_path: str
    scan_email_preview_path: str
    email_status: str


def register_settings_routes(
    app: Flask,
    *,
    settings_path: str,
    get_runtime_paths: Callable[[], RuntimePaths],
) -> None:
    """Register normal-user settings and read-only application information."""

    @app.get("/settings")
    def settings() -> str:
        settings_view = _build_settings_view(settings_path)

        return render_template(
            "settings.html",
            settings_view=settings_view,
        )

    @app.get("/settings/about")
    def settings_about() -> str:
        runtime_paths = get_runtime_paths()
        return render_template(
            "settings_about.html",
            application_info=build_application_info(
                database_path=runtime_paths.database_path,
                user_data_location=runtime_paths.base_directory,
            ),
        )


def _build_settings_view(settings_path: str) -> SettingsView:
    settings = load_settings(settings_path)
    email_readiness = get_email_readiness(settings.email)

    return SettingsView(
        settings_path=settings_path,
        database_path=settings["database_path"],
        reports_path=settings["reports_path"],
        logs_path=settings["logs_path"],
        candidate_profile_path=settings.get("candidate_profile_path"),
        report_history_policy="Latest scan only",
        report_replacement_behavior=(
            "Each successful scan replaces the previous HTML report, "
            "structured snapshot, and email preview."
        ),
        scan_config_path=DEFAULT_COMPANY_CONFIG_PATH,
        scan_settings_path=settings_path,
        scan_scoring_path=DEFAULT_SCORING_CONFIG_PATH,
        scan_report_path=DEFAULT_REPORT_PATH,
        scan_email_preview_path=DEFAULT_EMAIL_PREVIEW_PATH,
        email_status=email_readiness.message,
    )
