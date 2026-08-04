"""Define Junior's command-line interface for advanced and automated use.

This module translates CLI arguments into shared services for scanning,
validation, database setup, history summaries, and application tracking. It is
an interface layer: the underlying product rules remain in reusable modules so
the web and desktop entry points do not need separate implementations.
"""

import argparse

from job_radar import __version__
from job_radar.config import ConfigError
from job_radar.history_summary import build_history_summary, format_history_summary
from job_radar.profile_storage import get_active_profile
from job_radar.runtime_paths import (
    DEFAULT_SCORING_CONFIG_PATH,
    DEFAULT_SETTINGS_PATH,
    RuntimePaths,
    UserDataPaths,
)
from job_radar.scan_service import handle_scan
from job_radar.scoring import ScoringConfigError
from job_radar.storage import initialize_database
from job_radar.tracker.tracker_models import ApplicationRecord
from job_radar.tracker.tracker_service import get_application_workflow_state
from job_radar.tracker.tracker_storage import (
    list_applications,
    update_application_status,
    upsert_application,
)
from job_radar.user_data_bootstrap import (
    UserDataBootstrapError,
    bootstrap_packaged_user_configuration,
)
from job_radar.validation import validate_configuration


TRACKER_NEEDS_ACTION_WORKFLOW_STATES = {
    "follow_up_due",
    "needs_date_review",
    "active_pipeline",
}

