"""Create and launch the Job Radar web interface with safe startup diagnostics."""

import argparse
import secrets
import sys
import traceback
from datetime import UTC, date, datetime
from pathlib import Path

from flask import Flask, redirect, render_template, url_for

from job_radar import __version__
from job_radar.config import ConfigError
from job_radar.csrf import register_csrf_protection
from job_radar.runtime_paths import RuntimePaths, get_default_user_data_directory
from job_radar.session_secret import load_or_create_session_secret
from job_radar.profile_storage import get_active_profile
from job_radar.first_run_service import needs_first_run_setup
from job_radar.scan_service import handle_scan
from job_radar.setup_progress_service import incomplete_setup_destination
from job_radar.storage import initialize_database
from job_radar.web_routes.companies import register_company_routes
from job_radar.web_routes.administration import register_administration_routes
from job_radar.web_routes.history import register_history_routes
from job_radar.web_routes.profile import register_profile_routes
from job_radar.web_routes.reports import (
    build_latest_report_summary,
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

    initialize_database(runtime_paths.database_path)

    register_csrf_protection(app)
    register_administration_routes(
        app,
        get_database_path=lambda: _get_database_path(app),
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
        attention_applications = get_dashboard_attention_applications(
            applications
        )
        latest_report = build_latest_report_summary(
            _get_runtime_paths(app).reports_path
        )

        return render_template(
            "index.html",
            tracker_summary=tracker_summary,
            attention_applications=attention_applications,
            latest_report=latest_report,
        )

    register_settings_routes(
        app,
        settings_path=app.config["JOB_RADAR_SETTINGS_PATH"],
    )

    register_setup_routes(
        app,
        get_database_path=lambda: _get_database_path(app),
    )

    register_company_routes(
        app,
        get_database_path=lambda: _get_database_path(app),
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
    )

    register_report_routes(
        app,
        get_reports_path=lambda: str(
            _get_runtime_paths(app).reports_path
        ),
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
                f"Settings file: {_resolve_startup_settings_path(settings_path)}\n"
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

            log_file.write(
                "Exception messages and local variables are intentionally "
                "omitted to reduce the risk of logging credentials.\n"
                "-----\n"
            )
    except OSError:
        return None

    return log_path


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
            "    job-radar bootstrap-user-data\n\n"
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
