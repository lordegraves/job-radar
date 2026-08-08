"""Build one validated job representation from every recruiting platform."""

import hashlib
from dataclasses import replace
from html import unescape
import re

from job_radar.models import JobPosting


_WHITESPACE_RE = re.compile(r"\s+")
_BLOCK_TAG_RE = re.compile(
    r"(?is)</?(?:article|blockquote|br|div|h[1-6]|li|ol|p|section|table|td|th|tr|ul)[^>]*>"
)
_TAG_RE = re.compile(r"(?is)<[^>]+>")
_PLACEHOLDER_SOURCE_IDS = {
    "job",
    "job posting",
    "opening",
    "position",
    "spotlight job",
}
_TITLE_METADATA_RE = re.compile(
    r"(?i)\s+(?:date\s+posted|posted\s+date)\s*:.+$"
)
_RECALCULATED_ISSUES = {
    "incomplete_description",
    "missing_source_url",
    "missing_title",
    "placeholder_source_job_id",
    "unrecognized_workplace_value",
}


def clean_text(value: str | None) -> str:
    if value is None:
        return ""

    return _WHITESPACE_RE.sub(" ", value).strip()


def clean_human_text(value: str | None) -> str:
    """Remove source markup while preserving readable qualification sections."""

    if not value:
        return ""
    decoded = value
    for _ in range(3):
        next_value = unescape(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    decoded = _BLOCK_TAG_RE.sub("\n", decoded)
    decoded = _TAG_RE.sub(" ", decoded)
    lines: list[str] = []
    seen: set[str] = set()
    for raw_line in decoded.replace("\r", "\n").split("\n"):
        line = clean_text(raw_line)
        if not line:
            continue
        comparison = line.casefold()
        # ATS APIs sometimes repeat the same description in several fields.
        # Exact paragraph deduplication removes that transport duplication
        # without attempting to rewrite an employer's wording.
        if comparison in seen:
            continue
        seen.add(comparison)
        lines.append(line)
    return "\n".join(lines)


def normalize_workplace(value: str | None) -> tuple[str | None, str | None]:
    """Return Junior's common workplace label and any validation issue."""

    text = clean_human_text(value)
    if not text:
        return None, None
    lowered = text.casefold().replace("_", " ")
    if lowered in {
        "remote",
        "fully remote",
        "home based",
        "telecommute",
        "telecommuting",
        "virtual",
        "work from home",
    }:
        return "Remote", None
    if "hybrid" in lowered:
        return "Hybrid", None
    if lowered in {"on-site", "onsite", "on site", "in-person", "in person"}:
        return "On-site", None
    if lowered in {"flex", "flexible"}:
        return "Flex", None
    if lowered == "field":
        return "Field", None
    return text, "unrecognized_workplace_value"


def normalize_job_posting(posting: JobPosting) -> JobPosting:
    """Apply the shared post-collector contract before storage or evaluation."""

    title = clean_human_text(posting.title)
    title = _TITLE_METADATA_RE.sub("", title).strip()
    location = clean_human_text(posting.location) or None
    description = clean_human_text(posting.description) or None
    salary_text = clean_human_text(posting.salary_text) or None
    remote_status, workplace_issue = normalize_workplace(posting.remote_status)
    source_job_id = clean_human_text(posting.source_job_id) or None
    # A posting may be normalized once as a listing summary and again after
    # detail retrieval. Recalculate field-quality findings so a repaired field
    # does not remain permanently marked incomplete.
    issues: list[str] = [
        issue
        for issue in posting.normalization_issues
        if issue not in _RECALCULATED_ISSUES
    ]

    if source_job_id and source_job_id.casefold() in _PLACEHOLDER_SOURCE_IDS:
        source_job_id = None
        issues.append("placeholder_source_job_id")
    if not title:
        issues.append("missing_title")
    if not posting.source_url:
        issues.append("missing_source_url")
    if workplace_issue:
        issues.append(workplace_issue)

    skipped = posting.detail_retrieval_state == "skipped_unrelated"
    if not skipped and (
        description is None
        or len(description) < 200
        or posting.detail_retrieval_state == "summary_only"
    ):
        issues.append("incomplete_description")

    blocking_issues = {"missing_title", "missing_source_url", "incomplete_description"}
    state = (
        "skipped_unrelated"
        if skipped
        else ("incomplete" if blocking_issues.intersection(issues) else "complete")
    )
    canonical_key = make_canonical_key(posting.company_key, title, location)
    content_hash = make_content_hash(
        title,
        location,
        description,
        salary_text,
    )
    return JobPosting(
        company_key=clean_text(posting.company_key),
        company_name=clean_human_text(posting.company_name),
        source_type=clean_text(posting.source_type).lower(),
        source_url=clean_text(posting.source_url),
        title=title,
        location=location,
        description=description,
        source_job_id=source_job_id,
        remote_status=remote_status,
        salary_text=salary_text,
        canonical_key=canonical_key,
        content_hash=content_hash,
        listing_fingerprint=clean_text(posting.listing_fingerprint) or None,
        detail_retrieval_reason=posting.detail_retrieval_reason,
        detail_retrieval_state=posting.detail_retrieval_state,
        normalization_state=state,
        normalization_issues=tuple(dict.fromkeys(issues)),
    )


def normalize_job_postings(postings: list[JobPosting]) -> list[JobPosting]:
    """Normalize one company's batch and reject non-unique advertised IDs."""

    normalized = [normalize_job_posting(posting) for posting in postings]
    id_urls: dict[str, set[str]] = {}
    for posting in normalized:
        if posting.source_job_id:
            id_urls.setdefault(posting.source_job_id, set()).add(posting.source_url)
    duplicated_ids = {
        source_id
        for source_id, urls in id_urls.items()
        if len(urls) > 1
    }
    if not duplicated_ids:
        return normalized

    repaired: list[JobPosting] = []
    for posting in normalized:
        if posting.source_job_id not in duplicated_ids:
            repaired.append(posting)
            continue
        issues = tuple(
            dict.fromkeys((*posting.normalization_issues, "duplicate_source_job_id"))
        )
        repaired.append(
            replace(
                posting,
                source_job_id=None,
                normalization_issues=issues,
            )
        )
    return repaired


def normalize_for_key(value: str | None) -> str:
    cleaned = clean_text(value).lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned)
    cleaned = cleaned.strip("-")
    return cleaned


def make_canonical_key(
    company_key: str,
    title: str,
    location: str | None,
) -> str:
    company_part = normalize_for_key(company_key)
    title_part = normalize_for_key(title)
    location_part = normalize_for_key(location)

    if location_part:
        return f"{company_part}:{title_part}:{location_part}"

    return f"{company_part}:{title_part}"


def make_content_hash(
    title: str,
    location: str | None,
    description: str | None,
    salary_text: str | None = None,
) -> str:
    normalized_parts = [
        clean_text(title).lower(),
        clean_text(location).lower(),
        clean_text(description).lower(),
        clean_text(salary_text).lower(),
    ]

    content = "\n".join(normalized_parts)

    return hashlib.sha256(content.encode("utf-8")).hexdigest()
