import argparse

from job_radar.config import ConfigError, load_companies, load_settings
from job_radar.storage import initialize_database
from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.registry import collect_jobs_for_company


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="job_radar",
        description="Target-company job discovery and triage tool",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser(
        "scan",
        help="Scan configured companies and generate a report",
    )
    scan_parser.add_argument(
        "--config",
        required=True,
        help="Path to companies.yaml",
    )
    scan_parser.add_argument(
        "--settings",
        default="config/settings.yaml",
        help="Path to settings.yaml",
    )
    scan_parser.add_argument(
        "--report",
        required=True,
        help="Path to output Markdown report",
    )

    subparsers.add_parser(
        "init-db",
        help="Initialize the local SQLite database",
    )

    return parser


def handle_scan(config_path: str, settings_path: str, report_path: str) -> None:
    companies = load_companies(config_path)
    settings = load_settings(settings_path)

    print("Scan requested")
    print(f"Config: {config_path}")
    print(f"Settings: {settings_path}")
    print(f"Report: {report_path}")
    print(f"Database: {settings['database_path']}")
    print()
    print("Enabled companies:")

    total_jobs = 0
    total_errors = 0

    for company in companies:
        company_key = company["company_key"]
        company_name = company["name"]
        source_type = company["source_type"]

        print(f"- {company_key} ({company_name}) source_type={source_type}")

        try:
            postings = collect_jobs_for_company(company)
        except CollectorError as error:
            total_errors += 1
            print(f"  ERROR: {error}")
            continue

        total_jobs += len(postings)
        print(f"  collected_jobs={len(postings)}")

    print()
    print("Scan summary:")
    print(f"Companies enabled: {len(companies)}")
    print(f"Jobs collected: {total_jobs}")
    print(f"Collector errors: {total_errors}")
    print()
    print("Database writes are not implemented yet.")
    print("Report generation is not implemented yet.")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "scan":
            handle_scan(
                config_path=args.config,
                settings_path=args.settings,
                report_path=args.report,
            )
            return

        if args.command == "init-db":
            settings = load_settings()
            db_path = initialize_database(settings["database_path"])
            print(f"Database initialized: {db_path}")
            return

    except ConfigError as error:
        parser.exit(status=1, message=f"Config error: {error}\n")

    except ConfigError as error:
        parser.exit(status=1, message=f"Config error: {error}\n")