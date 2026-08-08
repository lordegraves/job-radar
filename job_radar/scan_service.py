"""Coordinate the full scan from collection through storage, reports, and email."""

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
import re
from threading import Lock
from time import monotonic, sleep

from job_radar.candidate_profile import CandidateProfile
from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.detail_page import (
    DETAIL_PAGE_SOURCE_TYPES,
    enrich_from_public_detail_page,
)
from job_radar.collectors.eightfold import enrich_cached_eightfold_posting
from job_radar.collectors.incremental_cache import (
    CACHE_CONFIG_KEY,
    DETAIL_CACHE_MAX_AGE,
    DETAIL_PLANNER_CONFIG_KEY,
    FINGERPRINTS_CONFIG_KEY,
    PROGRESS_CONFIG_KEY,
    REUSED_CONFIG_KEY,
    WARNINGS_CONFIG_KEY,
    WARNING_TYPES_CONFIG_KEY,
    record_collection_warning,
    report_progress,
)
from job_radar.collectors.icims import AUTHORITATIVE_EMPTY_CONFIG_KEY
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
from job_radar.eligibility import EligibilityResult, evaluate_practical_eligibility
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
from job_radar.llm_advisory import LlmAdvisoryError, LlmFitReview, review_job_fit
from job_radar.llm_advisory_cache import (
    advisory_input_hash,
    fetch_cached_advisory,
    store_advisory,
)
from job_radar.models import JobPosting
from job_radar.normalize import clean_text, normalize_job_postings
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
from job_radar.detail_retrieval import build_detail_retrieval_planner
from job_radar.evaluation_audit import (
    EVALUATION_AUDIT_NAME,
    TARGETED_EVALUATION_AUDIT_NAME,
    write_evaluation_audit,
    write_evaluation_trace_log,
)
from job_radar.operational_event_log import record_operational_event
from job_radar.retention_service import (
    apply_retention_after_report_write,
    archive_before_report_write,
)
from job_radar.raw_scan_export import RAW_SCAN_ARCHIVE_NAME, write_raw_scan_export
from job_radar.runtime_paths import DEFAULT_SCORING_CONFIG_PATH, RuntimePaths
from job_radar.scored_posting import ScoredPosting
from job_radar.resume_match import ResumeMatchResult, match_resume_to_posting
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
    fetch_source_posting_cache,
    initialize_database,
    record_scan_error,
    replace_source_posting_cache,
    start_scan_run,
    update_scan_run_progress,
    upsert_job_posting,
)
from job_radar.tracker.tracker_models import ApplicationRecord
from job_radar.tracker.tracker_service import get_application_workflow_state
from job_radar.tracker.tracker_storage import list_applications


_GENERAL_COLLECTION_WORKERS = 2
_LOCATION_OUTLIER_REASON_CODES = {
    "specific_location_outside_selected_areas",
    "location_outside_selected_areas",
    "remote_region_outside_selected_areas",
}


def _should_compare_resume(
    *,
    normalization_state: str | None,
    eligibility: EligibilityResult | None,
    include_location_outliers: bool,
    score: int,
    review_floor: int,
) -> bool:
    """Avoid deep matching when a hard practical rule already decides the job."""

    if normalization_state == "incomplete":
        return False
    if eligibility is None or eligibility.status != "not_eligible":
        return True
    return bool(
        include_location_outliers
        and eligibility.reasons
        and score >= review_floor
        and all(
            reason.code in _LOCATION_OUTLIER_REASON_CODES
            for reason in eligibility.reasons
        )
    )
_WORKDAY_COLLECTION_WORKERS = 2
_EIGHTFOLD_COLLECTION_WORKERS = 1
_COLLECTOR_STARTED_AT_CONFIG_KEY = "_collector_started_at"
_COLLECTION_RETRY_DELAY_SECONDS = 2.0
_FALLBACK_DETAIL_MAX_ATTEMPTS = 10
_FALLBACK_DETAIL_FAILURE_LIMIT = 3


