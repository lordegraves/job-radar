"""Coordinate the full scan from collection through storage, reports, and email."""

from datetime import UTC, datetime
from pathlib import Path

from job_radar.candidate_profile import CandidateProfile
from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.registry import collect_jobs_for_company
from job_radar.compensation import (
    evaluate_compensation,
    extract_annual_compensation_text,
)
from job_radar.config import ApplicationSettings, load_settings
from job_radar.email_sender import send_email_report
from job_radar.diagnostic_service import (
    classify_collector_failure,
    classify_scan_failure,
)
from job_radar.eligibility import evaluate_practical_eligibility
from job_radar.employer_resolution import resolve_scan_companies
from job_radar.employer_connection_service import record_scan_connection_result
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
from job_radar.job_decision_service import get_decided_job_ids
from job_radar.normalize import clean_text
from job_radar.profile_context import load_active_candidate_context
from job_radar.profile_storage import get_active_profile
from job_radar.profile_scoring import resolve_effective_scoring_config
from job_radar.html_report import write_html_report
from job_radar.report_models import ScanError, ScanReport
from job_radar.report_snapshot import write_report_snapshot
from job_radar.report_view_model import (
    is_potential_top_match_report_posting,
    is_review_needed_report_posting,
    is_top_match_report_posting,
)
from job_radar.evaluation_audit import (
    EVALUATION_AUDIT_NAME,
    TARGETED_EVALUATION_AUDIT_NAME,
    write_evaluation_audit,
)
from job_radar.retention_service import (
    apply_retention_after_report_write,
    archive_before_report_write,
)
from job_radar.raw_scan_export import RAW_SCAN_ARCHIVE_NAME, write_raw_scan_export
from job_radar.runtime_paths import DEFAULT_SCORING_CONFIG_PATH, RuntimePaths
from job_radar.scored_posting import ScoredPosting
from job_radar.resume_match import match_resume_to_posting
from job_radar.scan_lock import acquire_scan_lock
from job_radar.recommendation_policy import (
    evaluate_potential_top_match_eligibility,
    evaluate_review_needed_eligibility,
    evaluate_top_match_eligibility,
)
from job_radar.scoring import (
    classify_location,
    score_posting_with_evidence,
)
from job_radar.scan_diagnostic_log import (
    elapsed_seconds,
    record_scan_diagnostic,
    start_scan_diagnostics,
)
from job_radar.storage import (
    complete_scan_run,
    fail_scan_run,
    fetch_included_job_history_records,
    initialize_database,
    record_scan_error,
    start_scan_run,
    update_scan_run_progress,
    upsert_job_posting,
)
from job_radar.tracker.tracker_models import ApplicationRecord
from job_radar.tracker.tracker_service import get_application_workflow_state
from job_radar.tracker.tracker_storage import get_application, list_applications


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


def _build_tracker_workflow_summary(
    database_path: str,
    *,
    profile_id: str | None = None,
) -> dict[str, int]:
    workflow_summary: dict[str, int] = {}

    for application in list_applications(database_path, profile_id=profile_id):
        workflow_state = get_application_workflow_state(application)
        workflow_summary[workflow_state] = workflow_summary.get(workflow_state, 0) + 1

    return workflow_summary


def _get_application_for_posting(
    *,
    database_path: str,
    tracked_applications: list[ApplicationRecord],
    posting,
    profile_id: str | None = None,
) -> ApplicationRecord | None:
    application = get_application(
        database_path,
        posting.job_radar_id,
        profile_id=profile_id,
    )

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


def _is_storage_relevant_posting(scored_posting: ScoredPosting) -> bool:
    if scored_posting.application is not None:
        return True

    return (
        is_top_match_report_posting(scored_posting)
        or is_potential_top_match_report_posting(scored_posting)
        or scored_posting.location_outlier_eligible
        or is_review_needed_report_posting(scored_posting)
    )


def _exclude_decided_postings(
    scored_postings: list[ScoredPosting],
    decided_job_ids: set[str],
) -> list[ScoredPosting]:
    """Keep an exact saved or passed job out of this profile's future report."""

    return [
        item
        for item in scored_postings
        if item.posting.job_radar_id not in decided_job_ids
    ]


