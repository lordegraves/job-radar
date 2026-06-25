import argparse
from datetime import UTC, datetime
from pathlib import Path

from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.registry import collect_jobs_for_company
from job_radar.config import ConfigError, load_companies, load_settings
from job_radar.email_sender import send_email_report
from job_radar.email_summary import (
    build_email_body,
    build_email_html_body,
    build_email_subject,
    write_email_preview,
)
from job_radar.reporting import (
    ScanError,
    ScanReport,
    ScoredPosting,
    write_html_report,
    write_markdown_report,
)
from job_radar.scoring import (
    classify_location,
    evaluate_review_needed_eligibility,
    evaluate_top_match_eligibility,
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
        "--email-preview",
        default=None,
        help="Optional path to write a plain-text email preview. No email is sent.",
    )
    scan_parser.add_argument(
        "--send-email",
        action="store_true",
        help="Call the email send path after scan. Current implementation does not send SMTP email.",
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
    email_preview_path: str | None = None,
    send_email: bool = False,
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

    relevant_scored_postings = [
        scored_posting
        for scored_posting in scored_postings
        if scored_posting.top_match_eligible or scored_posting.review_needed_eligible
    ]

    jobs_stored = 0
    jobs_omitted = total_jobs - len(relevant_scored_postings)

    for scored_posting in relevant_scored_postings:
        result = upsert_job_posting(database_path, scored_posting.posting)
        jobs_stored += 1

        if result == "new":
            jobs_new += 1
        elif result == "seen":
            jobs_seen += 1
        elif result == "changed":
            jobs_changed += 1

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
        top_match_min_score=scoring_config["top_matches"]["min_score"],
        review_needed_min_score=scoring_config["review_needed"]["min_score"],
        jobs_stored=jobs_stored,
        jobs_omitted=jobs_omitted,
    )

    written_report_path = write_markdown_report(report_path, report)
    written_html_report_path = write_html_report(
        Path(report_path).with_suffix(".html"),
        report,
    )

    written_email_preview_path = None

    if email_preview_path is not None:
        written_email_preview_path = write_email_preview(
            email_preview_path,
            report,
            written_report_path,
        )

    email_send_result = None

    if send_email:
        email_send_result = send_email_report(
            email_settings=settings["email"],
            subject=build_email_subject(report),
            body=build_email_body(
                report=report,
                report_path=written_html_report_path,
                include_report_path=False,
            ),
            html_body=build_email_html_body(
                report=report,
                report_path=written_html_report_path,
                include_report_path=False,
            ),
            attachment_path=written_html_report_path,
        )

    print()
    print("Scan summary:")
    print(f"Companies enabled: {len(companies)}")
    print(f"Jobs collected: {total_jobs}")
    print(f"Jobs stored: {jobs_stored}")
    print(f"Jobs omitted: {jobs_omitted}")
    print(f"Jobs new: {jobs_new}")
    print(f"Jobs seen: {jobs_seen}")
    print(f"Jobs changed: {jobs_changed}")
    print(f"Collector errors: {len(collector_errors)}")
    print(f"Report written: {written_report_path}")
    print(f"HTML report written: {written_html_report_path}")

    if written_email_preview_path is not None:
        print(f"Email preview written: {written_email_preview_path}")

    if email_send_result is not None:
        print(f"Email send result: {email_send_result.message}")


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
                email_preview_path=args.email_preview,
                send_email=args.send_email
            )
            return

        if args.command == "init-db":
            settings = load_settings()
            db_path = initialize_database(settings["database_path"])
            print(f"Database initialized: {db_path}")
            return

    except ConfigError as error:
        parser.exit(status=1, message=f"Config error: {error}\n")