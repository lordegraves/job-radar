"""Prepare and serve normal-user settings and application information."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from flask import Flask, flash, redirect, render_template, request, session, url_for

from job_radar.application_info_service import build_application_info
from job_radar.config import load_settings
from job_radar.email_settings_service import (
    EmailSettingsError,
    load_email_settings_form,
    save_email_settings,
    test_email_connection,
)
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

    @app.get("/settings/email")
    def settings_email() -> str:
        return render_template(
            "settings_email.html",
            email_form=load_email_settings_form(settings_path),
            connection_test=session.get("email_connection_test"),
        )

    @app.post("/settings/email")
    def settings_email_save():
        try:
            save_email_settings(
                settings_path,
                enabled=request.form.get("enabled") == "yes",
                provider=request.form.get("provider", ""),
                sender=request.form.get("sender", ""),
                sender_name=request.form.get("sender_name", ""),
                recipients_text=request.form.get("recipients", ""),
                smtp_host=request.form.get("smtp_host", ""),
                smtp_port_text=request.form.get("smtp_port", ""),
                smtp_username=request.form.get("smtp_username", ""),
                smtp_tls_mode=request.form.get("smtp_tls_mode", ""),
                credential=request.form.get("credential", ""),
            )
        except EmailSettingsError as error:
            flash(str(error), "error")
            return redirect(url_for("settings_email"))
        flash("Email settings saved.", "success")
        return redirect(url_for("settings_email"))

    @app.post("/settings/email/test")
    def settings_email_test():
        try:
            result = test_email_connection(
                settings_path,
                provider=request.form.get("provider", ""),
                smtp_host=request.form.get("smtp_host", ""),
                smtp_port_text=request.form.get("smtp_port", ""),
                smtp_username=request.form.get("smtp_username", ""),
                smtp_tls_mode=request.form.get("smtp_tls_mode", ""),
                credential=request.form.get("credential", ""),
            )
        except EmailSettingsError as error:
            result = str(error)
        session["email_connection_test"] = _email_connection_status(
            request.form.get("provider", ""),
            result,
        )
        return redirect(url_for("settings_email"))


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


def _email_connection_status(provider: str, result: str) -> dict[str, str]:
    status, reason, tone = {
        "Connection successful": (
            "Connected",
            "Junior authenticated successfully.",
            "success",
        ),
        "Authentication failed": (
            "Authentication failed",
            "The username or password was rejected.",
            "error",
        ),
        "Server unreachable": (
            "Server unreachable",
            "Junior could not reach the email server.",
            "error",
        ),
        "TLS negotiation failed": (
            "TLS negotiation failed",
            "The secure connection could not be established.",
            "error",
        ),
        "Secure credential storage is unavailable": (
            "Credential unavailable",
            "The operating-system credential manager is unavailable.",
            "error",
        ),
        "Credential not configured": (
            "Not configured",
            "Enter a password or configure an approved environment variable.",
            "warning",
        ),
    }.get(result, ("Setup needs attention", result, "error"))
    tested_time = datetime.now().astimezone().strftime("%I:%M %p").lstrip("0")
    return {
        "provider": {
            "gmail": "Gmail",
            "outlook": "Outlook",
            "custom": "Custom SMTP",
        }.get(provider, "Email"),
        "status": status,
        "reason": reason,
        "tone": tone,
        "tested_at": f"Today at {tested_time}",
    }