def _record_company_evaluation_diagnostics(
    *,
    logs_path: str,
    scan_run_id: int,
    companies: list[dict],
    scored_postings: list[ScoredPosting],
    decided_job_ids: set[str],
) -> None:
    """Record aggregate outcomes without persisting job or profile contents."""

    for company in companies:
        company_key = str(company["company_key"])
        company_postings = [
            item
            for item in scored_postings
            if item.posting.company_key == company_key
        ]
        undecided_postings = [
            item
            for item in company_postings
            if item.posting.job_radar_id not in decided_job_ids
        ]
        actionable = [
            item
            for item in undecided_postings
            if _is_storage_relevant_posting(item)
        ]
        omitted = [
            item
            for item in undecided_postings
            if not _is_storage_relevant_posting(item)
        ]

        record_scan_diagnostic(
            logs_path,
            event="company_evaluation_completed",
            scan_run_id=scan_run_id,
            stage="scoring",
            company_id=company_key,
            source_type=str(company["source_type"]),
            jobs_found=len(company_postings),
            jobs_decided=len(company_postings) - len(undecided_postings),
            jobs_actionable=len(actionable),
            jobs_not_actionable=len(omitted),
            omitted_critical_gap=sum(
                bool(item.resume_match and item.resume_match.has_critical_gap)
                for item in omitted
            ),
            omitted_practical_mismatch=sum(
                bool(
                    item.eligibility
                    and item.eligibility.status == "not_eligible"
                )
                for item in omitted
            ),
            omitted_profile_exclusion=sum(
                bool(item.profile_avoid_matches)
                for item in omitted
            ),
            omitted_other_fit=sum(
                not bool(item.resume_match and item.resume_match.has_critical_gap)
                and not bool(
                    item.eligibility
                    and item.eligibility.status == "not_eligible"
                )
                and not bool(item.profile_avoid_matches)
                for item in omitted
            ),
            top_matches=sum(
                is_top_match_report_posting(item) for item in actionable
            ),
            potential_top_matches=sum(
                is_potential_top_match_report_posting(item)
                for item in actionable
            ),
            location_outliers=sum(
                item.location_outlier_eligible for item in actionable
            ),
            review_needed=sum(
                is_review_needed_report_posting(item) for item in actionable
            ),
        )


def handle_scan(
    config_path: str,
    settings_path: str,
    report_path: str,
    scoring_path: str = DEFAULT_SCORING_CONFIG_PATH,
    email_preview_path: str | None = None,
    send_email: bool = False,
    base_directory: str | Path | None = None,
    trigger_source: str = "manual",
    selected_employer_ids: list[str] | None = None,
) -> None:
    settings = load_settings(settings_path)
    runtime_paths = RuntimePaths.from_application_settings(
        settings,
        settings_path=settings_path,
        company_config_path=config_path,
        scoring_config_path=scoring_path,
        base_directory=base_directory,
    )
    database_path = runtime_paths.database_path
    resolved_report_path = runtime_paths.resolve(report_path)
    resolved_email_preview_path = runtime_paths.resolve_optional(email_preview_path)

    with acquire_scan_lock(database_path):
        _handle_scan_unlocked(
            config_path=str(runtime_paths.company_config_path),
            settings_path=str(runtime_paths.settings_path),
            settings=settings,
            report_path=str(resolved_report_path),
            scoring_path=str(runtime_paths.scoring_config_path),
            email_preview_path=(
                str(resolved_email_preview_path)
                if resolved_email_preview_path is not None
                else None
            ),
            send_email=send_email,
            database_path=str(database_path),
            logs_path=str(runtime_paths.logs_path),
            base_directory=runtime_paths.base_directory,
            candidate_profile_path=runtime_paths.candidate_profile_path,
            trigger_source=trigger_source,
            selected_employer_ids=selected_employer_ids,
        )


