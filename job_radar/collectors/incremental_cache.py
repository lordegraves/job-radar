"""Share transient incremental-cache metadata with detail-heavy collectors."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from job_radar.storage import CachedSourcePosting


CACHE_CONFIG_KEY = "_source_posting_cache"
FINGERPRINTS_CONFIG_KEY = "_source_listing_fingerprints"
REUSED_CONFIG_KEY = "_source_reused_identities"
DETAIL_CACHE_MAX_AGE = timedelta(days=7)


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
    cache = company_config.get(CACHE_CONFIG_KEY)
    if not isinstance(cache, dict):
        return None
    cached = cache.get(identity)
    if not isinstance(cached, CachedSourcePosting):
        return None
    if cached.listing_fingerprint != fingerprint:
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
