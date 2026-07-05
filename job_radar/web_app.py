import argparse
from dataclasses import dataclass

from flask import Flask, render_template

from job_radar.config import load_settings
from job_radar.storage import initialize_database
from job_radar.tracker.models import ApplicationRecord
from job_radar.tracker.service import get_application_workflow_state
from job_radar.tracker.storage import list_applications


@dataclass(frozen=True)
class TrackerApplicationView:
    application: ApplicationRecord
    workflow_state: str


def create_app(settings_path: str = "config/settings.yaml") -> Flask:
    app = Flask(__name__)
    app.config["JOB_RADAR_SETTINGS_PATH"] = settings_path

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/tracker")
    def tracker() -> str:
        settings = load_settings(app.config["JOB_RADAR_SETTINGS_PATH"])
        database_path = settings["database_path"]
        initialize_database(database_path)

        applications = [
            TrackerApplicationView(
                application=application,
                workflow_state=get_application_workflow_state(application),
            )
            for application in list_applications(database_path)
        ]

        return render_template(
            "tracker.html",
            database_path=database_path,
            applications=applications,
        )

    return app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="job_radar.web_app",
        description="Local Job Radar web interface",
    )
    parser.add_argument(
        "--settings",
        default="config/settings.yaml",
        help="Path to settings.yaml",
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