def _collection_pool_name(source_type: str) -> str:
    if source_type == "workday":
        return "workday"
    if source_type == "eightfold":
        return "eightfold"
    return "general"


def _collect_company_with_start_progress(
    collection_config: dict[str, object],
) -> list[JobPosting]:
    # A future may wait behind another tenant. Record the real collector start
    # so per-company diagnostics do not mislabel worker-queue time as source time.
    collection_config[_COLLECTOR_STARTED_AT_CONFIG_KEY] = monotonic()
    callback = collection_config.get(PROGRESS_CONFIG_KEY)
    if callable(callback):
        callback("Reading company job source")
    try:
        return collect_jobs_for_company(collection_config)
    except CollectorError as first_error:
        diagnostic = classify_collector_failure(first_error)
        source_type = str(collection_config.get("source_type") or "")
        # Eightfold already applies a larger source-specific retry budget.
        # Other collectors get one bounded retry before cache fallback.
        if diagnostic.category == "network" and source_type != "eightfold":
            report_progress(collection_config, "Retrying company job source")
            sleep(_COLLECTION_RETRY_DELAY_SECONDS)
            try:
                return collect_jobs_for_company(collection_config)
            except CollectorError as retry_error:
                diagnostic = classify_collector_failure(retry_error)
                if diagnostic.category != "network":
                    raise
        cached_postings = _fresh_cached_fallback_postings(collection_config)
        if diagnostic.category != "network" or not cached_postings:
            raise
        complete_count = sum(
            posting.normalization_state == "complete" for posting in cached_postings
        )
        incomplete_count = sum(
            posting.normalization_state == "incomplete" for posting in cached_postings
        )
        message = (
            "Junior temporarily could not refresh this source. It recovered "
            f"{complete_count} complete cached listing(s)"
        )
        if incomplete_count:
            message += (
                f" and visibly withheld {incomplete_count} plausible cached "
                "listing(s) whose descriptions remain incomplete"
            )
        message += "."
        record_collection_warning(
            collection_config,
            message,
            warning_type="source_cache_fallback",
        )
        return cached_postings


def _fresh_cached_fallback_postings(
    collection_config: dict[str, object],
) -> list[JobPosting]:
    """Return only recently verified cached records after a transient outage."""

    cache = collection_config.get(CACHE_CONFIG_KEY)
    if not isinstance(cache, dict):
        return []
    now = datetime.now(UTC)
    postings: list[JobPosting] = []
    detail_attempts = 0
    consecutive_detail_failures = 0
    for cached in cache.values():
        posting = getattr(cached, "posting", None)
        verified_text = getattr(cached, "detail_verified_at", None)
        if not isinstance(posting, JobPosting) or not isinstance(verified_text, str):
            continue
        try:
            verified_at = datetime.fromisoformat(verified_text.replace("Z", "+00:00"))
        except ValueError:
            continue
        if verified_at.tzinfo is None:
            verified_at = verified_at.replace(tzinfo=UTC)
        if now - verified_at > DETAIL_CACHE_MAX_AGE:
            continue
        posting = normalize_job_postings([posting])[0]
        planner = collection_config.get(DETAIL_PLANNER_CONFIG_KEY)
        decision = planner(posting.title, posting.location) if callable(planner) else None
        if posting.normalization_state == "incomplete" and decision is not None:
            if not decision.retrieve:
                posting = replace(
                    posting,
                    detail_retrieval_reason=decision.reason,
                    detail_retrieval_state="skipped_unrelated",
                )
            elif (
                detail_attempts < _FALLBACK_DETAIL_MAX_ATTEMPTS
                and consecutive_detail_failures < _FALLBACK_DETAIL_FAILURE_LIMIT
            ):
                original = posting
                if posting.source_type == "eightfold":
                    posting = enrich_cached_eightfold_posting(
                        posting,
                        collection_config,
                    )
                elif posting.source_type in DETAIL_PAGE_SOURCE_TYPES:
                    posting = enrich_from_public_detail_page(
                        posting,
                        source_api_url=(
                            str(collection_config.get("source_url") or "") or None
                        ),
                    )
                detail_attempts += 1
                if posting.detail_retrieval_state == "unavailable":
                    consecutive_detail_failures += 1
                elif posting.description and posting.description != original.description:
                    consecutive_detail_failures = 0
            posting = normalize_job_postings([posting])[0]
        fallback_state = (
            "cached_source_fallback"
            if posting.normalization_state == "complete"
            else (
                "skipped_unrelated"
                if posting.normalization_state == "skipped_unrelated"
                else "cached_source_fallback_incomplete"
            )
        )
        postings.append(
            replace(
                posting,
                detail_retrieval_state=fallback_state,
                normalization_issues=tuple(
                    dict.fromkeys(
                        (*posting.normalization_issues, "source_cache_fallback")
                    )
                ),
            )
        )
    return normalize_job_postings(postings)


