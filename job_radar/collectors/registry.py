"""Route each configured company to the collector for its recruiting platform."""

from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from job_radar.collectors.ashby import collect_ashby_jobs
from job_radar.collectors.greenhouse import CollectorError, collect_greenhouse_jobs
from job_radar.collectors.adaptive_html import collect_adaptive_html_jobs
from job_radar.collectors.talentbrew import collect_talentbrew_jobs
from job_radar.collectors.icims import (
    AUTHORITATIVE_EMPTY_CONFIG_KEY,
    collect_icims_jobs,
)
from job_radar.collectors.jibe import collect_jibe_jobs
from job_radar.collectors.lever import collect_lever_jobs
from job_radar.collectors.usajobs import collect_usajobs
from job_radar.collectors.workday import collect_workday_jobs
from job_radar.collectors.jobsyn import collect_jobsyn_jobs
from job_radar.collectors.oracle_hcm import collect_oracle_hcm_jobs
from job_radar.collectors.smartrecruiters import collect_smartrecruiters_jobs
from job_radar.collectors.selectminds import collect_selectminds_jobs
from job_radar.collectors.phenom import collect_phenom_jobs
from job_radar.collectors.rippling import collect_rippling_jobs
from job_radar.collectors.schoolspring import collect_schoolspring_jobs
from job_radar.collectors.dayforce import collect_dayforce_jobs
from job_radar.collectors.detail_page import (
    DETAIL_PAGE_SOURCE_TYPES,
    enrich_from_public_detail_page,
)
from job_radar.collectors.adp import collect_adp_jobs
from job_radar.collectors.activate import collect_activate_jobs
from job_radar.collectors.weka import collect_weka_jobs
from job_radar.collectors.recruitee import collect_recruitee_jobs
from job_radar.collectors.eightfold import collect_eightfold_jobs
from job_radar.collectors.ukg import collect_ukg_jobs
from job_radar.collectors.google_careers import collect_google_careers_jobs
from job_radar.collectors.incremental_cache import (
    CACHE_CONFIG_KEY,
    DETAIL_CACHE_MAX_AGE,
    DETAIL_PLANNER_CONFIG_KEY,
    record_collection_warning,
)
from job_radar.detail_retrieval import DetailRetrievalDecision
from job_radar.models import JobPosting
from job_radar.normalize import normalize_job_posting, normalize_job_postings


