"""Resolve normal-user company names and careers URLs without network access."""

import ipaddress
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from job_radar.database import connect_database
from job_radar.employer_storage import list_profile_employer_assignments
from job_radar.profile_storage import get_profile
from job_radar.storage import initialize_database


MATCHED_EXISTING = "MATCHED_EXISTING"
DETECTED_SCAN_READY = "DETECTED_SCAN_READY"
CREATED_SCAN_READY = "CREATED_SCAN_READY"
PENDING_REVIEW = "PENDING_REVIEW"
AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
UNSUPPORTED_SITE = "UNSUPPORTED_SITE"
INVALID_INPUT = "INVALID_INPUT"
ALREADY_ASSIGNED = "ALREADY_ASSIGNED"

_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


@dataclass(frozen=True)
class DetectedEmployerSource:
    """Describe centralized URL detection without exposing it in normal UI."""

    source_type: str | None
    source_identifier: str | None
    source_config: dict[str, str]
    scan_ready: bool


@dataclass(frozen=True)
class EmployerResolutionResult:
    """Return a bounded outcome for one normal-user submission."""

    status: str
    message: str
    employer_id: str | None = None
    employer_name: str | None = None
    careers_url: str | None = None
    review_request_id: str | None = None
    possible_employers: tuple[tuple[str, str], ...] = ()
    detected_source_label: str | None = None


def resolve_employer_submission(
    database_path: str | Path,
    *,
    profile_id: str,
    company_name: str = "",
    careers_url: str = "",
    confirm_detected: bool = False,
) -> EmployerResolutionResult:
    """Resolve, safely create, or queue one company for a managed profile."""

    db_path = initialize_database(database_path)
    if get_profile(db_path, profile_id) is None:
        return _invalid("Select a valid profile before adding a company.")

    display_name = " ".join(company_name.strip().split())
    normalized_name = normalize_company_name(display_name)
    submitted_url = careers_url.strip()
    normalized_url: str | None = None
    if submitted_url:
        try:
            normalized_url = normalize_careers_url(submitted_url)
        except ValueError as error:
            return _invalid(str(error))
    if not normalized_name and not normalized_url:
        return _invalid("Enter a company name or careers URL.")

    assigned_ids = {
        item.employer_id
        for item in list_profile_employer_assignments(db_path, profile_id)
    }
    exact = _find_exact_matches(
        db_path,
        normalized_name=normalized_name,
        normalized_url=normalized_url,
    )
    if len(exact) == 1:
        employer_id, name = exact[0]
        if employer_id in assigned_ids:
            return EmployerResolutionResult(
                status=ALREADY_ASSIGNED,
                message=f"{name} is already in this profile.",
                employer_id=employer_id,
                employer_name=name,
                careers_url=normalized_url,
            )
        return EmployerResolutionResult(
            status=MATCHED_EXISTING,
            message=f"{name} is already available in Junior.",
            employer_id=employer_id,
            employer_name=name,
            careers_url=normalized_url,
        )
    if len(exact) > 1:
        return _ambiguous(exact)

    strong_candidates = _find_strong_name_candidates(db_path, normalized_name)
    if strong_candidates:
        return _ambiguous(strong_candidates)

    detection = (
        detect_employer_source(normalized_url)
        if normalized_url is not None
        else DetectedEmployerSource(None, None, {}, False)
    )
    if detection.scan_ready and normalized_url is not None:
        if not confirm_detected:
            name = display_name or _display_name_from_detection(
                normalized_url,
                detection,
            )
            return EmployerResolutionResult(
                status=DETECTED_SCAN_READY,
                message=(
                    f"Junior recognized {name}'s public "
                    f"{_source_label(detection.source_type)} career site. "
                    "Confirm this is the company you want before adding it."
                ),
                employer_name=name,
                careers_url=normalized_url,
                detected_source_label=_source_label(detection.source_type),
            )
        return _create_and_assign_scan_ready(
            db_path,
            profile_id=profile_id,
            display_name=display_name,
            normalized_name=normalized_name,
            normalized_url=normalized_url,
            detection=detection,
        )

    detection_result = (
        UNSUPPORTED_SITE if normalized_url and detection.source_type is None
        else PENDING_REVIEW
    )
    return _create_pending_review(
        db_path,
        profile_id=profile_id,
        display_name=display_name,
        normalized_name=normalized_name,
        normalized_url=normalized_url,
        detection_result=detection_result,
    )


