"""Create stable Job Radar IDs for manually entered or imported jobs."""

import hashlib
from uuid import uuid4


def build_manual_job_radar_id(
    *,
    company_name: str,
    role_title: str,
    source_url: str | None = None,
    source_key: str | None = None,
) -> str:
    """Build an app-owned ID for manual jobs that did not come from a scan.

    URLs are useful evidence, but they are not durable app identity. Spreadsheet
    imports and GUI-created records get a Job Radar-owned ID so tracker records
    do not use posting URLs as primary keys.
    """
    stable_key = source_key or source_url

    if stable_key:
        seed = "|".join(
            [
                _normalize_id_part(company_name),
                _normalize_id_part(role_title),
                _normalize_id_part(stable_key),
            ]
        )
    else:
        seed = "|".join(
            [
                _normalize_id_part(company_name),
                _normalize_id_part(role_title),
                uuid4().hex,
            ]
        )

    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
    company_token = _tokenize_id_part(company_name)
    role_token = _tokenize_id_part(role_title)

    return f"jr_manual_{company_token}_{role_token}_{digest}"


def _normalize_id_part(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _tokenize_id_part(value: str) -> str:
    token = "_".join(_normalize_id_part(value).replace("/", " ").replace("-", " ").split())

    if not token:
        return "unknown"

    return token[:40]