TRACKER_NEEDS_REVIEW_WORKFLOW_STATES = {
    "needs_date_review",
    "dormant",
    "stale",
    "presumed_closed",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="junior",
        description="Target-company job discovery and triage tool",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser(
        "bootstrap-user-data",
        help="Create user-owned storage from safe packaged defaults",
    )
    bootstrap_parser.add_argument(
        "--source-settings",
        default=None,
        help="Optional existing settings file to migrate safely",
    )
    bootstrap_parser.add_argument(
        "--source-companies",
        default=None,
        help="Optional existing company configuration file to migrate",
    )
    bootstrap_parser.add_argument(
        "--source-scoring",
        default=None,
        help="Optional existing scoring configuration file to migrate",
    )
    bootstrap_parser.add_argument(
        "--source-profiles",
        default=None,
        help="Optional existing profiles directory to migrate",
    )
    bootstrap_parser.add_argument(
        "--source-database",
        default=None,
        help="Optional existing SQLite database to migrate safely",
    )
    bootstrap_parser.add_argument(
        "--destination",
        default=None,
        help="Optional user-data root override",
    )

    scan_parser = subparsers.add_parser(
        "scan",
        help="Scan configured companies and generate a report",
    )
    scan_parser.add_argument(
        "--config",
        required=True,
        help="Path to company config YAML",
    )
    scan_parser.add_argument(
        "--settings",
        default=DEFAULT_SETTINGS_PATH,
        help="Path to settings.yaml",
    )
    scan_parser.add_argument(
        "--report",
        required=True,
        help="Path to output HTML report",
    )
    scan_parser.add_argument(
        "--email-preview",
        default=None,
        help="Optional path to write a plain-text email preview. No email is sent.",
    )
    scan_parser.add_argument(
        "--send-email",
        action="store_true",
        help="Send the configured SMTP email after the scan.",
    )
    scan_parser.add_argument(
        "--scoring",
        default=DEFAULT_SCORING_CONFIG_PATH,
        help="Path to scoring YAML file",
    )

    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate configuration without scanning job sources",
    )
    validate_parser.add_argument(
        "--config",
        required=True,
        help="Path to companies.yaml",
    )
    validate_parser.add_argument(
        "--settings",
        default=DEFAULT_SETTINGS_PATH,
        help="Path to settings.yaml",
    )
    validate_parser.add_argument(
        "--scoring",
        default=DEFAULT_SCORING_CONFIG_PATH,
        help="Path to scoring YAML file",
    )
    validate_parser.add_argument(
        "--report",
        default=None,
        help="Optional report path to validate output directory access",
    )
    validate_parser.add_argument(
        "--email-preview",
        default=None,
        help="Optional email preview path to validate output directory access",
    )

    history_summary_parser = subparsers.add_parser(
        "history-summary",
        help="Summarize application history",
    )
    history_summary_parser.add_argument(
        "--settings",
        default=None,
        help="Optional explicit path to settings.yaml",
    )

    history_parser = subparsers.add_parser(
        "history",
        help="Work with application history",
    )
    history_subparsers = history_parser.add_subparsers(
        dest="history_command",
        required=True,
    )

    history_summary_group_parser = history_subparsers.add_parser(
        "summary",
        help="Summarize application history",
    )
    history_summary_group_parser.add_argument(
        "--settings",
        default=None,
        help="Optional explicit path to settings.yaml",
    )

    subparsers.add_parser(
        "init-db",
        help="Initialize the local SQLite database",
    )

    db_parser = subparsers.add_parser(
        "db",
        help="Work with the local SQLite database",
    )
    db_subparsers = db_parser.add_subparsers(
        dest="db_command",
        required=True,
    )
    db_subparsers.add_parser(
        "init",
        help="Initialize the local SQLite database",
    )

    tracker_parser = subparsers.add_parser(
        "tracker",
        help="Work with the application tracker",
    )
    tracker_subparsers = tracker_parser.add_subparsers(
        dest="tracker_command",
        required=True,
    )

    tracker_list_parser = tracker_subparsers.add_parser(
        "list",
        help="List tracked applications",
    )
    tracker_list_parser.add_argument(
        "--settings",
        default=None,
        help="Optional explicit path to settings.yaml",
    )
    tracker_list_filter_group = tracker_list_parser.add_mutually_exclusive_group()
    tracker_list_filter_group.add_argument(
        "--needs-action",
        action="store_true",
        help="Only show applications that need action or close attention",
    )
    tracker_list_filter_group.add_argument(
        "--needs-review",
        action="store_true",
        help="Only show applications that need tracker review or cleanup",
    )

    tracker_update_parser = tracker_subparsers.add_parser(
        "update",
        help="Update a tracked application",
    )
    tracker_update_parser.add_argument(
        "--junior-id",
        "--job-radar-id",
        dest="job_radar_id",
        required=True,
        help="Junior ID for the tracked application",
    )
    tracker_update_parser.add_argument(
        "--status",
        required=True,
        help="New application status",
    )
    tracker_update_parser.add_argument(
        "--follow-up-on",
        default=None,
        help="Optional follow-up date, such as 2026-07-10",
    )
    tracker_update_parser.add_argument(
        "--applied-on",
        default=None,
        help="Optional application date, such as 2026-07-03",
    )
    tracker_update_parser.add_argument(
        "--last-activity-on",
        default=None,
        help="Optional last activity date, such as 2026-07-05",
    )
    tracker_update_parser.add_argument(
        "--outcome",
        default=None,
        help="Optional application outcome",
    )
    tracker_update_parser.add_argument(
        "--notes",
        default=None,
        help="Optional tracker notes",
    )
    tracker_update_parser.add_argument(
        "--settings",
        default=None,
        help="Optional explicit path to settings.yaml",
    )

    tracker_add_parser = tracker_subparsers.add_parser(
        "add",
        help="Add a tracked application",
    )
    tracker_add_parser.add_argument(
        "--junior-id",
        "--job-radar-id",
        dest="job_radar_id",
        required=True,
        help="Junior ID for the tracked application",
    )
    tracker_add_parser.add_argument(
        "--company",
        required=True,
        help="Company name",
    )
    tracker_add_parser.add_argument(
        "--role",
        required=True,
        help="Role title",
    )
    tracker_add_parser.add_argument(
        "--url",
        default=None,
        help="Optional source URL",
    )
    tracker_add_parser.add_argument(
        "--status",
        default="review_needed",
        help="Application status",
    )
    tracker_add_parser.add_argument(
        "--follow-up-on",
        default=None,
        help="Optional follow-up date, such as 2026-07-10",
    )
    tracker_add_parser.add_argument(
        "--applied-on",
        default=None,
        help="Optional application date, such as 2026-07-03",
    )
    tracker_add_parser.add_argument(
        "--last-activity-on",
        default=None,
        help="Optional last activity date, such as 2026-07-05",
    )
    tracker_add_parser.add_argument(
        "--outcome",
        default=None,
        help="Optional application outcome",
    )
    tracker_add_parser.add_argument(
        "--notes",
        default=None,
        help="Optional tracker notes",
    )
    tracker_add_parser.add_argument(
        "--settings",
        default=None,
        help="Optional explicit path to settings.yaml",
    )

    return parser