def _handle_scan_unlocked(
    *,
    config_path: str,
    settings_path: str,
    settings: ApplicationSettings,
    report_path: str,
    scoring_path: str,
    email_preview_path: str | None,
    send_email: bool,
    database_path: str,
    logs_path: str,
    base_directory: Path,
    candidate_profile_path: Path | None,
    trigger_source: str,
    selected_employer_ids: list[str] | None,
) -> None:
    initialize_database(database_path)

    companies = resolve_scan_companies(
        database_path,
        config_path,
        selected_employer_ids=(
            set(selected_employer_ids)
            if selected_employer_ids is not None
            else None
        ),
    )

    requested_at = datetime.now(UTC).isoformat()
    active_profile = get_active_profile(database_path)
    scan_run_id = start_scan_run(
        database_path,
        requested_at=requested_at,
        companies_requested=len(companies),
        companies_enabled=len(companies),
        current_stage="configuration",
        profile_id=(
            active_profile.profile_id if active_profile is not None else None
        ),
        trigger_source=trigger_source,
    )

    current_stage = "configuration"
    companies_scanned = 0
    total_jobs = 0
    collector_errors: list[ScanError] = []
    report_status = "not_started"
    email_status = "not_requested"
    diagnostic_started = start_scan_diagnostics(
        logs_path,
        scan_run_id=scan_run_id,
        trigger=trigger_source,
        companies_requested=len(companies),
    )

    try:
        scoring_config = resolve_effective_scoring_config(
            database_path,
            scoring_path,
        )
        candidate_context = load_active_candidate_context(
            database_path,
            candidate_profile_path,
            base_directory=base_directory,
        )
        candidate_profile = candidate_context.candidate_profile
        resume_text = candidate_context.resume_text
        job_preferences = candidate_context.job_preferences
        profile_id = (
            candidate_context.managed_profile.profile_id
            if candidate_context.managed_profile is not None
            else None
        )

        print("Scan requested")
        print(f"Config: {config_path}")
        print(f"Settings: {settings_path}")
        print(f"Report: {report_path}")
        print(f"Database: {database_path}")
        print()
        print("Enabled companies:")

        jobs_new = 0
        jobs_seen = 0
        jobs_changed = 0
        collected_postings = []

        current_stage = "collection"
        update_scan_run_progress(
            database_path,
            scan_run_id=scan_run_id,
            current_stage=current_stage,
        )

        for company_number, company in enumerate(companies, start=1):
            company_key = company["company_key"]
            company_name = company["name"]
            source_type = company["source_type"]

            print(f"- {company_key} ({company_name}) source_type={source_type}")

            try:
                postings = collect_jobs_for_company(company)
            except CollectorError as error:
                diagnostic = classify_collector_failure(error)
                error_type_parts = [diagnostic.category]
                if diagnostic.failure_stage is not None:
                    error_type_parts.append(diagnostic.failure_stage)
                error_type_parts.append("failure")
                diagnostic_error_type = "_".join(error_type_parts)
                record_scan_connection_result(
                    database_path,
                    company_key,
                    failure_category=diagnostic.category,
                    failure_message=diagnostic.message,
                )
                collector_errors.append(
                    ScanError(
                        company_key=company_key,
                        company_name=company_name,
                        source_type=source_type,
                        message=diagnostic.message,
                    )
                )
                record_scan_error(
                    database_path,
                    scan_run_id=scan_run_id,
                    company_key=company_key,
                    source_type=source_type,
                    error_type=diagnostic_error_type,
                    error_message=diagnostic.message,
                )
                companies_scanned += 1
                update_scan_run_progress(
                    database_path,
                    scan_run_id=scan_run_id,
                    current_stage=current_stage,
                    companies_scanned=companies_scanned,
                    jobs_found=total_jobs,
                    collector_errors=len(collector_errors),
                )
                print(f"  ERROR: {diagnostic.message}")
                record_scan_diagnostic(
                    logs_path,
                    event="company_collection_failed",
                    scan_run_id=scan_run_id,
                    stage=current_stage,
                    company_number=company_number,
                    company_id=company_key,
                    source_type=source_type,
                    failure_reason=diagnostic.message,
                    companies_scanned=companies_scanned,
                    jobs_found=total_jobs,
                    collector_errors=len(collector_errors),
                    failure_category=diagnostic.category,
                    failure_stage=diagnostic.failure_stage,
                    elapsed_seconds=elapsed_seconds(diagnostic_started),
                )
                continue

            total_jobs += len(postings)
            record_scan_connection_result(
                database_path,
                company_key,
                job_count=len(postings),
            )
            collected_postings.extend(postings)
            companies_scanned += 1
            update_scan_run_progress(
                database_path,
                scan_run_id=scan_run_id,
                current_stage=current_stage,
                companies_scanned=companies_scanned,
                jobs_found=total_jobs,
                collector_errors=len(collector_errors),
            )
            print(f"  collected_jobs={len(postings)}")
            record_scan_diagnostic(
                logs_path,
                event="company_collection_completed",
                scan_run_id=scan_run_id,
                stage=current_stage,
                company_number=company_number,
                company_id=company_key,
                source_type=source_type,
                companies_scanned=companies_scanned,
                jobs_found=len(postings),
                elapsed_seconds=elapsed_seconds(diagnostic_started),
            )

        current_stage = "scoring"
        update_scan_run_progress(
            database_path,
            scan_run_id=scan_run_id,
            current_stage=current_stage,
            companies_scanned=companies_scanned,
            jobs_found=total_jobs,
            collector_errors=len(collector_errors),
        )

        history_summary = build_history_summary(
            database_path,
            profile_id=profile_id,
        )
        history_context = build_history_context(history_summary)
        history_records = fetch_included_job_history_records(
            database_path,
            profile_id=profile_id,
        )
        tracker_workflow_summary = _build_tracker_workflow_summary(
            database_path,
            profile_id=profile_id,
        )
        tracked_applications = list_applications(
            database_path,
            profile_id=profile_id,
        )

        scored_postings = []

        for posting in collected_postings:
            score, score_evidence = score_posting_with_evidence(
                posting,
                scoring_config,
            )
            reasons = [
                evidence.to_legacy_reason()
                for evidence in score_evidence
            ]
            location_status = classify_location(posting, scoring_config)
            resume_match = match_resume_to_posting(
                posting=posting,
                candidate_profile=candidate_profile,
                resume_text=resume_text,
            )
            top_match_eligible, top_match_reasons = evaluate_top_match_eligibility(
                posting=posting,
                score=score,
                score_reasons=reasons,
                location_status=location_status,
                scoring_config=scoring_config,
                resume_match=resume_match,
            )

            review_needed_eligible = evaluate_review_needed_eligibility(
                score=score,
                score_reasons=reasons,
                location_status=location_status,
                top_match_eligible=top_match_eligible,
                scoring_config=scoring_config,
                resume_match=resume_match,
            )
            potential_top_match_eligible = (
                evaluate_potential_top_match_eligibility(
                    posting=posting,
                    score=score,
                    score_reasons=reasons,
                    location_status=location_status,
                    scoring_config=scoring_config,
                    resume_match=resume_match,
                )
            )

            compensation_text = posting.salary_text or (
                extract_annual_compensation_text(posting.description)
            )
            compensation = evaluate_compensation(
                salary_text=compensation_text,
                compensation_floor_usd=(
                    candidate_profile.compensation_floor_usd
                    if candidate_profile is not None
                    else None
                ),
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
                profile_id=profile_id,
            )

            eligibility = evaluate_practical_eligibility(
                posting=posting,
                preferences=job_preferences,
                compensation=compensation,
            )
            location_outlier_eligible = (
                bool(
                    job_preferences
                    and job_preferences.include_strong_location_outliers
                )
                and potential_top_match_eligible
                and eligibility is not None
                and eligibility.status == "not_eligible"
                and bool(eligibility.reasons)
                and all(
                    reason.code
                    in {
                        "specific_location_outside_selected_areas",
                        "location_outside_selected_areas",
                        "remote_region_outside_selected_areas",
                    }
                    for reason in eligibility.reasons
                )
            )

            scored_postings.append(
                ScoredPosting(
                    posting=posting,
                    score=score,
                    score_reasons=reasons,
                    score_evidence=score_evidence,
                    location_status=location_status,
                    top_match_eligible=top_match_eligible,
                    potential_top_match_eligible=potential_top_match_eligible,
                    location_outlier_eligible=location_outlier_eligible,
                    review_needed_eligible=review_needed_eligible,
                    top_match_reasons=top_match_reasons,
                    resume_match=resume_match,
                    compensation=compensation,
                    eligibility=eligibility,
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
        # Keep the complete evaluation set for the audit before user decisions
        # hide jobs from the current review inbox.
        all_scored_postings = tuple(scored_postings)
        decided_job_ids = get_decided_job_ids(
            database_path,
            profile_id=profile_id,
        )
        _record_company_evaluation_diagnostics(
            logs_path=logs_path,
            scan_run_id=scan_run_id,
            companies=companies,
            scored_postings=scored_postings,
            decided_job_ids=decided_job_ids,
        )
        scored_postings = _exclude_decided_postings(
            scored_postings,
            decided_job_ids,
        )

        relevant_scored_postings = [
            scored_posting
            for scored_posting in scored_postings
            if _is_storage_relevant_posting(scored_posting)
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

        current_stage = "storage"
        update_scan_run_progress(
            database_path,
            scan_run_id=scan_run_id,
            current_stage=current_stage,
            companies_scanned=companies_scanned,
            jobs_found=total_jobs,
            collector_errors=len(collector_errors),
        )

        jobs_stored = 0
        jobs_omitted = total_jobs - len(relevant_scored_postings)
        new_scored_postings: list[ScoredPosting] = []

        for scored_posting in relevant_scored_postings:
            result = upsert_job_posting(
                database_path,
                scored_posting.posting,
                scan_run_id=scan_run_id,
            )
            jobs_stored += 1

            if result == "new":
                jobs_new += 1
                new_scored_postings.append(scored_posting)
            elif result == "seen":
                jobs_seen += 1
            elif result == "changed":
                jobs_changed += 1

        generated_at = datetime.now(UTC).isoformat()
        scan_kind = "selected" if selected_employer_ids else "full"
        evaluation_audit_name = (
            TARGETED_EVALUATION_AUDIT_NAME
            if selected_employer_ids
            else EVALUATION_AUDIT_NAME
        )
        evaluation_audit_path = (
            Path(report_path).parent / evaluation_audit_name
        )

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

        current_stage = "report_generation"
        update_scan_run_progress(
            database_path,
            scan_run_id=scan_run_id,
            current_stage=current_stage,
            companies_scanned=companies_scanned,
            jobs_found=total_jobs,
            collector_errors=len(collector_errors),
        )

        archive_before_report_write(
            html_report_path=Path(report_path).with_suffix(".html"),
            snapshot_path=Path(report_path).with_suffix(".json"),
            email_preview_path=email_preview_path,
            evaluation_audit_path=evaluation_audit_path,
            raw_scan_path=Path(report_path).parent / RAW_SCAN_ARCHIVE_NAME,
        )

        written_html_report_path = write_html_report(
            Path(report_path).with_suffix(".html"),
            report,
        )
        written_snapshot_path = write_report_snapshot(
            Path(report_path).with_suffix(".json"),
            report,
        )
        report_status = "completed"

        written_email_preview_path = None

        if email_preview_path is not None:
            written_email_preview_path = write_email_preview(
                email_preview_path,
                report,
            )

        write_raw_scan_export(
            Path(report_path).parent / RAW_SCAN_ARCHIVE_NAME,
            report,
        )
        evaluation_audit_summary = write_evaluation_audit(
            evaluation_audit_path,
            all_scored_postings,
            decided_job_ids=decided_job_ids,
            generated_at=generated_at,
            scan_kind=scan_kind,
            scan_run_id=scan_run_id,
        )
        # A successful scan promises a durable explanation of every evaluation.
        # Do not finalize a report set when that audit was not actually written.
        if (
            not evaluation_audit_path.is_file()
            or evaluation_audit_path.stat().st_size <= 0
        ):
            raise RuntimeError(
                "The scan evaluation audit was not created. "
                "The scan was not finalized."
            )
        if evaluation_audit_summary.jobs_evaluated != len(
            all_scored_postings
        ):
            raise RuntimeError(
                "The scan evaluation audit is incomplete. "
                "The scan was not finalized."
            )
        if total_jobs > 0 and evaluation_audit_summary.jobs_evaluated == 0:
            raise RuntimeError(
                "Jobs were collected, but no evaluation records were created. "
                "The scan was not finalized."
            )
        apply_retention_after_report_write(
            reports_path=Path(report_path).parent,
            logs_path=logs_path,
            retention=settings.retention,
        )

        email_send_result = None

        if send_email:
            current_stage = "email_delivery"
            update_scan_run_progress(
                database_path,
                scan_run_id=scan_run_id,
                current_stage=current_stage,
                companies_scanned=companies_scanned,
                jobs_found=total_jobs,
                collector_errors=len(collector_errors),
            )
            email_status = "sending"
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
            email_status = (
                "completed" if email_send_result.sent else "failed"
            )

        finished_at = datetime.now(UTC).isoformat()

        top_matches_count = sum(
            1
            for scored_posting in relevant_scored_postings
            if is_top_match_report_posting(scored_posting)
        )
        potential_top_matches_count = sum(
            1
            for scored_posting in relevant_scored_postings
            if is_potential_top_match_report_posting(scored_posting)
        )
        location_outliers_count = sum(
            scored_posting.location_outlier_eligible
            for scored_posting in relevant_scored_postings
        )
        review_needed_count = sum(
            1
            for scored_posting in relevant_scored_postings
            if is_review_needed_report_posting(scored_posting)
        )

        if not complete_scan_run(
            database_path,
            scan_run_id=scan_run_id,
            generated_at=generated_at,
            finished_at=finished_at,
            companies_scanned=companies_scanned,
            jobs_collected=total_jobs,
            actionable_jobs_stored=jobs_stored,
            jobs_not_actionable=jobs_omitted,
            jobs_new=jobs_new,
            jobs_seen=jobs_seen,
            jobs_changed=jobs_changed,
            collector_errors=len(collector_errors),
            top_matches_count=top_matches_count,
            review_needed_count=review_needed_count,
            report_status=report_status,
            email_status=email_status,
        ):
            raise RuntimeError(
                f"Scan run {scan_run_id} could not be marked complete."
            )
        record_scan_diagnostic(
            logs_path,
            event="scan_completed",
            scan_run_id=scan_run_id,
            stage="completed",
            companies_requested=len(companies),
            companies_scanned=companies_scanned,
            jobs_found=total_jobs,
            jobs_stored=jobs_stored,
            jobs_omitted=jobs_omitted,
            jobs_new=jobs_new,
            jobs_seen=jobs_seen,
            jobs_changed=jobs_changed,
            collector_errors=len(collector_errors),
            top_matches=top_matches_count,
            potential_top_matches=potential_top_matches_count,
            location_outliers=location_outliers_count,
            review_needed=review_needed_count,
            report_status=report_status,
            email_status=email_status,
            elapsed_seconds=elapsed_seconds(diagnostic_started),
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
        print(f"HTML report written: {written_html_report_path}")
        print(f"Structured report written: {written_snapshot_path}")

        if written_email_preview_path is not None:
            print(f"Email preview written: {written_email_preview_path}")

        if email_send_result is not None:
            print(f"Email send result: {email_send_result.message}")
    except Exception:
        finished_at = datetime.now(UTC).isoformat()
        diagnostic = classify_scan_failure(current_stage)
        record_scan_error(
            database_path,
            scan_run_id=scan_run_id,
            error_type=f"{diagnostic.category}_failure",
            error_message=diagnostic.message,
        )
        fail_scan_run(
            database_path,
            scan_run_id=scan_run_id,
            finished_at=finished_at,
            failed_stage=current_stage,
            failure_summary=diagnostic.message,
            companies_scanned=companies_scanned,
            jobs_found=total_jobs,
            collector_errors=len(collector_errors),
        )
        record_scan_diagnostic(
            logs_path,
            event="scan_failed",
            scan_run_id=scan_run_id,
            stage=current_stage,
            companies_requested=len(companies),
            companies_scanned=companies_scanned,
            jobs_found=total_jobs,
            collector_errors=len(collector_errors),
            report_status=report_status,
            email_status=email_status,
            failure_category=diagnostic.category,
            elapsed_seconds=elapsed_seconds(diagnostic_started),
        )
        raise