def _find_profile_avoid_matches(
    candidate_profile: CandidateProfile | None,
    posting: object,
) -> list[str]:
    if candidate_profile is None:
        return []

    title_text = clean_text(getattr(posting, "title", "") or "").lower()
    description_text = clean_text(
        getattr(posting, "description", "") or ""
    ).lower()
    posting_text = f"{title_text} {description_text}"

    matches: list[str] = []

    for avoid_term in candidate_profile.avoid:
        normalized_avoid = clean_text(avoid_term.replace("-", " ")).lower()

        if not normalized_avoid:
            continue

        if normalized_avoid == "cleared only roles":
            if _has_cleared_only_signal(posting_text):
                matches.append(avoid_term)
            continue

        if _is_central_profile_exclusion(
            normalized_avoid,
            title_text=title_text,
            description_text=description_text,
        ):
            matches.append(avoid_term)

    return _dedupe_preserving_order(matches)


def _is_central_profile_exclusion(
    exclusion: str,
    *,
    title_text: str,
    description_text: str,
) -> bool:
    """Do not reject a job for an incidental phrase buried in its description."""

    phrase = re.escape(exclusion).replace(r"\ ", r"\s+")
    bounded_phrase = rf"(?<!\w){phrase}(?!\w)"
    if re.search(bounded_phrase, title_text):
        return True

    central_markers = (
        r"responsible\s+for",
        r"primary\s+(?:responsibility|focus)(?:\s+is)?",
        r"core\s+(?:responsibility|focus)(?:\s+is)?",
        r"this\s+role\s+(?:owns|will\s+own|is\s+responsible\s+for)",
    )
    central_pattern = (
        rf"(?:{'|'.join(central_markers)})"
        rf"[\s:,-]{{1,12}}.{{0,80}}{bounded_phrase}"
    )
    return re.search(central_pattern, description_text) is not None


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
    applications_by_job_id: dict[str, ApplicationRecord],
    applications_by_source_url: dict[str, ApplicationRecord],
    posting,
) -> ApplicationRecord | None:
    application = applications_by_job_id.get(posting.job_radar_id)
    if application is not None:
        return application

    if not posting.source_url:
        return None
    return applications_by_source_url.get(posting.source_url.strip())


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


def _apply_normalization_quality_gate(
    posting: JobPosting,
    *,
    top_match_eligible: bool,
    review_needed_eligible: bool,
    potential_top_match_eligible: bool,
) -> tuple[bool, bool, bool]:
    """Prevent incomplete source evidence from becoming a recommendation."""

    if posting.normalization_state != "incomplete":
        return (
            top_match_eligible,
            review_needed_eligible,
            potential_top_match_eligible,
        )
    return False, False, False


