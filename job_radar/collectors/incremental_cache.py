"""Share transient incremental-cache metadata with detail-heavy collectors."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from job_radar.storage import CachedSourcePosting
from job_radar.normalize import normalize_job_posting


CACHE_CONFIG_KEY = "_source_posting_cache"
FINGERPRINTS_CONFIG_KEY = "_source_listing_fingerprints"
REUSED_CONFIG_KEY = "_source_reused_identities"
PROGRESS_CONFIG_KEY = "_scan_progress_callback"
WARNINGS_CONFIG_KEY = "_source_collection_warnings"
WARNING_TYPES_CONFIG_KEY = "_source_collection_warning_types"
DETAIL_PLANNER_CONFIG_KEY = "_detail_retrieval_planner"
DETAIL_CACHE_MAX_AGE = timedelta(days=7)
MAX_WARNING_LENGTH = 300


def _bounded_warning(warning: str) -> str:
    """Keep diagnostics bounded without cutting a user-facing sentence in half."""

    cleaned = " ".join(warning.split())
    if len(cleaned) <= MAX_WARNING_LENGTH:
        return cleaned
    bounded = cleaned[:MAX_WARNING_LENGTH]
    sentence_end = max(bounded.rfind(". "), bounded.rfind("! "), bounded.rfind("? "))
    if sentence_end >= MAX_WARNING_LENGTH // 2:
        return bounded[: sentence_end + 1]
    word_end = bounded.rfind(" ")
    return f"{bounded[:word_end].rstrip()}…" if word_end > 0 else bounded


def report_progress(company_config: dict[str, Any], operation: str) -> None:
    """Send a bounded public progress label when the scan supplied a callback."""

    callback = company_config.get(PROGRESS_CONFIG_KEY)
    if callable(callback):
        callback(operation[:160])


def record_collection_warning(
    company_config: dict[str, Any],
    warning: str,
    *,
    warning_type: str = "incomplete_position_detail_response_failure",
) -> None:
    """Retain a safe source warning for the shared scan lifecycle."""

    bounded_warning = _bounded_warning(warning)
    warnings = company_config.setdefault(WARNINGS_CONFIG_KEY, [])
    if isinstance(warnings, list) and bounded_warning not in warnings:
        warnings.append(bounded_warning)
        warning_types = company_config.setdefault(WARNING_TYPES_CONFIG_KEY, {})
        if isinstance(warning_types, dict):
            warning_types[bounded_warning] = warning_type


def listing_fingerprint(value: object) -> str:
    """Hash bounded public listing metadata without retaining raw responses."""

    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def get_cached_posting(
    company_config: dict[str, Any],
    *,
    identity: str,
    fingerprint: str,
) -> CachedSourcePosting | None:
    cached = get_recent_cached_posting(company_config, identity=identity)
    if cached is None or cached.listing_fingerprint != fingerprint:
        return None
    return cached


def get_recent_cached_posting(
    company_config: dict[str, Any],
    *,
    identity: str,
) -> CachedSourcePosting | None:
    """Return a fresh complete detail by stable source identity."""

    cache = company_config.get(CACHE_CONFIG_KEY)
    if not isinstance(cache, dict):
        return None
    cached = cache.get(identity)
    if not isinstance(cached, CachedSourcePosting):
        return None
    if normalize_job_posting(cached.posting).normalization_state != "complete":
        # Older releases could mark a failed detail response as verified.
        # Never let that legacy row suppress a fresh detail request.
        return None
    try:
        verified_at = datetime.fromisoformat(
            cached.detail_verified_at.replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        return None
    if verified_at.tzinfo is None:
        verified_at = verified_at.replace(tzinfo=UTC)
    if datetime.now(UTC) - verified_at > DETAIL_CACHE_MAX_AGE:
        return None
    return cached


def record_listing(
    company_config: dict[str, Any],
    *,
    identity: str,
    fingerprint: str,
    reused: bool,
) -> None:
    fingerprints = company_config.setdefault(FINGERPRINTS_CONFIG_KEY, {})
    if isinstance(fingerprints, dict):
        fingerprints[identity] = fingerprint
    if reused:
        reused_identities = company_config.setdefault(REUSED_CONFIG_KEY, set())
        if isinstance(reused_identities, set):
            reused_identities.add(identity)
