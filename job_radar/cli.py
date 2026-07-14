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
from job_radar.history_context import build_history_context
from job_radar.history_match import (
    find_history_matches,
    format_history_matches,
    summarize_history_risk,
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
    delete_job_history_record,
    fetch_included_job_history_records,
    initialize_database,
    record_scan_run,
    upsert_job_history_record,
    upsert_job_posting,
)
from job_radar.tracker.tracker_models import ApplicationRecord
from job_radar.tracker.tracker_service import (
    build_application_record_from_history_record,
    get_application_workflow_state,
    should_track_history_record,
)
from job_radar.tracker.tracker_storage import (
    delete_application,
    get_application,
    list_applications,
    update_application_status,
    upsert_application,
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

    history_parser = subparsers.add_parser(
        "history",
        help="Work with imported job history",
    )
    history_subparsers = history_parser.add_subparsers(
        dest="history_command",
        required=True,
    )

    history_import_parser = history_subparsers.add_parser(
        "import",
        help="Import job history from the tracking workbook",
    )
    history_import_parser.add_argument(
        "--workbook",
        required=True,
        help="Path to job-history.xlsx",
    )
    history_import_parser.add_argument(
        "--settings",
        default="config/settings.yaml",
        help="Path to settings.yaml",
    )

    history_summary_group_parser = history_subparsers.add_parser(
        "summary",
        help="Summarize imported job history",
    )
    history_summary_group_parser.add_argument(
        "--settings",
        default="config/settings.yaml",
        help="Path to settings.yaml",
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
        default="config/settings.yaml",
        help="Path to settings.yaml",
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
        "--job-radar-id",
        required=True,
        help="Job Radar ID for the tracked application",
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
        default="config/settings.yaml",
        help="Path to settings.yaml",
    )

    tracker_add_parser = tracker_subparsers.add_parser(
        "add",
        help="Add a tracked application",
    )
    tracker_add_parser.add_argument(
        "--job-radar-id",
        required=True,
        help="Job Radar ID for the tracked application",
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
        default="config/settings.yaml",
        help="Path to settings.yaml",
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


def _import_history_records(
    *,
    database_path: str,
    records: list,
) -> tuple[int, int, int, int, int]:
    history_imported_count = 0
    history_updated_count = 0
    tracker_imported_count = 0
    tracker_updated_count = 0
    tracker_skipped_count = 0

    for record in records:
        tracker_record = build_application_record_from_history_record(record)

        if should_track_history_record(record):
            delete_job_history_record(database_path, record.import_key)

            tracker_upsert_result = upsert_application(database_path, tracker_record)

            if tracker_upsert_result == "new":
                tracker_imported_count += 1
            elif tracker_upsert_result == "updated":
                tracker_updated_count += 1

            continue

        delete_application(database_path, tracker_record.job_radar_id)

        history_upsert_result = upsert_job_history_record(database_path, record)

        if history_upsert_result == "new":
            history_imported_count += 1
        elif history_upsert_result == "updated":
            history_updated_count += 1

        tracker_skipped_count += 1

    return (
        history_imported_count,
        history_updated_count,
        tracker_imported_count,
        tracker_updated_count,
        tracker_skipped_count,
    )


def _import_job_history_for_scan(
    *,
    settings: dict,
    database_path: str,
) -> None:
    workbook_path = settings.get("job_history_workbook_path")

    if not workbook_path:
        return

    if not Path(workbook_path).exists():
        print("Application history import skipped")
        print(f"Workbook: {workbook_path}")
        print("Reason: workbook file does not exist; using existing database history")
        print()
        return

    import_result = load_job_history_workbook(workbook_path)

    (
        imported_count,
        updated_count,
        tracker_imported_count,
        tracker_updated_count,
        tracker_skipped_count,
    ) = _import_history_records(
        database_path=database_path,
        records=import_result.records,
    )

    print("Application history import complete")
    print(f"Workbook: {workbook_path}")
    print(f"Rows read: {import_result.rows_read}")
    print(f"Rows imported: {imported_count}")
    print(f"Rows updated: {updated_count}")
    print(f"Rows skipped: {import_result.rows_skipped}")
    print(f"Tracker rows imported: {tracker_imported_count}")
    print(f"Tracker rows updated: {tracker_updated_count}")
    print(f"Tracker rows skipped: {tracker_skipped_count}")
    print()


def _build_tracker_workflow_summary(database_path: str) -> dict[str, int]:
    workflow_summary: dict[str, int] = {}

    for application in list_applications(database_path):
        workflow_state = get_application_workflow_state(application)
        workflow_summary[workflow_state] = workflow_summary.get(workflow_state, 0) + 1

    return workflow_summary


def _get_application_for_posting(
    *,
    database_path: str,
    tracked_applications: list[ApplicationRecord],
    posting,
) -> ApplicationRecord | None:
    application = get_application(database_path, posting.job_radar_id)

    if application is not None:
        return application

    if not posting.source_url:
        return None

    posting_source_url = posting.source_url.strip()

    for tracked_application in tracked_applications:
        if tracked_application.source_url is None:
            continue

        if tracked_application.source_url.strip() == posting_source_url:
            return tracked_application

    return None


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

    _import_job_history_for_scan(
        settings=settings,
        database_path=database_path,
    )

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

    history_summary = build_history_summary(database_path)
    history_context = build_history_context(history_summary)
    history_records = fetch_included_job_history_records(database_path)
    tracker_workflow_summary = _build_tracker_workflow_summary(database_path)
    tracked_applications = list_applications(database_path)

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

        history_matches = find_history_matches(
            posting=posting,
            history_records=history_records,
        )
        history_risk_level, history_risk_reasons = summarize_history_risk(
            history_matches
        )
        application = _get_application_for_posting(
            database_path=database_path,
            tracked_applications=tracked_applications,
            posting=posting,
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
                history_context=format_history_matches(history_matches),
                history_risk_level=history_risk_level,
                history_risk_reasons=history_risk_reasons,
                # Scan/report reads tracker state only. Newly discovered jobs must
                # not become tracked simply because they scored well.
                application=application,
            )
        )

    scored_postings.sort(key=lambda item: item.score, reverse=True)

    relevant_scored_postings = [
        scored_posting
        for scored_posting in scored_postings
        if scored_posting.top_match_eligible or scored_posting.review_needed_eligible
    ]

    relevant_source_urls = {
        scored_posting.posting.source_url
        for scored_posting in relevant_scored_postings
    }

    omitted_scored_postings = [
        scored_posting
        for scored_posting in scored_postings
        if scored_posting.posting.source_url not in relevant_source_urls
    ]

    jobs_stored = 0
    jobs_omitted = total_jobs - len(relevant_scored_postings)
    new_scored_postings: list[ScoredPosting] = []

    for scored_posting in relevant_scored_postings:
        result = upsert_job_posting(database_path, scored_posting.posting)
        jobs_stored += 1

        if result == "new":
            jobs_new += 1
            new_scored_postings.append(scored_posting)
        elif result == "seen":
            jobs_seen += 1
        elif result == "changed":
            jobs_changed += 1

    generated_at = datetime.now(UTC).isoformat()

    report = ScanReport(
        companies_enabled=len(companies),
        jobs_collected=total_jobs,
        jobs_new=jobs_new,
        jobs_seen=jobs_seen,
        jobs_changed=jobs_changed,
        collector_errors=collector_errors,
        postings=collected_postings,
        scored_postings=relevant_scored_postings,
        new_scored_postings=new_scored_postings,
        omitted_scored_postings=omitted_scored_postings,
        generated_at=generated_at,
        top_match_min_score=scoring_config["top_matches"]["min_score"],
        review_needed_min_score=scoring_config["review_needed"]["min_score"],
        jobs_stored=jobs_stored,
        jobs_omitted=jobs_omitted,
        history_context=history_context,
        tracker_workflow_summary=tracker_workflow_summary,
    )

    record_scan_run(
        database_path=database_path,
        generated_at=generated_at,
        companies_enabled=len(companies),
        jobs_collected=total_jobs,
        actionable_jobs_stored=jobs_stored,
        jobs_not_actionable=jobs_omitted,
        jobs_new=jobs_new,
        jobs_seen=jobs_seen,
        jobs_changed=jobs_changed,
        collector_errors=len(collector_errors),
        top_matches_count=sum(
            1
            for scored_posting in relevant_scored_postings
            if scored_posting.top_match_eligible
        ),
        review_needed_count=sum(
            1
            for scored_posting in relevant_scored_postings
            if scored_posting.review_needed_eligible
        ),
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
    print(f"Actionable jobs stored: {jobs_stored}")
    print(f"Jobs not actionable: {jobs_omitted}")
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

    (
        imported_count,
        updated_count,
        tracker_imported_count,
        tracker_updated_count,
        tracker_skipped_count,
    ) = _import_history_records(
        database_path=database_path,
        records=import_result.records,
    )

    print("Application history import complete")
    print(f"Workbook: {workbook_path}")
    print(f"Database: {database_path}")
    print(f"Rows read: {import_result.rows_read}")
    print(f"Rows imported: {imported_count}")
    print(f"Rows updated: {updated_count}")
    print(f"Rows skipped: {import_result.rows_skipped}")
    print(f"Tracker rows imported: {tracker_imported_count}")
    print(f"Tracker rows updated: {tracker_updated_count}")
    print(f"Tracker rows skipped: {tracker_skipped_count}")


def handle_history_summary(settings_path: str) -> None:
    settings = load_settings(settings_path)
    database_path = settings["database_path"]
    initialize_database(database_path)

    summary = build_history_summary(database_path)

    print(format_history_summary(summary), end="")


def handle_tracker_list(
    settings_path: str,
    *,
    needs_action: bool = False,
    needs_review: bool = False,
) -> None:
    settings = load_settings(settings_path)
    database_path = settings["database_path"]
    initialize_database(database_path)

    applications = list_applications(database_path)

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
        print(f"  Job Radar ID: {application.job_radar_id}")
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
    settings_path: str,
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
    settings = load_settings(settings_path)
    database_path = settings["database_path"]
    initialize_database(database_path)

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
    )

    print("Application tracker entry saved")
    print(f"Database: {database_path}")
    print(f"Result: {result}")
    print(f"Job Radar ID: {job_radar_id}")
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
    settings_path: str,
    *,
    job_radar_id: str,
    status: str,
    follow_up_on: str | None = None,
    applied_on: str | None = None,
    last_activity_on: str | None = None,
    outcome: str | None = None,
    notes: str | None = None,
) -> None:
    settings = load_settings(settings_path)
    database_path = settings["database_path"]
    initialize_database(database_path)

    updated = update_application_status(
        database_path,
        job_radar_id=job_radar_id,
        status=status,
        follow_up_on=follow_up_on,
        outcome=outcome,
        notes=notes,
        applied_on=applied_on,
        last_activity_on=last_activity_on,
    )

    if not updated:
        print("Application tracker update failed")
        print(f"Database: {database_path}")
        print(f"Job Radar ID: {job_radar_id}")
        print("Reason: tracked application was not found")
        return

    print("Application tracker updated")
    print(f"Database: {database_path}")
    print(f"Job Radar ID: {job_radar_id}")
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

        if args.command == "import-history":
            handle_import_history(
                workbook_path=args.workbook,
                settings_path=args.settings,
            )
            return

        if args.command == "history-summary":
            handle_history_summary(settings_path=args.settings)
            return

        if args.command == "history":
            if args.history_command == "import":
                handle_import_history(
                    workbook_path=args.workbook,
                    settings_path=args.settings,
                )
                return

            if args.history_command == "summary":
                handle_history_summary(settings_path=args.settings)
                return

        if args.command == "init-db":
            settings = load_settings()
            db_path = initialize_database(settings["database_path"])
            print(f"Database initialized: {db_path}")
            return

        if args.command == "db":
            if args.db_command == "init":
                settings = load_settings()
                db_path = initialize_database(settings["database_path"])
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

    except (ConfigError, ScoringConfigError) as error:
        parser.exit(status=1, message=f"Config error: {error}\n")

if __name__ == "__main__":
    main()