def _augment_ambiguous_jobs_with_llm(
    scored_postings: list[ScoredPosting],
    *,
    settings: ApplicationSettings,
    database_path: str,
    profile_id: str | None,
    resume_text: str | None,
    scoring_config: dict[str, object],
) -> tuple[list[ScoredPosting], int, int, int]:
    """Review a bounded plausible set; hard eligibility remains unchanged."""

    if (
        not settings.llm.enabled
        or not profile_id
        or not resume_text
    ):
        return scored_postings, 0, 0, 0
    review_floor = int(scoring_config["review_needed"]["min_score"])
    candidates = [
        (index, item)
        for index, item in enumerate(scored_postings)
        if item.resume_match is not None
        and item.posting.normalization_state == "complete"
        and item.score >= review_floor
        and not (
            item.eligibility is not None
            and item.eligibility.status == "not_eligible"
        )
        and item.application is None
    ]
    candidates.sort(key=lambda entry: entry[1].score, reverse=True)
    candidates = candidates[: settings.llm.max_reviews_per_scan]
    if not candidates:
        return scored_postings, 0, 0, 0

    def perform(entry: tuple[int, ScoredPosting]):
        index, item = entry
        deterministic = item.resume_match
        if deterministic is None:
            return index, None, False, False
        input_hash = advisory_input_hash(
            settings=settings.llm,
            posting=item.posting,
            resume_text=resume_text,
            deterministic_match=deterministic,
        )
        cached = fetch_cached_advisory(
            database_path,
            profile_id=profile_id,
            job_radar_id=item.posting.job_radar_id,
            input_hash=input_hash,
        )
        if cached is not None:
            return index, cached, True, False
        try:
            review = review_job_fit(
                settings=settings.llm,
                posting=item.posting,
                resume_text=resume_text,
                deterministic_match=deterministic,
            )
        except LlmAdvisoryError:
            return index, None, False, True
        store_advisory(
            database_path,
            profile_id=profile_id,
            job_radar_id=item.posting.job_radar_id,
            input_hash=input_hash,
            review=review,
        )
        return index, review, False, False

    reviewed = reused = failed = 0
    updated = list(scored_postings)
    with ThreadPoolExecutor(max_workers=min(3, len(candidates))) as executor:
        for index, review, was_reused, did_fail in executor.map(perform, candidates):
            reused += int(was_reused)
            failed += int(did_fail)
            if review is None:
                continue
            reviewed += int(not was_reused)
            updated[index] = _apply_llm_fit_review(
                updated[index],
                review=review,
                scoring_config=scoring_config,
            )
    return updated, reviewed, reused, failed


