import hashlib
import re


_WHITESPACE_RE = re.compile(r"\s+")


def clean_text(value: str | None) -> str:
    if value is None:
        return ""

    return _WHITESPACE_RE.sub(" ", value).strip()


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