def normalize_company_name(value: str) -> str:
    """Create a Unicode-aware comparison form while preserving display text."""

    collapsed = " ".join(value.strip().split())
    return unicodedata.normalize("NFKC", collapsed).casefold()


def normalize_careers_url(value: str) -> str:
    """Normalize a public HTTP(S) careers URL without losing tenant paths."""

    candidate = value.strip()
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlsplit(candidate)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Enter a complete public HTTP or HTTPS careers URL.")
    if parsed.username or parsed.password:
        raise ValueError("Careers URLs cannot contain a username or password.")

    hostname = parsed.hostname.casefold().rstrip(".")
    if _unsafe_hostname(hostname):
        raise ValueError("Enter a public careers URL, not a local or private address.")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("The careers URL contains an invalid port.") from error
    if port not in {None, 80, 443}:
        raise ValueError("The careers URL must use the normal HTTP or HTTPS port.")

    scheme = parsed.scheme.casefold()
    netloc = hostname
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = None
    if port is not None:
        netloc = f"{hostname}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    clean_query = [
        (key, val)
        for key, val in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_")
        and key.casefold() not in _TRACKING_QUERY_KEYS
    ]
    return urlunsplit(
        (scheme, netloc, path, urlencode(clean_query, doseq=True), "")
    )


def detect_employer_source(careers_url: str) -> DetectedEmployerSource:
    """Recognize supported collector families from public URL structure."""

    parsed = urlsplit(careers_url)
    host = parsed.hostname or ""
    parts = [part for part in parsed.path.split("/") if part]
    slug = parts[0] if parts else None

    if host in {"boards.greenhouse.io", "job-boards.greenhouse.io"} and slug:
        return _slug_detection("greenhouse", slug, careers_url)
    if host == "jobs.lever.co" and slug:
        return _slug_detection("lever", slug, careers_url)
    if host == "jobs.ashbyhq.com" and slug:
        return _slug_detection("ashby", slug, careers_url)

    source_type = _detect_supported_family(host, parsed.path.casefold())
    return DetectedEmployerSource(source_type, None, {}, False)


def _detect_supported_family(host: str, path: str) -> str | None:
    patterns = (
        ("myworkdayjobs.com", "workday"),
        ("icims.com", "icims"),
        ("oraclecloud.com", "oracle_hcm"),
        ("smartrecruiters.com", "smartrecruiters"),
        ("selectminds.com", "selectminds"),
        ("phenompeople.com", "phenom"),
        ("dayforcehcm.com", "dayforce"),
        ("adp.com", "adp"),
        ("rippling.com", "rippling"),
        ("schoolspring.com", "schoolspring"),
        ("jibeapply.com", "jibe"),
        ("jobsyn.org", "jobsyn"),
        ("activatejob.com", "activate"),
        ("weka.io", "weka"),
    )
    for domain, source_type in patterns:
        if host == domain or host.endswith(f".{domain}"):
            return source_type
    if "/jobs" in path or "/careers" in path:
        return "html"
    return None