def collect_jobs_for_company(company_config: dict[str, Any]) -> list[JobPosting]:
    source_type = company_config.get("source_type")

    postings: list[JobPosting]

    if source_type == "greenhouse":
        postings = collect_greenhouse_jobs(company_config)

    elif source_type == "lever":
        postings = collect_lever_jobs(company_config)

    elif source_type == "ashby":
        postings = collect_ashby_jobs(company_config)

    elif source_type == "workday":
        postings = collect_workday_jobs(company_config)

    elif source_type == "usajobs":
        postings = collect_usajobs(company_config)

    elif source_type == "icims":
        postings = collect_icims_jobs(company_config)

    elif source_type == "jibe":
        postings = collect_jibe_jobs(company_config)

    elif source_type == "html":
        postings = collect_adaptive_html_jobs(company_config)

    elif source_type == "talentbrew":
        postings = collect_talentbrew_jobs(company_config)
    
    elif source_type == "jobsyn":
        postings = collect_jobsyn_jobs(company_config)
    
    elif source_type == "oracle_hcm":
        postings = collect_oracle_hcm_jobs(company_config)
    
    elif source_type == "smartrecruiters":
        postings = collect_smartrecruiters_jobs(company_config)
    
    elif source_type == "selectminds":
        postings = collect_selectminds_jobs(company_config)
    
    elif source_type == "phenom":
        postings = collect_phenom_jobs(company_config)

    elif source_type == "rippling":
        postings = collect_rippling_jobs(company_config)

    elif source_type == "schoolspring":
        postings = collect_schoolspring_jobs(company_config)

    elif source_type == "dayforce":
        postings = collect_dayforce_jobs(company_config)
    
    elif source_type == "adp":
        postings = collect_adp_jobs(company_config)

    elif source_type == "activate":
        postings = collect_activate_jobs(company_config)

    elif source_type == "weka":
        postings = collect_weka_jobs(company_config)

    elif source_type == "recruitee":
        postings = collect_recruitee_jobs(company_config)

    elif source_type == "eightfold":
        postings = collect_eightfold_jobs(company_config)

    elif source_type == "ukg":
        postings = collect_ukg_jobs(company_config)

    elif source_type == "google_careers":
        postings = collect_google_careers_jobs(company_config)

    else:
        raise CollectorError(
            f"No collector implemented for source_type={source_type} "
            f"company={company_config.get('company_key')}"
        )

    normalized = normalize_job_postings(postings)
    planner = company_config.get(DETAIL_PLANNER_CONFIG_KEY)
    def enrich(posting: JobPosting) -> JobPosting:
        if posting.normalization_state != "incomplete":
            return posting
        decision = (
            planner(posting.title, posting.location)
            if callable(planner)
            else DetailRetrievalDecision(True, "Complete description required.")
        )
        if not decision.retrieve:
            return normalize_job_posting(
                replace(
                    posting,
                    detail_retrieval_reason=decision.reason,
                    detail_retrieval_state="skipped_unrelated",
                )
            )
        if posting.source_type in DETAIL_PAGE_SOURCE_TYPES:
            cached_detail = _recent_cached_detail(posting, company_config)
            posting = normalize_job_posting(
                cached_detail
                or enrich_from_public_detail_page(
                    posting,
                    source_api_url=str(company_config.get("source_url") or "") or None,
                )
            )
        return posting

    if source_type == "oracle_hcm":
        # Oracle detail responses are independent. A small tenant-local pool
        # avoids hundreds of sequential requests without creating an
        # aggressive burst that could trigger employer throttling.
        worker_count = min(6, max(1, len(normalized)))
        with ThreadPoolExecutor(max_workers=worker_count) as detail_executor:
            normalized = list(detail_executor.map(enrich, normalized))
    else:
        normalized = [enrich(posting) for posting in normalized]
    plausible_incomplete_count = sum(
        posting.normalization_state == "incomplete"
        and posting.detail_retrieval_state != "skipped_unrelated"
        for posting in normalized
    )
    if plausible_incomplete_count:
        record_collection_warning(
            company_config,
            f"Junior collected {plausible_incomplete_count} job listing(s) selected "
            "for description retrieval without enough "
            "description content for a complete qualification assessment.",
            warning_type="normalization_incomplete_description",
        )
    # A successful Greenhouse jobs-list response is authoritative even when its
    # jobs array is empty. A missing or retired board returns an HTTP failure,
    # so warning on a valid empty array incorrectly labels employers such as
    # Voxel51 as broken when they simply have no openings today.
    authoritative_empty = bool(
        source_type == "icims"
        and company_config.get(AUTHORITATIVE_EMPTY_CONFIG_KEY)
    )
    if not normalized and source_type != "greenhouse" and not authoritative_empty:
        message = (
            "Junior reached this company's recruiting source, but it returned no "
            "discoverable job listings. The employer may have no openings, or the "
            "public listing index may be unavailable even while individual posting "
            "links still work. Junior cannot safely discover unlisted jobs until "
            "the employer restores or replaces that index."
            if source_type == "icims"
            else "Junior received no current job listings. The company may have no "
            "openings, or its recruiting source may have changed."
        )
        record_collection_warning(
            company_config,
            message,
            warning_type="empty_source_result",
        )
    return normalized


def _recent_cached_detail(
    posting: JobPosting,
    company_config: dict[str, Any],
) -> JobPosting | None:
    """Reuse unchanged complete public detail for a bounded seven-day window."""

    cache = company_config.get(CACHE_CONFIG_KEY)
    identity = posting.source_job_id or posting.source_url
    if not isinstance(cache, dict) or not identity:
        return None
    cached = cache.get(identity)
    cached_posting = getattr(cached, "posting", None)
    verified_text = getattr(cached, "detail_verified_at", None)
    if not isinstance(cached_posting, JobPosting) or not isinstance(
        verified_text, str
    ):
        return None
    try:
        verified_at = datetime.fromisoformat(verified_text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if verified_at.tzinfo is None:
        verified_at = verified_at.replace(tzinfo=UTC)
    if datetime.now(UTC) - verified_at > DETAIL_CACHE_MAX_AGE:
        return None
    cached_posting = normalize_job_posting(cached_posting)
    if (
        cached_posting.source_url != posting.source_url
        or cached_posting.title != posting.title
        or cached_posting.normalization_state != "complete"
    ):
        return None
    return replace(
        posting,
        location=cached_posting.location or posting.location,
        description=cached_posting.description,
        remote_status=cached_posting.remote_status or posting.remote_status,
        salary_text=cached_posting.salary_text or posting.salary_text,
        detail_retrieval_state="cached_detail_reuse",
    )