def handle_bootstrap_user_data(
    *,
    source_settings_path: str | None = None,
    source_company_config_path: str | None = None,
    source_scoring_config_path: str | None = None,
    source_profiles_path: str | None = None,
    source_database_path: str | None = None,
    destination: str | None = None,
) -> None:
    user_data_paths = (
        UserDataPaths.from_root(destination)
        if destination is not None
        else UserDataPaths.default()
    )
    result = bootstrap_packaged_user_configuration(
        source_settings_path=source_settings_path,
        source_company_config_path=source_company_config_path,
        source_scoring_config_path=source_scoring_config_path,
        source_profiles_path=source_profiles_path,
        source_database_path=source_database_path,
        user_data_paths=user_data_paths,
    )

    print("User data bootstrap complete")
    print(f"Destination: {user_data_paths.root}")
    print(f"Files copied: {len(result.copied_files)}")
    print(f"Existing files preserved: {len(result.preserved_files)}")

    for copy_result in result.copied_files:
        print(f"Copied: {copy_result.destination}")

    for copy_result in result.preserved_files:
        print(f"Preserved: {copy_result.destination}")


def handle_history_summary(settings_path: str | None) -> None:
    runtime_paths = RuntimePaths.from_settings_argument(settings_path)
    database_path = runtime_paths.database_path
    initialize_database(database_path)

    active_profile = get_active_profile(database_path)
    summary = build_history_summary(
        database_path,
        profile_id=(active_profile.profile_id if active_profile else None),
    )

    print(format_history_summary(summary), end="")


def handle_tracker_list(
    settings_path: str | None,
    *,
    needs_action: bool = False,
    needs_review: bool = False,
) -> None:
    runtime_paths = RuntimePaths.from_settings_argument(settings_path)
    database_path = runtime_paths.database_path
    initialize_database(database_path)

    active_profile = get_active_profile(database_path)
    applications = list_applications(
        database_path,
        profile_id=(active_profile.profile_id if active_profile else None),
    )

    if needs_action:
        applications = [
            application
            for application in applications
            if get_application_workflow_state(application)
            in TRACKER_NEEDS_ACTION_WORKFLOW_STATES
        ]

    if needs_review:
        applications = [
            application
            for application in applications
            if get_application_workflow_state(application)
            in TRACKER_NEEDS_REVIEW_WORKFLOW_STATES
        ]

    print("Application tracker")
    print(f"Database: {database_path}")
    print(f"Applications tracked: {len(applications)}")

    if needs_action:
        print("Filter: needs action")

    if needs_review:
        print("Filter: needs review")

    if not applications:
        print("No tracked applications.")
        return

    for application in applications:
        workflow_state = get_application_workflow_state(application)

        print()
        print(f"- {application.company_name} — {application.role_title}")
        print(f"  Junior ID: {application.job_radar_id}")
        print(f"  Status: {application.status}")
        print(f"  Workflow: {workflow_state}")

        if application.follow_up_on:
            print(f"  Follow up on: {application.follow_up_on}")

        if application.applied_on:
            print(f"  Applied on: {application.applied_on}")

        if application.last_activity_on:
            print(f"  Last activity on: {application.last_activity_on}")

        if application.outcome:
            print(f"  Outcome: {application.outcome}")

        if application.source_url:
            print(f"  URL: {application.source_url}")

        if application.notes:
            print(f"  Notes: {application.notes}")


def handle_tracker_add(
    settings_path: str | None,
    *,
    job_radar_id: str,
    company_name: str,
    role_title: str,
    source_url: str | None = None,
    status: str = "review_needed",
    follow_up_on: str | None = None,
    applied_on: str | None = None,
    last_activity_on: str | None = None,
    outcome: str | None = None,
    notes: str | None = None,
) -> None:
    runtime_paths = RuntimePaths.from_settings_argument(settings_path)
    database_path = runtime_paths.database_path
    initialize_database(database_path)
    active_profile = get_active_profile(database_path)

    result = upsert_application(
        database_path,
        ApplicationRecord(
            job_radar_id=job_radar_id,
            company_name=company_name,
            role_title=role_title,
            source_url=source_url,
            status=status,
            follow_up_on=follow_up_on,
            outcome=outcome,
            notes=notes,
            applied_on=applied_on,
            last_activity_on=last_activity_on,
        ),
        profile_id=(active_profile.profile_id if active_profile else None),
    )

    print("Application tracker entry saved")
    print(f"Database: {database_path}")
    print(f"Result: {result}")
    print(f"Junior ID: {job_radar_id}")
    print(f"Company: {company_name}")
    print(f"Role: {role_title}")
    print(f"Status: {status}")

    if follow_up_on:
        print(f"Follow up on: {follow_up_on}")

    if applied_on:
        print(f"Applied on: {applied_on}")

    if last_activity_on:
        print(f"Last activity on: {last_activity_on}")

    if outcome:
        print(f"Outcome: {outcome}")

    if source_url:
        print(f"URL: {source_url}")

    if notes:
        print(f"Notes: {notes}")