def _find_exact_matches(
    database_path: Path,
    *,
    normalized_name: str,
    normalized_url: str | None,
) -> list[tuple[str, str]]:
    conditions = []
    parameters: list[str] = []
    if normalized_url:
        conditions.append(
            "(normalized_careers_url = ? OR "
            "json_extract(source_config_json, '$.careers_url') = ?)"
        )
        parameters.extend((normalized_url, normalized_url))
    if normalized_name:
        conditions.extend(
            (
                "normalized_name = ?",
                "employer_id IN (SELECT employer_id FROM employer_aliases "
                "WHERE normalized_alias = ?)",
            )
        )
        parameters.extend((normalized_name, normalized_name))
    if not conditions:
        return []
    with connect_database(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT employer_id, name
            FROM employer_sources
            WHERE {" OR ".join(conditions)}
              AND retired = 0
            ORDER BY name COLLATE NOCASE, employer_id
            """,
            parameters,
        ).fetchall()
        if normalized_url:
            legacy_rows = connection.execute(
                """
                SELECT employer_id, name, source_config_json
                FROM employer_sources
                WHERE retired = 0
                  AND normalized_careers_url IS NULL
                """
            ).fetchall()
            for employer_id, name, raw_config in legacy_rows:
                try:
                    config = json.loads(raw_config)
                    stored_url = config.get("careers_url")
                    if (
                        isinstance(stored_url, str)
                        and normalize_careers_url(stored_url) == normalized_url
                    ):
                        rows.append((employer_id, name))
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
        if normalized_name:
            legacy_name_rows = connection.execute(
                """
                SELECT employer_id, name
                FROM employer_sources
                WHERE retired = 0
                  AND normalized_name IS NULL
                """
            ).fetchall()
            for employer_id, name in legacy_name_rows:
                if normalize_company_name(str(name)) == normalized_name:
                    rows.append((employer_id, name))
    rows = list(dict.fromkeys((str(row[0]), str(row[1])) for row in rows))
    return rows


def _find_strong_name_candidates(
    database_path: Path,
    normalized_name: str,
) -> list[tuple[str, str]]:
    if len(normalized_name) < 4:
        return []
    with connect_database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT employer_id, name, normalized_name
            FROM employer_sources
            WHERE retired = 0
            """
        ).fetchall()
    candidates = []
    submitted_tokens = set(normalized_name.split())
    for employer_id, name, stored_name in rows:
        comparison_name = str(stored_name or "") or normalize_company_name(
            str(name)
        )
        stored_tokens = set(comparison_name.split())
        if submitted_tokens and stored_tokens and (
            submitted_tokens < stored_tokens or stored_tokens < submitted_tokens
        ):
            candidates.append((str(employer_id), str(name)))
    return candidates


