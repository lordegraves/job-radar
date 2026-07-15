from datetime import UTC, datetime
from pathlib import Path

from job_radar.candidate_profile import CandidateProfile, load_candidate_profile
from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.registry import collect_jobs_for_company
from job_radar.compensation import evaluate_compensation
from job_radar.config import load_companies, load_settings
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
from job_radar.history_summary import build_history_summary
from job_radar.job_history import load_job_history_workbook
from job_radar.normalize import clean_text
from job_radar.reporting import (
    ScanError,
    ScanReport,
    ScoredPosting,
    write_html_report,
    write_markdown_report,
)
from job_radar.resume_loader import load_resume_text, write_normalized_resume_text
from job_radar.resume_match import match_resume_to_posting
from job_radar.scoring import (
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
    upsert_application,
)


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
