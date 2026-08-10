"""Create and launch the Junior web interface with safe startup diagnostics."""

import argparse
import json
import os
import secrets
import sys
import traceback
from datetime import UTC, date, datetime
from pathlib import Path
from time import monotonic

from flask import Flask, g, jsonify, redirect, render_template, request, url_for

from job_radar import __build__, __version__
from job_radar.build_info import RELEASE_LABEL
from job_radar.config import ConfigError
from job_radar.csrf import register_csrf_protection
from job_radar.runtime_paths import RuntimePaths, get_default_user_data_directory
from job_radar.operational_event_log import (
    record_operational_event,
    set_diagnostic_operation_id,
)
from job_radar.session_secret import load_or_create_session_secret
from job_radar.profile_storage import get_active_profile
from job_radar.first_run_service import needs_first_run_setup
from job_radar.starter_catalog_service import seed_starter_catalog
from job_radar.job_decision_service import (
    DECISION_PASSED,
    DECISION_SAVED,
    list_job_decisions,
)
from job_radar.employer_import import import_pending_legacy_employers
from job_radar.scan_service import handle_scan
from job_radar.setup_progress_service import incomplete_setup_destination
from job_radar.storage import (
    fetch_included_job_history_records,
    initialize_database,
)
from job_radar.web_routes.companies import register_company_routes
from job_radar.web_routes.administration import register_administration_routes
from job_radar.web_routes.history import register_history_routes
from job_radar.web_routes.profile import register_profile_routes
from job_radar.web_routes.reports import (
    build_latest_report_summary,
    build_review_inbox_summary,
    register_report_routes,
)
from job_radar.web_routes.scan import register_scan_routes
from job_radar.web_routes.settings import register_settings_routes
from job_radar.web_routes.setup import register_setup_routes
from job_radar.web_routes.tracker import (
    CANONICAL_DECISION_FILTER_OPTIONS,
    TRACKER_EDIT_OUTCOME_OPTIONS,
    build_tracker_summary,
    get_dashboard_attention_applications,
    get_tracker_application_views,
    register_tracker_routes,
)



