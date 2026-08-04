"""Prepare and serve normal-user settings and application information."""

import io
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from flask import (
    Flask,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from job_radar import __build__, __version__
from job_radar.application_info_service import build_application_info
from job_radar.build_info import RELEASE_LABEL, RELEASE_TAG
from job_radar.collector_catalog import list_collector_capabilities
from job_radar.company_discovery_settings_service import (
    CompanyDiscoverySettingsError,
    load_company_discovery_settings_form,
    save_company_discovery_settings,
)
from job_radar.config import load_settings
from job_radar.diagnostic_log_service import (
    DiagnosticLogError,
    build_diagnostic_log_download,
    build_support_summary,
    diagnostic_download_name,
    list_diagnostic_logs,
    open_data_directory,
    read_diagnostic_log,
)
from job_radar.diagnostic_service import build_diagnostics_view
from job_radar.email_sender import get_email_readiness, send_generated_scan_report
from job_radar.email_settings_service import (
    EmailSettingsError,
    load_email_settings_form,
    save_email_settings,
    test_email_connection,
)
from job_radar.retention_settings_service import (
    RetentionSettingsError,
    load_retention_settings_form,
    save_retention_settings,
)
from job_radar.runtime_paths import (
    DEFAULT_COMPANY_CONFIG_PATH,
    DEFAULT_EMAIL_PREVIEW_PATH,
    DEFAULT_REPORT_PATH,
    DEFAULT_SCORING_CONFIG_PATH,
    RuntimePaths,
)
from job_radar.schedule_service import (
    ScheduleError,
    build_schedule_view,
    save_scan_schedule,
)
from job_radar.scan_progress import calculate_scan_elapsed_seconds
from job_radar.scheduler_integration import (
    SchedulerIntegrationError,
    apply_scheduler,
    disable_scheduler,
    inspect_scheduler,
    remove_scheduler,
)
from job_radar.source_health_service import build_latest_scan_warnings
from job_radar.storage import fetch_latest_scan_run
from job_radar.update_check_service import check_for_update
from job_radar.update_install_service import (
    UpdateInstallError,
    download_verified_update,
    launch_windows_installer,
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
        runtime_paths = get_runtime_paths()
        settings_view = _build_settings_view(settings_path)

        return render_template(
            "settings.html",
            settings_view=settings_view,
            retention_form=load_retention_settings_form(settings_path),
            email_form=load_email_settings_form(settings_path),
            connection_test=session.get("email_connection_test"),
            delivery_test=session.get("email_delivery_test"),
            schedule_view=build_schedule_view(runtime_paths.database_path),
            scheduler_integration=inspect_scheduler(),
            discovery_form=load_company_discovery_settings_form(settings_path),
            llm_connection_test=session.get("llm_connection_test"),
            open_section=request.args.get("section", "").strip(),
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
    def settings_about() -> str:
        """Present normal-user help separately from technical diagnostics."""

        runtime_paths = get_runtime_paths()
        return render_template(
            "settings_about.html",
            application_info=build_application_info(
                database_path=runtime_paths.database_path,
                user_data_location=runtime_paths.user_data_directory,
            ),
        )

    @app.get("/settings/job-platforms")
    def settings_job_platforms() -> str:
        return render_template(
            "settings_job_platforms.html",
            capabilities=list_collector_capabilities(),
        )

    @app.get("/settings/diagnostics/sources")
    def settings_source_health():
        """Keep old bookmarks working after source health moved to Companies."""

        return redirect(url_for("companies", _anchor="company-sources"))

    @app.get("/settings/diagnostics/latest-scan")
    def settings_scan_diagnostics() -> str:
        runtime_paths = get_runtime_paths()
        latest_scan = fetch_latest_scan_run(runtime_paths.database_path)
        return render_template(
            "settings_scan_diagnostics.html",
            warnings=build_latest_scan_warnings(runtime_paths.database_path),
            latest_scan=latest_scan,
            elapsed_seconds=(
                calculate_scan_elapsed_seconds(latest_scan)
                if latest_scan is not None
                else None
            ),
        )

    @app.get("/settings/company-discovery")
    def settings_company_discovery():
        """Keep old bookmarks working after lookup controls moved to Settings."""

        return redirect(
            url_for(
                "settings",
                section="company-discovery",
                _anchor="company-discovery-settings",
            )
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
        return _settings_section_redirect("company-discovery")

    @app.post("/settings/about/check-updates")
    def settings_about_check_updates():
        session["update_check"] = check_for_update(
            __version__,
            installed_build=__build__.removeprefix(f"{RELEASE_LABEL} Build "),
            release_label=RELEASE_LABEL,
            release_tag=RELEASE_TAG,
        ).as_session_value()
        return redirect(url_for("settings_diagnostics"))

    @app.post("/settings/install-update")
    def settings_install_update():
        shutdown_event = current_app.config.get(
            "JOB_RADAR_DESKTOP_SHUTDOWN_EVENT"
        )
        update_exit_event = current_app.config.get(
            "JOB_RADAR_DESKTOP_UPDATE_EXIT_EVENT"
        )
        if not (
            shutdown_event is not None
            and update_exit_event is not None
            and current_app.config.get("JOB_RADAR_DESKTOP_UPDATE_AVAILABLE")
        ):
            flash(
                "Automatic updates are available from the installed Windows "
                "desktop app only.",
                "error",
            )
            return redirect(url_for("settings_diagnostics"))

        update = check_for_update(
            __version__,
            installed_build=__build__.removeprefix(f"{RELEASE_LABEL} Build "),
            release_label=RELEASE_LABEL,
            release_tag=RELEASE_TAG,
        )
        try:
            installer_path = download_verified_update(
                update,
                get_runtime_paths().user_data_directory / "updates",
            )
            launch_windows_installer(
                installer_path,
                application_path=Path(sys.executable),
                result_path=(
                    get_runtime_paths().user_data_directory
                    / "updates"
                    / "last-update-result.json"
                ),
                log_path=(
                    get_runtime_paths().logs_path / "junior-update.log"
                ),
                expected_build=(
                    f"{RELEASE_LABEL} Build {update.available_build}"
                    if update.available_build
                    else str(update.available_version)
                ),
            )
        except UpdateInstallError as error:
            flash(str(error), "error")
            return redirect(url_for("settings_diagnostics"))

        # Give the response time to reach the native window before closing it.
        def close_for_update() -> None:
            update_exit_event.set()
            shutdown_event.set()

        timer = threading.Timer(1.0, close_for_update)
        timer.daemon = True
        timer.start()
        return render_template(
            "update_installing.html",
            update=update,
        )

    @app.post("/settings/update-result/dismiss")
    def dismiss_update_result():
        current_app.config["JOB_RADAR_UPDATE_RESULT"] = None
        destination = request.form.get("next", "").strip()
        if not destination.startswith("/") or destination.startswith("//"):
            destination = url_for("settings_diagnostics")
        return redirect(destination)

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
        diagnostic_logs = list_diagnostic_logs(runtime_paths.logs_path)
        selected_log_name = request.args.get("log", "").strip()
        if not selected_log_name and diagnostic_logs:
            selected_log_name = diagnostic_logs[0].name
        selected_log = None
        if selected_log_name:
            try:
                selected_log = read_diagnostic_log(
                    runtime_paths.logs_path,
                    selected_log_name,
                )
            except DiagnosticLogError:
                selected_log_name = ""
        return render_template(
            "settings_diagnostics.html",
            diagnostics=diagnostics,
            settings_view=_build_settings_view(settings_path),
            application_info=application_info,
            update_check=session.pop("update_check", None),
            update_install_available=bool(
                current_app.config.get("JOB_RADAR_DESKTOP_UPDATE_AVAILABLE")
            ),
            diagnostic_logs=diagnostic_logs,
            selected_log=selected_log,
            selected_log_name=selected_log_name,
            support_summary=build_support_summary(
                application_info,
                diagnostics,
            ),
        )

    @app.get("/settings/diagnostics/logs/<log_name>")
    def settings_diagnostic_log(log_name: str) -> str:
        return redirect(
            url_for(
                "settings_diagnostics",
                log=log_name,
                _anchor="developer-logs",
            )
        )

    @app.get("/settings/diagnostics/logs/<log_name>/download")
    def settings_diagnostic_log_download(log_name: str):
        runtime_paths = get_runtime_paths()
        try:
            download_content = build_diagnostic_log_download(
                runtime_paths.logs_path,
                log_name,
            )
            log_view = read_diagnostic_log(runtime_paths.logs_path, log_name)
        except DiagnosticLogError as error:
            flash(str(error), "error")
            return redirect(url_for("settings_diagnostics"))
        download_name = diagnostic_download_name(log_view)
        return send_file(
            io.BytesIO(download_content.encode("utf-8")),
            as_attachment=True,
            download_name=download_name,
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
    def settings_email():
        """Keep old bookmarks working after email controls moved to Settings."""

        return _settings_section_redirect("email")

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
            return _settings_section_redirect("email")
        flash("Email settings saved.", "success")
        return _settings_section_redirect("email")

    @app.get("/settings/schedule")
    def settings_schedule():
        """Keep old bookmarks working after schedule controls moved to Settings."""

        return _settings_section_redirect("schedule")

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
            return _settings_section_redirect("schedule")
        flash("Scan schedule saved.", "success")
        return _settings_section_redirect("schedule")

    @app.get("/settings/retention")
    def settings_retention():
        """Keep old bookmarks working after retention controls moved to Settings."""

        return _settings_section_redirect("retention")

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
            return _settings_section_redirect("retention")
        flash("Report and log retention settings saved.", "success")
        return _settings_section_redirect("retention")

    @app.post("/settings/llm")
    def settings_llm_save():
        flash("AI résumé tailoring is under development.", "info")
        return _settings_section_redirect("llm")

    @app.post("/settings/llm/test")
    def settings_llm_test():
        session.pop("llm_connection_test", None)
        flash("AI résumé tailoring is under development.", "info")
        return _settings_section_redirect("llm")

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
        return _settings_section_redirect("schedule")

    @app.post("/settings/schedule/system/disable")
    def settings_schedule_system_disable():
        try:
            message = disable_scheduler()
        except SchedulerIntegrationError as error:
            flash(str(error), "error")
        else:
            flash(message, "success")
        return _settings_section_redirect("schedule")

    @app.post("/settings/schedule/system/remove")
    def settings_schedule_system_remove():
        try:
            message = remove_scheduler()
        except SchedulerIntegrationError as error:
            flash(str(error), "error")
        else:
            flash(message, "success")
        return _settings_section_redirect("schedule")

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
        return _settings_section_redirect("email")

    @app.post("/settings/email/send-latest")
    def settings_email_send_latest():
        runtime_paths = get_runtime_paths()
        result = send_generated_scan_report(
            load_settings(settings_path).email,
            preview_path=runtime_paths.resolve(DEFAULT_EMAIL_PREVIEW_PATH),
            report_path=runtime_paths.resolve(DEFAULT_REPORT_PATH),
        )
        session["email_delivery_test"] = _email_delivery_status(
            sent=result.sent,
            message=result.message,
        )
        return _settings_section_redirect("email")


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


def _settings_section_redirect(section: str):
    """Return users to the inline Settings section they were working in."""

    return redirect(
        url_for(
            "settings",
            section=section,
            _anchor=f"{section}-settings",
        )
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


def _email_delivery_status(*, sent: bool, message: str) -> dict[str, str]:
    tested_time = datetime.now().astimezone().strftime("%I:%M %p").lstrip("0")
    return {
        "status": "Scan summary sent" if sent else "Scan summary not sent",
        "reason": (
            "Junior sent the latest summary and attached the full HTML report."
            if sent
            else message
        ),
        "tone": "success" if sent else "error",
        "tested_at": f"Today at {tested_time}",
    }