def _create_and_assign_scan_ready(
    database_path: Path,
    *,
    profile_id: str,
    display_name: str,
    normalized_name: str,
    normalized_url: str,
    detection: DetectedEmployerSource,
) -> EmployerResolutionResult:
    name = display_name or _display_name_from_detection(
        normalized_url,
        detection,
    )
    employer_id = _employer_id(name)
    with connect_database(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            existing = connection.execute(
                """
                SELECT employer_id, name
                FROM employer_sources
                WHERE normalized_careers_url = ?
                   OR (source_type = ? AND source_identifier = ?)
                LIMIT 1
                """,
                (
                    normalized_url,
                    detection.source_type,
                    detection.source_identifier,
                ),
            ).fetchone()
            if existing is not None:
                existing_id, existing_name = str(existing[0]), str(existing[1])
                assigned = connection.execute(
                    """
                    SELECT 1 FROM profile_company_associations
                    WHERE profile_id = ? AND company_id = ?
                    """,
                    (profile_id, existing_id),
                ).fetchone()
                connection.commit()
                return EmployerResolutionResult(
                    status=ALREADY_ASSIGNED if assigned else MATCHED_EXISTING,
                    message=(
                        f"{existing_name} is already in this profile."
                        if assigned
                        else f"{existing_name} is already available in Junior."
                    ),
                    employer_id=existing_id,
                    employer_name=existing_name,
                    careers_url=normalized_url,
                )

            employer_id = _unique_id_in_connection(connection, employer_id)
            source_config = dict(detection.source_config)
            source_config["careers_url"] = normalized_url
            connection.execute(
                """
                INSERT INTO employer_sources (
                    employer_id, name, normalized_name, source_type, enabled,
                    source_config_json, normalized_careers_url,
                    source_identifier, resolution_status, submitted_name,
                    submitted_url, validation_state, creation_source
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, 'scan_ready', ?, ?, ?, 'user')
                """,
                (
                    employer_id,
                    name,
                    normalized_name or normalize_company_name(name),
                    detection.source_type,
                    json.dumps(source_config, separators=(",", ":"), sort_keys=True),
                    normalized_url,
                    detection.source_identifier,
                    display_name or None,
                    normalized_url,
                    "valid",
                ),
            )
            connection.execute(
                """
                INSERT INTO profile_company_associations (
                    profile_id, company_id, enabled
                ) VALUES (?, ?, 1)
                """,
                (profile_id, employer_id),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return EmployerResolutionResult(
        status=CREATED_SCAN_READY,
        message=f"{name} was added and will be included in future scans.",
        employer_id=employer_id,
        employer_name=name,
        careers_url=normalized_url,
    )


def _create_pending_review(
    database_path: Path,
    *,
    profile_id: str,
    display_name: str,
    normalized_name: str,
    normalized_url: str | None,
    detection_result: str,
) -> EmployerResolutionResult:
    request_id = f"review_{uuid4().hex}"
    summary = (
        "Junior needs an administrator to finish setting up this company "
        "before it can be scanned."
    )
    with connect_database(database_path) as connection:
        existing = connection.execute(
            """
            SELECT request_id
            FROM employer_review_requests
            WHERE requesting_profile_id = ?
              AND normalized_company_name = ?
              AND normalized_careers_url = ?
              AND status = 'PENDING'
            """,
            (profile_id, normalized_name, normalized_url or ""),
        ).fetchone()
        if existing is not None:
            return EmployerResolutionResult(
                status=detection_result,
                message=summary,
                careers_url=normalized_url,
                employer_name=(
                    display_name or _display_name_from_url(normalized_url or "")
                ),
                review_request_id=str(existing[0]),
            )
        try:
            connection.execute(
                """
                INSERT INTO employer_review_requests (
                    request_id, submitted_company_name, submitted_careers_url,
                    normalized_company_name, normalized_careers_url,
                    requesting_profile_id, detection_result, safe_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    display_name or None,
                    normalized_url,
                    normalized_name,
                    normalized_url or "",
                    profile_id,
                    detection_result,
                    summary,
                ),
            )
        except sqlite3.IntegrityError:
            existing = connection.execute(
                """
                SELECT request_id
                FROM employer_review_requests
                WHERE requesting_profile_id = ?
                  AND normalized_company_name = ?
                  AND normalized_careers_url = ?
                  AND status = 'PENDING'
                """,
                (profile_id, normalized_name, normalized_url or ""),
            ).fetchone()
            if existing is None:
                raise
            request_id = str(existing[0])
    return EmployerResolutionResult(
        status=detection_result,
        message=summary,
        careers_url=normalized_url,
        employer_name=display_name or _display_name_from_url(normalized_url or ""),
        review_request_id=request_id,
    )


def _slug_detection(
    source_type: str,
    slug: str,
    careers_url: str,
) -> DetectedEmployerSource:
    normalized_slug = slug.strip()
    return DetectedEmployerSource(
        source_type=source_type,
        source_identifier=normalized_slug.casefold(),
        source_config={
            "source_slug": normalized_slug,
            "careers_url": careers_url,
        },
        scan_ready=True,
    )


def _source_label(source_type: str | None) -> str:
    """Return the small set of scan-ready source names shown for confirmation."""

    return {
        "greenhouse": "Greenhouse",
        "lever": "Lever",
        "ashby": "Ashby",
    }.get(source_type or "", "supported")


def _unsafe_hostname(hostname: str) -> bool:
    if (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
        or hostname.endswith(".internal")
    ):
        return True
    try:
        address = ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        return False
    return not address.is_global


def _employer_id(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.casefold()).strip("-") or "employer"


def _unique_id_in_connection(connection: sqlite3.Connection, base: str) -> str:
    candidate = base
    suffix = 2
    while connection.execute(
        "SELECT 1 FROM employer_sources WHERE employer_id = ?",
        (candidate,),
    ).fetchone():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _display_name_from_url(value: str) -> str:
    host = urlsplit(value).hostname or "New company"
    label = host.split(".")[0].replace("-", " ").strip()
    return label.title() or "New company"


def _display_name_from_detection(
    value: str,
    detection: DetectedEmployerSource,
) -> str:
    if detection.source_identifier:
        return detection.source_identifier.replace("-", " ").replace("_", " ").title()
    return _display_name_from_url(value)


def _ambiguous(
    candidates: list[tuple[str, str]],
) -> EmployerResolutionResult:
    return EmployerResolutionResult(
        status=AMBIGUOUS_MATCH,
        message="More than one company may match. Choose an exact company below.",
        possible_employers=tuple(candidates),
    )


def _invalid(message: str) -> EmployerResolutionResult:
    return EmployerResolutionResult(status=INVALID_INPUT, message=message)