def _apply_llm_fit_review(
    item: ScoredPosting,
    *,
    review: LlmFitReview,
    scoring_config: dict[str, object],
) -> ScoredPosting:
    """Replace only professional-fit evidence, never practical eligibility."""

    deterministic = item.resume_match
    if deterministic is None:
        return item
    gaps = [gap.summary for gap in review.material_gaps]
    label = {
        "strong": "Strong",
        "plausible": "Moderate",
        "weak": "Poor Fit",
    }[review.fit_assessment]
    merged_match = ResumeMatchResult(
        label=label,
        evidence=list(review.evidence) or deterministic.evidence,
        gaps=gaps,
        critical_gaps=(gaps if review.fit_assessment == "weak" else []),
        requirements_reviewed=deterministic.requirements_reviewed,
    )
    top, top_reasons = evaluate_top_match_eligibility(
        posting=item.posting,
        score=item.score,
        score_reasons=item.score_reasons,
        location_status=item.location_status,
        scoring_config=scoring_config,
        resume_match=merged_match,
    )
    review_needed = evaluate_review_needed_eligibility(
        score=item.score,
        score_reasons=item.score_reasons,
        location_status=item.location_status,
        top_match_eligible=top,
        scoring_config=scoring_config,
        resume_match=merged_match,
    )
    potential = evaluate_potential_top_match_eligibility(
        posting=item.posting,
        score=item.score,
        score_reasons=item.score_reasons,
        location_status=item.location_status,
        scoring_config=scoring_config,
        resume_match=merged_match,
    )
    top, review_needed, potential = _apply_normalization_quality_gate(
        item.posting,
        top_match_eligible=top,
        review_needed_eligible=review_needed,
        potential_top_match_eligible=potential,
    )
    return replace(
        item,
        resume_match=merged_match,
        top_match_eligible=top,
        review_needed_eligible=review_needed,
        potential_top_match_eligible=potential,
        top_match_reasons=top_reasons,
        llm_review=review,
        deterministic_resume_match=deterministic,
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

    # A targeted validation scan must never replace the durable full-scan
    # inbox. Protect that boundary here as well as in the web route so every
    # caller (GUI, CLI, or a future launcher) gets the same safe behavior.
    if selected_employer_ids is not None:
        if resolved_report_path.name == "target-scan.html":
            resolved_report_path = (
                resolved_report_path.parent / "targeted-scan.html"
            )
        if (
            resolved_email_preview_path is not None
            and resolved_email_preview_path.name
            == "target-email-preview.txt"
        ):
            resolved_email_preview_path = (
                resolved_email_preview_path.parent
                / "targeted-email-preview.txt"
            )

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
        detail_retrieval_planner, _detail_planner_signature = (
            build_detail_retrieval_planner(candidate_profile, scoring_config)
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
        collected_by_company: dict[int, list[JobPosting]] = {}

        current_stage = "collection"
        update_scan_run_progress(
            database_path,
            scan_run_id=scan_run_id,
            current_stage=current_stage,
        )

        progress_lock = Lock()
        future_context: dict[
            Future[list[JobPosting]],
            tuple[int, dict[str, object], dict[str, object], float],
        ] = {}

        # Separate pools prevent a queued rate-limited ATS tenant from occupying
        # a general worker while it waits. Eightfold remains serialized; Workday
        # gets modest overlap; other independent sources share two workers.
        with (
            ThreadPoolExecutor(
                max_workers=_GENERAL_COLLECTION_WORKERS
            ) as general_executor,
            ThreadPoolExecutor(
                max_workers=_WORKDAY_COLLECTION_WORKERS
            ) as workday_executor,
            ThreadPoolExecutor(
                max_workers=_EIGHTFOLD_COLLECTION_WORKERS
            ) as eightfold_executor,
        ):
            for company_number, company in enumerate(companies, start=1):
                company_key = company["company_key"]
                company_name = company["name"]
                source_type = company["source_type"]
                collection_config = dict(company)
                collection_config[CACHE_CONFIG_KEY] = fetch_source_posting_cache(
                    database_path,
                    str(company_key),
                    str(source_type),
                )
                collection_config[DETAIL_PLANNER_CONFIG_KEY] = (
                    detail_retrieval_planner
                )
                last_progress_write = [0.0]

                def report_collection_progress(
                    operation: str,
                    *,
                    number: int = company_number,
                    name: str = str(company_name),
                    source: str = str(source_type),
                    last_write: list[float] = last_progress_write,
                ) -> None:
                    now = monotonic()
                    with progress_lock:
                        if now - last_write[0] < 1.0:
                            return
                        last_write[0] = now
                        update_scan_run_progress(
                            database_path,
                            scan_run_id=scan_run_id,
                            current_stage="collection",
                            companies_scanned=companies_scanned,
                            jobs_found=total_jobs,
                            collector_errors=len(collector_errors),
                            current_company_name=name,
                            current_company_number=number,
                            current_source_type=source,
                            current_operation=operation,
                        )

                collection_config[PROGRESS_CONFIG_KEY] = report_collection_progress
                pool_name = _collection_pool_name(str(source_type))
                source_executor = general_executor
                if pool_name == "workday":
                    source_executor = workday_executor
                elif pool_name == "eightfold":
                    source_executor = eightfold_executor
                future = source_executor.submit(
                    _collect_company_with_start_progress,
                    collection_config,
                )
                future_context[future] = (
                    company_number,
                    company,
                    collection_config,
                    monotonic(),
                )

            for future in as_completed(future_context):
                (
                    company_number,
                    company,
                    collection_config,
                    company_started,
                ) = future_context[future]
                company_key = company["company_key"]
                company_name = company["name"]
                source_type = company["source_type"]
                collector_started = collection_config.get(
                    _COLLECTOR_STARTED_AT_CONFIG_KEY,
                    company_started,
                )
                if not isinstance(collector_started, (int, float)):
                    collector_started = company_started
                company_queue_seconds = round(
                    max(0.0, float(collector_started) - company_started),
                    3,
                )
                print(
                    f"- {company_key} ({company_name}) "
                    f"source_type={source_type}"
                )

                try:
                    postings = future.result()
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
                        company_queue_seconds=company_queue_seconds,
                        company_elapsed_seconds=elapsed_seconds(
                            float(collector_started)
                        ),
                        elapsed_seconds=elapsed_seconds(diagnostic_started),
                    )
                    continue

                total_jobs += len(postings)
                observed_at = datetime.now(UTC).isoformat()
                listing_fingerprints = collection_config.get(
                    FINGERPRINTS_CONFIG_KEY,
                    {},
                )
                reused_identities = collection_config.get(REUSED_CONFIG_KEY, set())
                replace_source_posting_cache(
                    database_path,
                    company_key=str(company_key),
                    company_name=str(company_name),
                    source_type=str(source_type),
                    postings=postings,
                    listing_fingerprints=(
                        listing_fingerprints
                        if isinstance(listing_fingerprints, dict)
                        else {}
                    ),
                    reused_identities=(
                        reused_identities
                        if isinstance(reused_identities, set)
                        else set()
                    ),
                    observed_at=observed_at,
                )
                record_scan_connection_result(
                    database_path,
                    company_key,
                    job_count=len(postings),
                    confirmed_empty=bool(
                        collection_config.get(
                            AUTHORITATIVE_EMPTY_CONFIG_KEY
                        )
                    )
                    or source_type == "greenhouse",
                )
                collection_warnings = collection_config.get(WARNINGS_CONFIG_KEY, [])
                warning_types = collection_config.get(WARNING_TYPES_CONFIG_KEY, {})
                if isinstance(collection_warnings, list):
                    for warning in collection_warnings:
                        message = str(warning)
                        collector_errors.append(
                            ScanError(
                                company_key=company_key,
                                company_name=company_name,
                                source_type=source_type,
                                message=message,
                            )
                        )
                        record_scan_error(
                            database_path,
                            scan_run_id=scan_run_id,
                            company_key=company_key,
                            source_type=source_type,
                            error_type=(
                                str(warning_types.get(message))
                                if isinstance(warning_types, dict)
                                and warning_types.get(message)
                                else "incomplete_position_detail_response_failure"
                            ),
                            error_message=message,
                        )
                collected_by_company[company_number] = postings
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
                    jobs_reused=len(reused_identities),
                    company_queue_seconds=company_queue_seconds,
                    company_elapsed_seconds=elapsed_seconds(float(collector_started)),
                    elapsed_seconds=elapsed_seconds(diagnostic_started),
                )

        for company_number in sorted(collected_by_company):
            collected_postings.extend(collected_by_company[company_number])

        current_stage = "scoring"
        scoring_started = monotonic()
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
        applications_by_job_id = {
            application.job_radar_id: application
            for application in tracked_applications
        }
        applications_by_source_url = {
            application.source_url.strip(): application
            for application in tracked_applications
            if application.source_url and application.source_url.strip()
        }

        scored_postings = []

        scoring_total = len(collected_postings)
        scoring_last_progress = scoring_started
        for scoring_number, posting in enumerate(collected_postings, start=1):
            score, score_evidence = score_posting_with_evidence(
                posting,
                scoring_config,
            )
            reasons = [
                evidence.to_legacy_reason()
                for evidence in score_evidence
            ]
            location_status = classify_location(posting, scoring_config)
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
            eligibility = evaluate_practical_eligibility(
                posting=posting,
                preferences=job_preferences,
                compensation=compensation,
            )
            skip_resume_comparison = not _should_compare_resume(
                normalization_state=posting.normalization_state,
                eligibility=eligibility,
                include_location_outliers=bool(
                    job_preferences
                    and job_preferences.include_strong_location_outliers
                ),
                score=score,
                review_floor=int(scoring_config["review_needed"]["min_score"]),
            )
            resume_match = (
                None
                if skip_resume_comparison
                else match_resume_to_posting(
                    posting=posting,
                    candidate_profile=candidate_profile,
                    resume_text=resume_text,
                )
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

            history_matches = find_history_matches(
                posting=posting,
                history_records=history_records,
            )
            history_risk_level, history_risk_reasons = summarize_history_risk(
                history_matches
            )
            application = _get_application_for_posting(
                applications_by_job_id=applications_by_job_id,
                applications_by_source_url=applications_by_source_url,
                posting=posting,
            )

            (
                top_match_eligible,
                review_needed_eligible,
                potential_top_match_eligible,
            ) = _apply_normalization_quality_gate(
                posting,
                top_match_eligible=top_match_eligible,
                review_needed_eligible=review_needed_eligible,
                potential_top_match_eligible=potential_top_match_eligible,
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

            # Keep progress visible and hand time back to the operating system
            # during very large scans. This does not change evaluation order or
            # decisions; it prevents one uninterrupted scoring loop from making
            # the desktop feel locked.
            now = monotonic()
            if scoring_number == scoring_total or now - scoring_last_progress >= 1.0:
                update_scan_run_progress(
                    database_path,
                    scan_run_id=scan_run_id,
                    current_stage=current_stage,
                    companies_scanned=companies_scanned,
                    jobs_found=total_jobs,
                    collector_errors=len(collector_errors),
                    current_operation=(
                        f"Evaluating job {scoring_number:,} of {scoring_total:,}"
                    ),
                )
                scoring_last_progress = now
                sleep(0.001)

        # AI assistance is deliberately user-requested per job. Enabling it must
        # never add paid provider calls, latency, or nondeterminism to a scan.
        llm_reviewed = llm_reused = llm_failed = 0

        record_scan_diagnostic(
            logs_path,
            event="scan_evaluation_completed",
            scan_run_id=scan_run_id,
            stage=current_stage,
            jobs_found=len(scored_postings),
            phase_elapsed_seconds=elapsed_seconds(scoring_started),
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
        raw_scan_name = (
            "targeted-scan-raw.zip"
            if selected_employer_ids
            else RAW_SCAN_ARCHIVE_NAME
        )
        raw_scan_path = Path(report_path).parent / raw_scan_name

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
            llm_jobs_reviewed=llm_reviewed,
            llm_reviews_reused=llm_reused,
            llm_failures=llm_failed,
        )

        current_stage = "report_generation"
        report_started = monotonic()
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
            raw_scan_path=raw_scan_path,
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
            raw_scan_path,
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
        write_evaluation_trace_log(
            logs_path,
            all_scored_postings,
            scan_run_id=scan_run_id,
            decided_job_ids=decided_job_ids,
            generated_at=generated_at,
        )
        record_scan_diagnostic(
            logs_path,
            event="scan_report_generation_completed",
            scan_run_id=scan_run_id,
            stage=current_stage,
            jobs_found=total_jobs,
            phase_elapsed_seconds=elapsed_seconds(report_started),
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
    except Exception as error:
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
        record_operational_event(
            logs_path,
            kind="errors",
            subsystem="scan",
            event="scan_failed",
            severity="error",
            fields={
                "scan_run_id": scan_run_id,
                "stage": current_stage,
                "error_type": type(error).__name__,
                "failure_category": diagnostic.category,
                "companies_scanned": companies_scanned,
                "jobs_found": total_jobs,
            },
        )
        raise

