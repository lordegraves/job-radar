import argparse
from datetime import UTC, datetime
from pathlib import Path

from job_radar.candidate_profile import CandidateProfile, load_candidate_profile
from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.registry import collect_jobs_for_company
from job_radar.compensation import evaluate_compensation
from job_radar.config import ConfigError, load_companies, load_settings
from job_radar.email_sender import send_email_report
from job_radar.email_summary import (
    build_email_body,
    build_email_html_body,
    build_email_subject,
    write_email_preview,
)
from job_radar.history_summary import build_history_summary, format_history_summary
from job_radar.job_history import load_job_history_workbook
from job_radar.reporting import (
    ScanError,
    ScanReport,
    ScoredPosting,
    write_html_report,
    write_markdown_report,
)
from job_radar.normalize import clean_text
from job_radar.resume_loader import load_resume_text, write_normalized_resume_text
from job_radar.resume_match import match_resume_to_posting
from job_radar.scoring import (
    ScoringConfigError,
    classify_location,
    evaluate_review_needed_eligibility,
    evaluate_top_match_eligibility,
    load_scoring_config,
    score_posting,
)
from job_radar.storage import (
    initialize_database,
    upsert_job_history_record,
    upsert_job_posting,
)
from job_radar.validation import validate_configuration


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
        help="Path to company config YAML",
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
        default="config/settings.yaml",
        help="Path to settings.yaml",
    )
    validate_parser.add_argument(
        "--scoring",
        default="config/scoring.yaml",
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

    import_history_parser = subparsers.add_parser(
        "import-history",
        help="Import job history from the tracking workbook",
    )
    import_history_parser.add_argument(
        "--workbook",
        required=True,
        help="Path to job-history.xlsx",
    )
    import_history_parser.add_argument(
        "--settings",
        default="config/settings.yaml",
        help="Path to settings.yaml",
    )

    history_summary_parser = subparsers.add_parser(
        "history-summary",
        help="Summarize imported job history",
    )
    history_summary_parser.add_argument(
        "--settings",
        default="config/settings.yaml",
        help="Path to settings.yaml",
    )

    subparsers.add_parser(
        "init-db",
        help="Initialize the local SQLite database",
    )

    return parser


def _load_candidate_context(settings: dict) -> tuple[object | None, str | None]:
    candidate_profile_path = settings.get("candidate_profile_path")

    if not candidate_profile_path:
        return None, None

    candidate_profile = load_candidate_profile(candidate_profile_path)

    if candidate_profile.resume is None:
        return candidate_profile, None

    resume_text = load_resume_text(candidate_profile.resume.source_path)

    if candidate_profile.resume.normalized_text_path:
        write_normalized_resume_text(
            source_path=candidate_profile.resume.source_path,
            normalized_text_path=candidate_profile.resume.normalized_text_path,
        )

    return candidate_profile, resume_text


def _find_profile_avoid_matches(
    candidate_profile: CandidateProfile | None,
    posting: object,
) -> list[str]:
    if candidate_profile is None:
        return []

    posting_text = clean_text(
        " ".join(
            [
                getattr(posting, "title", "") or "",
                getattr(posting, "description", "") or "",
            ]
        )
    ).lower()

    matches: list[str] = []

    for avoid_term in candidate_profile.avoid:
        normalized_avoid = clean_text(avoid_term.replace("-", " ")).lower()

        if not normalized_avoid:
            continue

        if normalized_avoid == "cleared only roles":
            if _has_cleared_only_signal(posting_text):
                matches.append(avoid_term)
            continue

        if normalized_avoid in posting_text:
            matches.append(avoid_term)

    return _dedupe_preserving_order(matches)


def _has_cleared_only_signal(posting_text: str) -> bool:
    clearance_only_markers = [
        "active secret",
        "active top secret",
        "top secret",
        "ts sci",
        "ts/sci",
        "polygraph",
        "active clearance",
        "security clearance required",
    ]

    return any(marker in posting_text for marker in clearance_only_markers)


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    deduped_values: list[str] = []

    for value in values:
        if value not in deduped_values:
            deduped_values.append(value)

    return deduped_values


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
    candidate_profile, resume_text = _load_candidate_context(settings)

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
                resume_match=match_resume_to_posting(
                    posting=posting,
                    candidate_profile=candidate_profile,
                    resume_text=resume_text,
                ),
                compensation=evaluate_compensation(
                    salary_text=posting.salary_text,
                    compensation_floor_usd=(
                        candidate_profile.compensation_floor_usd
                        if candidate_profile is not None
                        else None
                    ),
                ),
                profile_avoid_matches=_find_profile_avoid_matches(
                    candidate_profile=candidate_profile,
                    posting=posting,
                ),
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


def handle_import_history(
    workbook_path: str,
    settings_path: str,
) -> None:
    settings = load_settings(settings_path)
    database_path = settings["database_path"]
    initialize_database(database_path)

    import_result = load_job_history_workbook(workbook_path)

    imported_count = 0
    updated_count = 0

    for record in import_result.records:
        upsert_result = upsert_job_history_record(database_path, record)

        if upsert_result == "new":
            imported_count += 1
        elif upsert_result == "updated":
            updated_count += 1

    print("Application history import complete")
    print(f"Workbook: {workbook_path}")
    print(f"Database: {database_path}")
    print(f"Rows read: {import_result.rows_read}")
    print(f"Rows imported: {imported_count}")
    print(f"Rows updated: {updated_count}")
    print(f"Rows skipped: {import_result.rows_skipped}")


def handle_history_summary(settings_path: str) -> None:
    settings = load_settings(settings_path)
    database_path = settings["database_path"]
    initialize_database(database_path)

    summary = build_history_summary(database_path)

    print(format_history_summary(summary), end="")


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

        if args.command == "validate":
            handle_validate(
                config_path=args.config,
                settings_path=args.settings,
                scoring_path=args.scoring,
                report_path=args.report,
                email_preview_path=args.email_preview,
            )
            return

        if args.command == "import-history":
            handle_import_history(
                workbook_path=args.workbook,
                settings_path=args.settings,
            )
            return

        if args.command == "history-summary":
            handle_history_summary(settings_path=args.settings)
            return

        if args.command == "init-db":
            settings = load_settings()
            db_path = initialize_database(settings["database_path"])
            print(f"Database initialized: {db_path}")
            return

    except (ConfigError, ScoringConfigError) as error:
        parser.exit(status=1, message=f"Config error: {error}\n")