def create_app(
    settings_path: str | Path | None = None,
    *,
    base_directory: str | Path | None = None,
    isolate_scan_process: bool = False,
) -> Flask:
    app = Flask(__name__)
    runtime_paths = (
        RuntimePaths.from_settings(
            settings_path=settings_path,
            base_directory=base_directory,
        )
        if settings_path is not None and base_directory is not None
        else RuntimePaths.from_settings_argument(settings_path)
    )
    app.config["JOB_RADAR_RUNTIME_PATHS"] = runtime_paths
    app.config["JOB_RADAR_SETTINGS_PATH"] = str(runtime_paths.settings_path)
    app.config["SECRET_KEY"] = load_or_create_session_secret(
        runtime_paths.database_path
    )
    # This marker makes an Administration unlock valid only for this process.
    app.config["JOB_RADAR_ADMIN_SESSION_MARKER"] = secrets.token_urlsafe(32)
    update_result_path = (
        runtime_paths.user_data_directory / "updates" / "last-update-result.json"
    )
    update_result = None
    if update_result_path.is_file():
        try:
            candidate = json.loads(update_result_path.read_text(encoding="utf-8-sig"))
            if (
                isinstance(candidate, dict)
                and candidate.get("status") in {"success", "error"}
                and isinstance(candidate.get("message"), str)
            ):
                update_result = candidate
        except (OSError, UnicodeError, json.JSONDecodeError):
            update_result = {
                "status": "error",
                "message": (
                    "Junior restarted, but the update result could not be read. "
                    "Check the installed build in Diagnostics."
                ),
            }
        update_result_path.unlink(missing_ok=True)
    app.config["JOB_RADAR_UPDATE_RESULT"] = update_result

    @app.context_processor
    def inject_build_label() -> dict[str, str]:
        """Make the exact tester build visible on every GUI page."""

        return {
            "junior_build_label": __build__,
            "junior_release_label": RELEASE_LABEL,
            # Keep the result visible until the user explicitly dismisses it.
            "junior_update_result": app.config.get("JOB_RADAR_UPDATE_RESULT"),
            "junior_test_environment_label": os.environ.get(
                "JUNIOR_TEST_ENVIRONMENT_LABEL", ""
            ).strip(),
        }

    initialize_database(runtime_paths.database_path)
    seed_starter_catalog(runtime_paths.database_path)
    # Complete the protected one-time employer migration before any profile,
    # company, or recommendation page builds a profile-owned workspace.
    import_pending_legacy_employers(
        runtime_paths.database_path,
        runtime_paths.company_config_path,
    )

    register_csrf_protection(app)

    @app.before_request
    def begin_request_diagnostics() -> None:
        """Give related GUI and error events one safe correlation value."""

        g.junior_request_id = secrets.token_hex(6)
        set_diagnostic_operation_id(g.junior_request_id)
        g.junior_request_started = monotonic()
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            record_operational_event(
                _get_runtime_paths(app).logs_path,
                kind="user_actions",
                subsystem="web",
                event="user_action_started",
                fields={
                    "request_id": g.junior_request_id,
                    "endpoint": request.endpoint or "unknown",
                    "method": request.method,
                },
            )

    @app.after_request
    def record_user_action(response):
        """Record state-changing GUI operations without form or user content."""

        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            record_operational_event(
                _get_runtime_paths(app).logs_path,
                kind="user_actions",
                subsystem="web",
                event="user_action_completed",
                severity="error" if response.status_code >= 400 else "info",
                fields={
                    "request_id": getattr(g, "junior_request_id", None),
                    "endpoint": request.endpoint or "unknown",
                    "method": request.method,
                    "status_code": response.status_code,
                    "elapsed_seconds": round(
                        monotonic()
                        - getattr(g, "junior_request_started", monotonic()),
                        3,
                    ),
                },
            )
        return response

    @app.teardown_request
    def record_unexpected_request_error(error: BaseException | None) -> None:
        """Retain safe failure context without exception messages or locals."""

        if error is None:
            return
        record_operational_event(
            _get_runtime_paths(app).logs_path,
            kind="errors",
            subsystem="web",
            event="request_failed",
            severity="error",
            fields={
                "request_id": getattr(g, "junior_request_id", None),
                "endpoint": request.endpoint or "unknown",
                "method": request.method,
                "error_type": type(error).__name__,
            },
        )
    register_administration_routes(
        app,
        get_database_path=lambda: _get_database_path(app),
        get_runtime_paths=lambda: _get_runtime_paths(app),
    )

    @app.get("/health")
    def health():
        """Give orchestrators a bounded readiness signal without user data."""

        return jsonify(
            {
                "application": "junior",
                "status": "ready",
                "version": __version__,
            }
        )

    @app.get("/")
    def index() -> str:
        database_path = _get_database_path(app)
        setup_destination = incomplete_setup_destination(database_path)
        if setup_destination is not None:
            return redirect(url_for(setup_destination, setup="1"))
        runtime_paths = _get_runtime_paths(app)
        legacy_profile_exists = (
            runtime_paths.candidate_profile_path is not None
            and runtime_paths.candidate_profile_path.is_file()
        )
        if (
            not legacy_profile_exists
            and needs_first_run_setup(database_path)
        ):
            return redirect(url_for("setup_welcome"))
        profile_id = _get_active_profile_id(app)
        applications = get_tracker_application_views(
            database_path,
            profile_id=profile_id,
        )
        tracker_summary = build_tracker_summary(applications)
        application_history_count = len(
            fetch_included_job_history_records(
                database_path,
                profile_id=profile_id,
            )
        )
        attention_applications = get_dashboard_attention_applications(
            applications
        )
        latest_report = build_latest_report_summary(
            _get_runtime_paths(app).reports_path
        )
        review_inbox = build_review_inbox_summary(
            _get_runtime_paths(app).reports_path,
            database_path,
            profile_id=profile_id,
        )
        job_decisions = (
            list_job_decisions(database_path, profile_id=profile_id)
            if profile_id is not None
            else []
        )
        job_decision_summary = {
            "saved": sum(
                item.decision == DECISION_SAVED for item in job_decisions
            ),
            "reviewed": sum(
                item.decision == DECISION_PASSED for item in job_decisions
            ),
            "total": len(job_decisions),
        }

        return render_template(
            "index.html",
            tracker_summary=tracker_summary,
            application_history_count=application_history_count,
            attention_applications=attention_applications,
            latest_report=latest_report,
            review_inbox=review_inbox,
            job_decision_summary=job_decision_summary,
        )

    register_settings_routes(
        app,
        settings_path=app.config["JOB_RADAR_SETTINGS_PATH"],
        get_runtime_paths=lambda: _get_runtime_paths(app),
    )

    register_setup_routes(
        app,
        get_database_path=lambda: _get_database_path(app),
    )

    register_company_routes(
        app,
        get_database_path=lambda: _get_database_path(app),
        settings_path=app.config["JOB_RADAR_SETTINGS_PATH"],
    )

    register_profile_routes(
        app,
        settings_path=app.config["JOB_RADAR_SETTINGS_PATH"],
        base_directory=str(_get_runtime_paths(app).base_directory),
        database_path=str(_get_runtime_paths(app).database_path),
        scoring_path=str(_get_runtime_paths(app).scoring_config_path),
    )

    register_history_routes(
        app,
        get_database_path=lambda: _get_database_path(app),
        get_profile_id=lambda: _get_active_profile_id(app),
        decision_options=CANONICAL_DECISION_FILTER_OPTIONS,
        tracker_edit_outcome_options=TRACKER_EDIT_OUTCOME_OPTIONS,
    )

    register_scan_routes(
        app,
        get_runtime_paths=lambda: _get_runtime_paths(app),
        handle_scan_func=handle_scan,
        isolate_scan_process=isolate_scan_process,
    )

    register_report_routes(
        app,
        get_reports_path=lambda: str(
            _get_runtime_paths(app).reports_path
        ),
        get_database_path=lambda: _get_database_path(app),
        get_profile_id=lambda: _get_active_profile_id(app),
        get_logs_path=lambda: str(_get_runtime_paths(app).logs_path),
        get_settings_path=lambda: app.config["JOB_RADAR_SETTINGS_PATH"],
        get_base_directory=lambda: str(_get_runtime_paths(app).base_directory),
    )

    register_tracker_routes(
        app,
        get_database_path=lambda: _get_database_path(app),
        get_profile_id=lambda: _get_active_profile_id(app),
        today_provider=lambda: date.today(),
    )

    return app