def handle_tracker_update(
    settings_path: str | None,
    *,
    job_radar_id: str,
    status: str,
    follow_up_on: str | None = None,
    applied_on: str | None = None,
    last_activity_on: str | None = None,
    outcome: str | None = None,
    notes: str | None = None,
) -> None:
    runtime_paths = RuntimePaths.from_settings_argument(settings_path)
    database_path = runtime_paths.database_path
    initialize_database(database_path)
    active_profile = get_active_profile(database_path)

    updated = update_application_status(
        database_path,
        job_radar_id=job_radar_id,
        status=status,
        follow_up_on=follow_up_on,
        outcome=outcome,
        notes=notes,
        applied_on=applied_on,
        last_activity_on=last_activity_on,
        profile_id=(active_profile.profile_id if active_profile else None),
    )

    if not updated:
        print("Application tracker update failed")
        print(f"Database: {database_path}")
        print(f"Junior ID: {job_radar_id}")
        print("Reason: tracked application was not found")
        return

    print("Application tracker updated")
    print(f"Database: {database_path}")
    print(f"Junior ID: {job_radar_id}")
    print(f"Status: {status}")

    if follow_up_on:
        print(f"Follow up on: {follow_up_on}")

    if applied_on:
        print(f"Applied on: {applied_on}")

    if last_activity_on:
        print(f"Last activity on: {last_activity_on}")

    if outcome:
        print(f"Outcome: {outcome}")

    if notes:
        print(f"Notes: {notes}")


def handle_validate(
    config_path: str,
    settings_path: str,
    scoring_path: str,
    report_path: str | None = None,
    email_preview_path: str | None = None,
) -> None:
    result = validate_configuration(
        config_path=config_path,
        settings_path=settings_path,
        scoring_path=scoring_path,
        report_path=report_path,
        email_preview_path=email_preview_path,
    )

    print("Configuration validation passed")

    for check in result.checks:
        print(f"- {check}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "bootstrap-user-data":
            handle_bootstrap_user_data(
                source_settings_path=args.source_settings,
                source_company_config_path=args.source_companies,
                source_scoring_config_path=args.source_scoring,
                source_profiles_path=args.source_profiles,
                source_database_path=args.source_database,
                destination=args.destination,
            )
            return

        if args.command == "scan":
            handle_scan(
                config_path=args.config,
                settings_path=args.settings,
                report_path=args.report,
                scoring_path=args.scoring,
                email_preview_path=args.email_preview,
                send_email=args.send_email,
            )
            return

        if args.command == "validate":
            handle_validate(
                config_path=args.config,
                settings_path=args.settings,
                scoring_path=args.scoring,
                report_path=args.report,
                email_preview_path=args.email_preview,
            )
            return

        if args.command == "history-summary":
            handle_history_summary(settings_path=args.settings)
            return

        if args.command == "history":
            if args.history_command == "summary":
                handle_history_summary(settings_path=args.settings)
                return

        if args.command == "init-db":
            runtime_paths = RuntimePaths.from_default_settings()
            db_path = initialize_database(runtime_paths.database_path)
            print(f"Database initialized: {db_path}")
            return

        if args.command == "db":
            if args.db_command == "init":
                runtime_paths = RuntimePaths.from_default_settings()
                db_path = initialize_database(runtime_paths.database_path)
                print(f"Database initialized: {db_path}")
                return

        if args.command == "tracker":
            if args.tracker_command == "list":
                handle_tracker_list(
                    settings_path=args.settings,
                    needs_action=args.needs_action,
                    needs_review=args.needs_review,
                )
                return

            if args.tracker_command == "add":
                handle_tracker_add(
                    settings_path=args.settings,
                    job_radar_id=args.job_radar_id,
                    company_name=args.company,
                    role_title=args.role,
                    source_url=args.url,
                    status=args.status,
                    follow_up_on=args.follow_up_on,
                    applied_on=args.applied_on,
                    last_activity_on=args.last_activity_on,
                    outcome=args.outcome,
                    notes=args.notes,
                )
                return

            if args.tracker_command == "update":
                handle_tracker_update(
                    settings_path=args.settings,
                    job_radar_id=args.job_radar_id,
                    status=args.status,
                    follow_up_on=args.follow_up_on,
                    applied_on=args.applied_on,
                    last_activity_on=args.last_activity_on,
                    outcome=args.outcome,
                    notes=args.notes,
                )
                return

    except (ConfigError, ScoringConfigError, UserDataBootstrapError) as error:
        parser.exit(status=1, message=f"Config error: {error}\n")

if __name__ == "__main__":
    main()
