import argparse
from datetime import date
from pathlib import Path

from flask import Flask, render_template

from job_radar.runtime_paths import RuntimePaths
from job_radar.scan_service import handle_scan
from job_radar.storage import initialize_database
from job_radar.web_routes.companies import register_company_routes
from job_radar.web_routes.history import register_history_routes
from job_radar.web_routes.profile import register_profile_routes
from job_radar.web_routes.reports import (
    build_latest_report_summary,
    register_report_routes,
)
from job_radar.web_routes.scan import register_scan_routes
from job_radar.web_routes.settings import register_settings_routes
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

    initialize_database(runtime_paths.database_path)

    @app.get("/")
    def index() -> str:
        database_path = _get_database_path(app)
        applications = get_tracker_application_views(database_path)
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

    register_company_routes(
        app,
        get_company_config_path=lambda: str(
            _get_runtime_paths(app).company_config_path
        ),
    )

    register_profile_routes(
        app,
        settings_path=app.config["JOB_RADAR_SETTINGS_PATH"],
        base_directory=str(_get_runtime_paths(app).base_directory),
    )

    register_history_routes(
        app,
        get_database_path=lambda: _get_database_path(app),
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
        today_provider=lambda: date.today(),
    )

    return app


def _get_runtime_paths(app: Flask) -> RuntimePaths:
    return app.config["JOB_RADAR_RUNTIME_PATHS"]


def _get_database_path(app: Flask) -> str:
    database_path = _get_runtime_paths(app).database_path
    initialize_database(database_path)
    return str(database_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="job_radar.web_app",
        description="Local Job Radar web interface",
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


def main() -> None:
    args = build_parser().parse_args()
    app = create_app(settings_path=args.settings)
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