def _get_runtime_paths(app: Flask) -> RuntimePaths:
    return app.config["JOB_RADAR_RUNTIME_PATHS"]


def _get_database_path(app: Flask) -> str:
    database_path = _get_runtime_paths(app).database_path
    initialize_database(database_path)
    return str(database_path)


def _get_active_profile_id(app: Flask) -> str | None:
    profile = get_active_profile(_get_runtime_paths(app).database_path)
    return profile.profile_id if profile is not None else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="job_radar.web_app",
        description="Local junior web interface",
    )
    parser.add_argument(
        "--settings",
        default=None,
        help="Optional explicit path to settings.yaml",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface for the local web app",
    )
    parser.add_argument(
        "--port",
        default=5000,
        type=int,
        help="Port for the local web app",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Run Flask in debug mode",
    )

    return parser


def _resolve_startup_settings_path(
    settings_path: str | Path | None,
) -> Path:
    if settings_path is not None:
        return Path(settings_path).expanduser().resolve()

    return get_default_user_data_directory() / "config" / "settings.yaml"


def _resolve_startup_log_path(
    settings_path: str | Path | None,
) -> Path:
    resolved_settings_path = _resolve_startup_settings_path(settings_path)

    if resolved_settings_path.parent.name.casefold() == "config":
        workspace_root = resolved_settings_path.parent.parent
    else:
        workspace_root = resolved_settings_path.parent

    return workspace_root / "logs" / "startup-errors.log"


