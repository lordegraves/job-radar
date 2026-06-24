import argparse
from datetime import UTC, datetime

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.registry import collect_jobs_for_company
from job_radar.config import ConfigError, load_companies, load_settings
from job_radar.reporting import ScanError, ScanReport, ScoredPosting, write_markdown_report
from job_radar.scoring import (
    classify_location,
    evaluate_top_match_eligibility,
    evaluate_review_needed_eligibility,
    load_scoring_config,
    score_posting,
)
from job_radar.storage import initialize_database, upsert_job_posting


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
    scan_parser.add_argument(
        "--scoring",
        default="config/scoring.yaml",
        help="Path to scoring YAML file",
    )

    subparsers.add_parser(
        "init-db",
        help="Initialize the local SQLite database",
    )

    return parser


def handle_scan(
    config_path: str,
    settings_path: str,
    report_path: str,
    scoring_path: str = "config/scoring.yaml",
) -> None:
    companies = load_companies(config_path)
    settings = load_settings(settings_path)
    database_path = settings["database_path"]
    scoring_config = load_scoring_config(scoring_path)

    initialize_database(database_path)

    print("Scan requested")
    print(f"Config: {config_path}")
    print(f"Settings: {settings_path}")
    print(f"Report: {report_path}")
    print(f"Database: {database_path}")
    print()
    print("Enabled companies:")

    total_jobs = 0
    jobs_new = 0
    jobs_seen = 0
    jobs_changed = 0
    collector_errors: list[ScanError] = []
    collected_postings = []

    for company in companies:
        company_key = company["company_key"]
        company_name = company["name"]
        source_type = company["source_type"]

        print(f"- {company_key} ({company_name}) source_type={source_type}")

        try:
            postings = collect_jobs_for_company(company)
        except CollectorError as error:
            collector_errors.append(
                ScanError(
                    company_key=company_key,
                    company_name=company_name,
                    source_type=source_type,
                    message=str(error),
                )
            )
            print(f"  ERROR: {error}")
            continue

        total_jobs += len(postings)
        collected_postings.extend(postings)
        print(f"  collected_jobs={len(postings)}")

        for posting in postings:
            result = upsert_job_posting(database_path, posting)

            if result == "new":
                jobs_new += 1
            elif result == "seen":
                jobs_seen += 1
            elif result == "changed":
                jobs_changed += 1

    scored_postings = []

    for posting in collected_postings:
        score, reasons = score_posting(posting, scoring_config)
        location_status = classify_location(posting, scoring_config)
        top_match_eligible, top_match_reasons = evaluate_top_match_eligibility(
            posting=posting,
            score=score,
            score_reasons=reasons,
            location_status=location_status,
            scoring_config=scoring_config,
        )

        review_needed_eligible = evaluate_review_needed_eligibility(
            score=score,
            score_reasons=reasons,
            location_status=location_status,
            top_match_eligible=top_match_eligible,
            scoring_config=scoring_config,
        )

        scored_postings.append(
            ScoredPosting(
                posting=posting,
                score=score,
                score_reasons=reasons,
                location_status=location_status,
                top_match_eligible=top_match_eligible,
                review_needed_eligible=review_needed_eligible,
                top_match_reasons=top_match_reasons,
            )
        )

    scored_postings.sort(key=lambda item: item.score, reverse=True)

    report = ScanReport(
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        companies_enabled=len(companies),
        jobs_collected=total_jobs,
        jobs_new=jobs_new,
        jobs_seen=jobs_seen,
        jobs_changed=jobs_changed,
        collector_errors=collector_errors,
        postings=collected_postings,
        scored_postings=scored_postings,
    )

    written_report_path = write_markdown_report(report_path, report)

    print()
    print("Scan summary:")
    print(f"Companies enabled: {len(companies)}")
    print(f"Jobs collected: {total_jobs}")
    print(f"Jobs new: {jobs_new}")
    print(f"Jobs seen: {jobs_seen}")
    print(f"Jobs changed: {jobs_changed}")
    print(f"Collector errors: {len(collector_errors)}")
    print(f"Report written: {written_report_path}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "scan":
            handle_scan(
                config_path=args.config,
                settings_path=args.settings,
                report_path=args.report,
                scoring_path=args.scoring,
            )
            return

        if args.command == "init-db":
            settings = load_settings()
            db_path = initialize_database(settings["database_path"])
            print(f"Database initialized: {db_path}")
            return

    except ConfigError as error:
        parser.exit(status=1, message=f"Config error: {error}\n")