"""Prepare and serve normal-user settings and application information."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from flask import (
    Flask,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from job_radar import __build__, __version__
from job_radar.build_info import RELEASE_LABEL, RELEASE_TAG
from job_radar.application_info_service import build_application_info
from job_radar.collector_catalog import list_collector_capabilities
from job_radar.company_discovery_settings_service import (
    CompanyDiscoverySettingsError,
    load_company_discovery_settings_form,
    save_company_discovery_settings,
)
from job_radar.config import load_settings
from job_radar.diagnostic_service import build_diagnostics_view
from job_radar.diagnostic_log_service import (
    DiagnosticLogError,
    build_support_summary,
    get_diagnostic_log_download,
    list_diagnostic_logs,
    open_data_directory,
    read_diagnostic_log,
)
from job_radar.email_settings_service import (
    EmailSettingsError,
    load_email_settings_form,
    save_email_settings,
    test_email_connection,
)
from job_radar.email_sender import get_email_readiness
from job_radar.employer_connection_service import test_employer_connection
from job_radar.runtime_paths import (
    DEFAULT_COMPANY_CONFIG_PATH,
    DEFAULT_EMAIL_PREVIEW_PATH,
    DEFAULT_REPORT_PATH,
    DEFAULT_SCORING_CONFIG_PATH,
    RuntimePaths,
)
from job_radar.retention_settings_service import (
    RetentionSettingsError,
    load_retention_settings_form,
    save_retention_settings,
)
from job_radar.schedule_service import (
    ScheduleError,
    build_schedule_view,
    save_scan_schedule,
)
from job_radar.scheduler_integration import (
    SchedulerIntegrationError,
    apply_scheduler,
    disable_scheduler,
    inspect_scheduler,
    remove_scheduler,
)
from job_radar.source_health_service import (
    build_latest_scan_warnings,
    build_source_health_items,
)
from job_radar.source_test_runner import SourceTestRunner
from job_radar.update_check_service import check_for_update


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
    source_test_runner = SourceTestRunner(
        lambda employer_id: test_employer_connection(
            get_runtime_paths().database_path,
            employer_id,
        )
    )

    @app.get("/settings")
    def settings() -> str:
        settings_view = _build_settings_view(settings_path)
        runtime_paths = get_runtime_paths()

        return render_template(
            "settings.html",
            settings_view=settings_view,
            application_info=build_application_info(
                database_path=runtime_paths.database_path,
                user_data_location=runtime_paths.user_data_directory,
            ),
            update_check=session.pop("update_check", None),
        )

    @app.post("/settings/shutdown")
    def settings_shutdown():
        shutdown_event = current_app.config.get(
            "JOB_RADAR_DESKTOP_SHUTDOWN_EVENT"
        )
        if shutdown_event is None:
            flash(
                "Exit Junior is available from the desktop launcher only.",
                "error",
            )
            return redirect(url_for("settings"))
        shutdown_event.set()
        return render_template("shutdown.html")

    @app.get("/settings/about")
    def settings_about():
        """Keep old bookmarks working after About moved onto Settings."""

        return redirect(url_for("settings"))

    @app.get("/settings/job-platforms")
    def settings_job_platforms() -> str:
        return render_template(
            "settings_job_platforms.html",
            capabilities=list_collector_capabilities(),
        )

    @app.get("/settings/diagnostics/sources")
    def settings_source_health() -> str:
        runtime_paths = get_runtime_paths()
        return render_template(
            "settings_source_health.html",
            sources=build_source_health_items(runtime_paths.database_path),
            test_status=source_test_runner.status(),
        )

    @app.post("/settings/diagnostics/sources/test")
    def settings_source_health_test():
        runtime_paths = get_runtime_paths()
        available = {
            item.employer_id: item
            for item in build_source_health_items(runtime_paths.database_path)
        }
        requested = request.form.getlist("employer_id")
        if request.form.get("test_scope") == "untested":
            requested = [
                item.employer_id
                for item in available.values()
                if item.enabled and item.state == "not_tested"
            ]
        selected = [item for item in requested if item in available]
        if not selected:
            flash("Select at least one company source to test.", "error")
        elif source_test_runner.start(selected):
            flash(
                f"Testing {len(selected)} company source(s) in the background.",
                "success",
            )
        else:
            flash("A company-source test is already running.", "error")
        return redirect(url_for("settings_source_health"))

    @app.get("/settings/diagnostics/sources/status")
    def settings_source_health_status():
        return jsonify(source_test_runner.status())

    @app.get("/settings/diagnostics/latest-scan")
    def settings_scan_diagnostics() -> str:
        runtime_paths = get_runtime_paths()
        return render_template(
            "settings_scan_diagnostics.html",
            warnings=build_latest_scan_warnings(runtime_paths.database_path),
        )

    @app.get("/settings/company-discovery")
    def settings_company_discovery() -> str:
        return render_template(
            "settings_company_discovery.html",
            discovery_form=load_company_discovery_settings_form(settings_path),
        )

    @app.post("/settings/company-discovery")
    def settings_company_discovery_save():
        try:
            save_company_discovery_settings(
                settings_path,
                external_lookup_enabled=(
                    request.form.get("external_lookup") == "enabled"
                ),
            )
        except CompanyDiscoverySettingsError as error:
            flash(str(error), "error")
        else:
            flash("External company lookup preference saved.", "success")
        return redirect(url_for("settings_company_discovery"))

    @app.post("/settings/about/check-updates")
    def settings_about_check_updates():
        session["update_check"] = check_for_update(
            __version__,
            installed_build=__build__.removeprefix(f"{RELEASE_LABEL} Build "),
            release_label=RELEASE_LABEL,
            release_tag=RELEASE_TAG,
        ).as_session_value()
        return redirect(url_for("settings"))

    @app.get("/settings/diagnostics")
    def settings_diagnostics() -> str:
        runtime_paths = get_runtime_paths()
        diagnostics = build_diagnostics_view(
            runtime_paths.database_path,
            settings_path,
        )
        application_info = build_application_info(
            database_path=runtime_paths.database_path,
            user_data_location=runtime_paths.user_data_directory,
        )
        return render_template(
            "settings_diagnostics.html",
            diagnostics=diagnostics,
            diagnostic_logs=list_diagnostic_logs(runtime_paths.logs_path),
            support_summary=build_support_summary(
                application_info,
                diagnostics,
            ),
        )

    @app.get("/settings/diagnostics/logs/<log_name>")
    def settings_diagnostic_log(log_name: str) -> str:
        runtime_paths = get_runtime_paths()
        try:
            log_view = read_diagnostic_log(runtime_paths.logs_path, log_name)
        except DiagnosticLogError as error:
            flash(str(error), "error")
            return redirect(url_for("settings_diagnostics"))
        return render_template(
            "settings_diagnostic_log.html",
            log_view=log_view,
        )

    @app.get("/settings/diagnostics/logs/<log_name>/download")
    def settings_diagnostic_log_download(log_name: str):
        runtime_paths = get_runtime_paths()
        try:
            log_path = get_diagnostic_log_download(
                runtime_paths.logs_path,
                log_name,
            )
        except DiagnosticLogError as error:
            flash(str(error), "error")
            return redirect(url_for("settings_diagnostics"))
        return send_file(
            log_path,
            as_attachment=True,
            download_name=log_path.name,
            mimetype="text/plain",
        )

    @app.post("/settings/diagnostics/open-data")
    def settings_diagnostics_open_data():
        runtime_paths = get_runtime_paths()
        try:
            open_data_directory(runtime_paths.user_data_directory)
        except DiagnosticLogError as error:
            flash(str(error), "error")
        else:
            flash("Junior opened the data directory.", "success")
        return redirect(url_for("settings_diagnostics"))

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

    @app.get("/settings/schedule")
    def settings_schedule() -> str:
        runtime_paths = get_runtime_paths()
        return render_template(
            "settings_schedule.html",
            schedule_view=build_schedule_view(runtime_paths.database_path),
            scheduler_integration=inspect_scheduler(),
        )

    @app.post("/settings/schedule")
    def settings_schedule_save():
        runtime_paths = get_runtime_paths()
        try:
            save_scan_schedule(
                runtime_paths.database_path,
                enabled=request.form.get("enabled") == "yes",
                run_time=request.form.get("run_time", ""),
                weekdays=request.form.getlist("weekdays"),
                email_delivery=request.form.get("email_delivery") == "yes",
            )
        except ScheduleError as error:
            flash(str(error), "error")
            return redirect(url_for("settings_schedule"))
        flash("Scan schedule saved.", "success")
        return redirect(url_for("settings_schedule"))

    @app.get("/settings/retention")
    def settings_retention() -> str:
        return render_template(
            "settings_retention.html",
            retention_form=load_retention_settings_form(settings_path),
        )

    @app.post("/settings/retention")
    def settings_retention_save():
        try:
            save_retention_settings(
                settings_path,
                report_policy=request.form.get("report_policy", ""),
                report_count_text=request.form.get("report_count", ""),
                log_policy=request.form.get("log_policy", ""),
                log_count_text=request.form.get("log_count", ""),
            )
        except RetentionSettingsError as error:
            flash(str(error), "error")
            return redirect(url_for("settings_retention"))
        flash("Report and log retention settings saved.", "success")
        return redirect(url_for("settings_retention"))

    @app.post("/settings/schedule/system/apply")
    def settings_schedule_system_apply():
        runtime_paths = get_runtime_paths()
        try:
            message = apply_scheduler(
                build_schedule_view(
                    runtime_paths.database_path
                ).schedule,
                user_data_root=runtime_paths.base_directory,
            )
        except SchedulerIntegrationError as error:
            flash(str(error), "error")
        else:
            flash(message, "success")
        return redirect(url_for("settings_schedule"))

    @app.post("/settings/schedule/system/disable")
    def settings_schedule_system_disable():
        try:
            message = disable_scheduler()
        except SchedulerIntegrationError as error:
            flash(str(error), "error")
        else:
            flash(message, "success")
        return redirect(url_for("settings_schedule"))

    @app.post("/settings/schedule/system/remove")
    def settings_schedule_system_remove():
        try:
            message = remove_scheduler()
        except SchedulerIntegrationError as error:
            flash(str(error), "error")
        else:
            flash(message, "success")
        return redirect(url_for("settings_schedule"))

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
        report_history_policy=_retention_policy_label(
            settings.retention.reports.mode,
            settings.retention.reports.total_to_keep,
        ),
        report_replacement_behavior=(
            "The latest filenames remain stable. Junior archives the previous "
            "report set when report history is enabled."
        ),
        scan_config_path=DEFAULT_COMPANY_CONFIG_PATH,
        scan_settings_path=settings_path,
        scan_scoring_path=DEFAULT_SCORING_CONFIG_PATH,
        scan_report_path=DEFAULT_REPORT_PATH,
        scan_email_preview_path=DEFAULT_EMAIL_PREVIEW_PATH,
        email_status=email_readiness.message,
    )


def _retention_policy_label(mode: str, total_to_keep: int) -> str:
    if mode == "latest_only":
        return "Latest scan only"
    if mode == "latest_plus_previous":
        return "Latest scan plus the previous scan"
    return f"Most recent {total_to_keep} scans"


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