def _write_startup_diagnostic_log(
    error: Exception,
    *,
    settings_path: str | Path | None,
    failure_stage: str = "application_startup",
    safe_details: dict[str, str] | None = None,
) -> Path | None:
    log_path = _resolve_startup_log_path(settings_path)
    stack_frames = traceback.extract_tb(error.__traceback__)

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).isoformat()

        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(
                f"[{timestamp}] junior startup failure\n"
                f"Version: {__version__}\n"
                f"Build: {__build__}\n"
                f"Settings file: {_resolve_startup_settings_path(settings_path)}\n"
                f"Failure stage: {failure_stage}\n"
                f"Failure category: {_startup_failure_category(error, stack_frames)}\n"
                f"Error type: {type(error).__name__}\n"
                "Stack frames:\n"
            )

            if stack_frames:
                for frame in stack_frames:
                    log_file.write(
                        f"- {frame.filename}:{frame.lineno} "
                        f"in {frame.name}\n"
                    )
            else:
                log_file.write("- unavailable\n")

            if safe_details:
                log_file.write("Safe runtime details:\n")
                for name, value in sorted(safe_details.items()):
                    log_file.write(f"- {name}: {value}\n")

            log_file.write(
                "Exception messages and local variables are intentionally "
                "omitted to reduce the risk of logging credentials.\n"
                "-----\n"
            )
    except OSError:
        return None

    return log_path


def _startup_failure_category(
    error: Exception,
    stack_frames: list[traceback.FrameSummary],
) -> str:
    """Classify startup failures without copying raw exception messages."""

    frame_names = " ".join(frame.filename.casefold() for frame in stack_frames)
    if "clr_loader" in frame_names or "pythonnet" in frame_names:
        return "windows_desktop_runtime_bridge"
    if "webview" in frame_names:
        return "desktop_window_backend"
    if isinstance(error, ConfigError):
        return "configuration"
    return "unexpected_application_failure"


def _format_configuration_startup_error(
    error: ConfigError,
    *,
    settings_path: str | Path | None,
) -> str:
    technical_details = str(error)
    resolved_settings_path = _resolve_startup_settings_path(settings_path)

    if technical_details.startswith("Config file does not exist:"):
        return (
            "junior could not start because its settings file was not found.\n\n"
            "What to do:\n"
            "Run this command once to create your junior workspace:\n\n"
            "    junior bootstrap-user-data\n\n"
            "Then start junior again.\n\n"
            "Technical details:\n"
            f"{technical_details}\n"
        )

    return (
        "junior could not start because its settings are invalid.\n\n"
        "What to do:\n"
        "Open the settings file shown below and correct the reported problem, "
        "then start junior again.\n\n"
        "Technical details:\n"
        f"{technical_details}\n\n"
        "Settings file:\n"
        f"{resolved_settings_path}\n"
    )


def _format_unexpected_startup_error(
    error: Exception,
    *,
    settings_path: str | Path | None,
    diagnostic_log_path: Path | None,
) -> str:
    resolved_settings_path = _resolve_startup_settings_path(settings_path)
    diagnostic_guidance = (
        f"Diagnostic log:\n{diagnostic_log_path}\n\n"
        if diagnostic_log_path is not None
        else (
            "Diagnostic log:\n"
            "junior could not write the diagnostic log. Include the technical "
            "details below when requesting support.\n\n"
        )
    )

    return (
        "junior could not start because of an unexpected problem.\n\n"
        "This is probably not something you can fix through junior's settings.\n\n"
        "What to do:\n"
        "Contact Clayton Graves at claytonmgraves@outlook.com and include the "
        "diagnostic log location and technical details shown below.\n\n"
        "Do not include passwords, access tokens, or other credentials in your "
        "support message.\n\n"
        f"{diagnostic_guidance}"
        "Technical details:\n"
        f"junior version: {__version__}\n"
        f"Error type: {type(error).__name__}\n"
        f"Settings file: {resolved_settings_path}\n"
        "The exception message was omitted to avoid exposing credentials or "
        "other private data.\n"
    )


def main() -> None:
    args = build_parser().parse_args()

    try:
        app = create_app(settings_path=args.settings)
        app.run(host=args.host, port=args.port, debug=args.debug)
    except ConfigError as error:
        sys.stderr.write(
            _format_configuration_startup_error(
                error,
                settings_path=args.settings,
            )
        )
        raise SystemExit(1) from error
    except Exception as error:
        diagnostic_log_path = _write_startup_diagnostic_log(
            error,
            settings_path=args.settings,
        )
        sys.stderr.write(
            _format_unexpected_startup_error(
                error,
                settings_path=args.settings,
                diagnostic_log_path=diagnostic_log_path,
            )
        )
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
