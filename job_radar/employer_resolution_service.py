"""Resolve normal-user company names and careers URLs without network access."""

import ipaddress
import json
import re
import sqlite3
import unicodedata
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import date, datetime
from html import unescape
from pathlib import Path
from urllib.parse import (
    parse_qsl,
    urlencode,
    urljoin,
    urlsplit,
    urlunsplit,
)
from uuid import uuid4

import requests

from job_radar.collectors.collector_http import get_response
from job_radar.database import connect_database
from job_radar.collectors.greenhouse import CollectorError
from job_radar.collectors.registry import collect_jobs_for_company
from job_radar.collectors.walmart import walmart_scope_config
from job_radar.employer_storage import list_profile_employer_assignments
from job_radar.profile_storage import get_profile
from job_radar.normalize import clean_human_text
from job_radar.storage import initialize_database


MATCHED_EXISTING = "MATCHED_EXISTING"
DETECTED_SCAN_READY = "DETECTED_SCAN_READY"
DETECTED_SETUP_REQUIRED = "DETECTED_SETUP_REQUIRED"
CREATED_SCAN_READY = "CREATED_SCAN_READY"
PENDING_REVIEW = "PENDING_REVIEW"
AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
UNSUPPORTED_SITE = "UNSUPPORTED_SITE"
NO_CURRENT_JOBS = "NO_CURRENT_JOBS"
INVALID_INPUT = "INVALID_INPUT"
ALREADY_ASSIGNED = "ALREADY_ASSIGNED"
DISCOVERY_TIMED_OUT = "DISCOVERY_TIMED_OUT"

_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}
_COMPANY_DISCOVERY_TIMEOUT_SECONDS = 120
_DISCOVERY_MAX_PAGES = 12
_DISCOVERY_MAX_DOCUMENT_BYTES = 8_000_000
_CAREER_LINK_TERMS = (
    "career",
    "employment",
    "job",
    "join-us",
    "join_us",
    "opportunit",
    "work-with-us",
)
_EXTERNAL_HANDOFF_BLOCKED_HOSTS = {
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "youtube.com",
}
_TALENTBREW_NON_SCOPE_QUERY_KEYS = {
    "glat",
    "glon",
    "latitude",
    "longitude",
    "p",
}
_DOMAIN_SLUG_ATS_URLS = (
    "https://jobs.ashbyhq.com/{slug}",
    "https://boards.greenhouse.io/{slug}",
    "https://jobs.lever.co/{slug}",
    "https://{slug}.hrmdirect.com/employment/job-openings.php?search=true",
)
_COMMON_SECOND_LEVEL_SUFFIXES = {
    "co.uk",
    "com.au",
    "com.br",
    "com.mx",
    "co.nz",
    "co.jp",
    "co.in",
}
_DOMAIN_COMPANY_SUFFIXES = (
    "technologies",
    "technology",
    "aerospace",
    "machines",
    "systems",
    "space",
    "labs",
    "corp",
    "inc",
)
_KNOWN_PUBLIC_CAREER_HANDOFFS = {
    (
        "www.sony.com",
        "/en_us/sca/careers/main.html",
    ): "https://sonyglobal.wd1.myworkdayjobs.com/SonyGlobalCareers",
}


@dataclass(frozen=True)
class DetectedEmployerSource:
    """Describe centralized URL detection without exposing it in normal UI."""

    source_type: str | None
    source_identifier: str | None
    source_config: dict[str, str]
    scan_ready: bool
    confidence: str = "high"
    evidence: tuple[str, ...] = ()


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
    requires_company_name: bool = False


def resolve_employer_submission(
    database_path: str | Path,
    *,
    profile_id: str,
    company_name: str = "",
    careers_url: str = "",
    confirm_detected: bool = False,
    discovery_observer: Callable[[str, Mapping[str, object]], None] | None = None,
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
            requires_company_name = (
                detection.source_type == "adp" and not display_name
            )
            name = (
                display_name
                or (
                    ""
                    if requires_company_name
                    else _display_name_from_detection(normalized_url, detection)
                )
            )
            return EmployerResolutionResult(
                status=DETECTED_SCAN_READY,
                message=(
                    "Junior recognized this public "
                    f"{_source_label(detection.source_type)} career site. "
                    "Confirm this is the company you want before adding it."
                ),
                employer_name=name,
                careers_url=normalized_url,
                detected_source_label=_source_label(detection.source_type),
                requires_company_name=requires_company_name,
            )
        if detection.source_type == "adp" and not display_name:
            return _invalid(
                "Enter the company name before adding this ADP career site."
            )
        tested_source = _first_working_source(
            [detection],
            display_name=(
                display_name
                or _display_name_from_detection(normalized_url, detection)
            ),
            discovery_observer=discovery_observer,
            walmart_scope=walmart_scope_config(get_profile(db_path, profile_id).preferences),
        )
        if tested_source is None:
            return _source_test_failed()
        detection, job_count = tested_source
        return _create_and_assign_scan_ready(
            db_path,
            profile_id=profile_id,
            display_name=display_name,
            normalized_name=normalized_name,
            normalized_url=normalized_url,
            detection=detection,
            connection_job_count=job_count,
        )

    if normalized_url and not confirm_detected:
        return EmployerResolutionResult(
            status=DETECTED_SETUP_REQUIRED,
            message=(
                "Junior will inspect this public careers site and configure the "
                "appropriate collector. Enter the employer's name to continue."
            ),
            careers_url=normalized_url,
            requires_company_name=True,
        )
    if normalized_url:
        if not display_name:
            return _invalid("Enter the company name before testing this careers site.")
        return _create_and_assign_generic(
            db_path,
            profile_id=profile_id,
            display_name=display_name,
            normalized_name=normalized_name,
            normalized_url=normalized_url,
            discovery_observer=discovery_observer,
        )
    return _create_and_assign_name_only(
        db_path,
        profile_id=profile_id,
        display_name=display_name,
        normalized_name=normalized_name,
        discovery_observer=discovery_observer,
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

    if host in {"careers.walmart.com", "www.careers.walmart.com"}:
        return DetectedEmployerSource(
            source_type="walmart",
            source_identifier="walmart-careers-us",
            source_config={
                "source_url": "https://careers.walmart.com/api/graphql",
                "careers_url": careers_url,
                "display_name": "Walmart",
            },
            scan_ready=True,
            evidence=("Walmart public careers hostname",),
        )

    if host in {"boards.greenhouse.io", "job-boards.greenhouse.io"} and slug:
        return _slug_detection("greenhouse", slug, careers_url)
    if host == "jobs.lever.co" and slug:
        return _slug_detection("lever", slug, careers_url)
    if host == "jobs.ashbyhq.com" and slug:
        return _slug_detection("ashby", slug, careers_url)
    if host.endswith(".hrmdirect.com") and host.count(".") >= 2:
        return DetectedEmployerSource(
            source_type="html",
            source_identifier=f"hrmdirect:{host.casefold()}",
            source_config={
                "source_url": careers_url,
                "careers_url": careers_url,
                "job_link_patterns": ["job-opening.php?req="],
            },
            scan_ready=True,
            evidence=("HRMDirect public job board",),
        )
    if host.endswith(".myworkdayjobs.com"):
        workday_detection = _workday_detection(careers_url, careers_url)
        if workday_detection is not None:
            return workday_detection
    if host == "workforcenow.adp.com":
        adp_detection = _adp_detection(careers_url)
        if adp_detection is not None:
            return adp_detection
    if host.endswith(".recruitee.com") and host.count(".") >= 2:
        tenant = host.removesuffix(".recruitee.com")
        return DetectedEmployerSource(
            source_type="recruitee",
            source_identifier=tenant,
            source_config={
                "source_url": f"https://{host}/api/offers/",
                "careers_url": careers_url,
            },
            scan_ready=True,
        )
    if host.endswith(".icims.com") and host.count(".") >= 2:
        return DetectedEmployerSource(
            source_type="icims",
            source_identifier=host.casefold(),
            source_config={
                "source_url": careers_url,
                "careers_url": careers_url,
            },
            scan_ready=True,
        )
    if host.endswith(".ultipro.com"):
        ukg_detection = _ukg_detection(careers_url)
        if ukg_detection is not None:
            return ukg_detection
    if host == "jobs.smartrecruiters.com" and slug:
        return DetectedEmployerSource(
            source_type="smartrecruiters",
            source_identifier=slug.casefold(),
            source_config={
                "source_url": (
                    f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
                ),
                "company_identifier": slug,
                "careers_url": careers_url,
            },
            scan_ready=True,
            evidence=("SmartRecruiters public job-board URL",),
        )
    if host == "ats.rippling.com" and slug:
        return DetectedEmployerSource(
            source_type="rippling",
            source_identifier=slug.casefold(),
            source_config={
                "source_slug": slug,
                "careers_url": careers_url,
            },
            scan_ready=True,
            evidence=("Rippling ATS public job-board URL",),
        )
    if host == "jobs.dayforcehcm.com" and slug:
        return DetectedEmployerSource(
            source_type="dayforce",
            source_identifier=f"{host}:{slug.casefold()}",
            source_config={
                "source_url": careers_url,
                "careers_url": careers_url,
            },
            scan_ready=True,
            evidence=("Dayforce public candidate-portal URL",),
        )
    if host.endswith(".referrals.selectminds.com"):
        return DetectedEmployerSource(
            source_type="selectminds",
            source_identifier=host.casefold(),
            source_config={
                "source_url": careers_url,
                "careers_url": careers_url,
            },
            scan_ready=True,
            evidence=("SelectMinds public careers hostname",),
        )
    if host == "careers.nintendo.com":
        return DetectedEmployerSource(
            source_type="html",
            source_identifier="careers.nintendo.com",
            source_config={
                "source_url": "https://careers.nintendo.com/jobs/",
                "careers_url": careers_url,
                "job_link_patterns": ["/jobs/"],
                "display_name": "Nintendo",
            },
            scan_ready=True,
        )
    if host in {"valvesoftware.com", "www.valvesoftware.com"}:
        return DetectedEmployerSource(
            source_type="html",
            source_identifier="www.valvesoftware.com",
            source_config={
                "source_url": "https://www.valvesoftware.com/en/jobs",
                "careers_url": careers_url,
                "job_link_patterns": ["?job_id="],
                "display_name": "Valve",
            },
            scan_ready=True,
        )
    if host == "careers.blizzard.com":
        return DetectedEmployerSource(
            source_type="phenom",
            source_identifier="careers.blizzard.com",
            source_config={
                "source_url": (
                    "https://careers.blizzard.com/global/en/search-results"
                ),
                "job_base_url": "https://careers.blizzard.com/global/en",
                "careers_url": careers_url,
                "display_name": "Blizzard",
            },
            scan_ready=True,
        )
    if host in {"broadcom.com", "www.broadcom.com"}:
        workday_url = (
            "https://broadcom.wd1.myworkdayjobs.com/External_Career"
        )
        detection = _workday_detection(workday_url, careers_url)
        if detection is None:
            return DetectedEmployerSource(None, None, {}, False)
        return DetectedEmployerSource(
            source_type=detection.source_type,
            source_identifier=detection.source_identifier,
            source_config={**detection.source_config, "display_name": "Broadcom"},
            scan_ready=True,
        )
    if host in {"careers.microsoft.com", "apply.careers.microsoft.com"}:
        return DetectedEmployerSource(
            source_type="eightfold",
            source_identifier="apply.careers.microsoft.com:microsoft.com",
            source_config={
                "source_url": "https://apply.careers.microsoft.com",
                "domain": "microsoft.com",
                "careers_url": careers_url,
                "display_name": "Microsoft",
            },
            scan_ready=True,
        )
    if host in {"google.com", "www.google.com"} and parsed.path.rstrip("/") == (
        "/about/careers/applications/jobs/results"
    ):
        return DetectedEmployerSource(
            source_type="google_careers",
            source_identifier="google-careers",
            source_config={
                "source_url": (
                    "https://www.google.com/about/careers/applications/jobs/results"
                ),
                "careers_url": careers_url,
                "display_name": "Google",
            },
            scan_ready=True,
        )
    if host in {"lockheedmartin.com", "www.lockheedmartin.com"}:
        return DetectedEmployerSource(
            source_type="talentbrew",
            source_identifier="talentbrew:www.lockheedmartinjobs.com",
            source_config={
                # The corporate landing page blocks automated access, while
                # this official public search page exposes the real job list.
                "source_url": "https://www.lockheedmartinjobs.com/search-jobs",
                "careers_url": careers_url,
                "job_link_patterns": ["/job/"],
                "display_name": "Lockheed Martin",
            },
            scan_ready=True,
        )

    source_type = _detect_supported_family(host, parsed.path.casefold())
    return DetectedEmployerSource(source_type, None, {}, False)


def _adp_detection(careers_url: str) -> DetectedEmployerSource | None:
    """Build a complete ADP collector configuration from its public URL."""

    parsed = urlsplit(careers_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    cid = query.get("cid", "").strip()
    cc_id = query.get("ccId", "").strip()
    if not cid or not cc_id:
        return None

    locale = query.get("lang", "").strip() or "en_US"
    return DetectedEmployerSource(
        source_type="adp",
        source_identifier=f"{cid.casefold()}:{cc_id.casefold()}",
        source_config={
            "source_url": careers_url,
            "cid": cid,
            "ccId": cc_id,
            "locale": locale,
            "careers_url": careers_url,
        },
        scan_ready=True,
    )


def _ukg_detection(careers_url: str) -> DetectedEmployerSource | None:
    """Build a complete UKG collector configuration from a public board URL."""

    parsed = urlsplit(careers_url)
    host = parsed.hostname or ""
    parts = [part for part in parsed.path.split("/") if part]
    if (
        not host.endswith(".ultipro.com")
        or len(parts) < 3
        or parts[1].casefold() != "jobboard"
    ):
        return None
    tenant = parts[0]
    board_id = parts[2]
    board_url = f"https://{host}/{tenant}/JobBoard/{board_id}/"
    return DetectedEmployerSource(
        source_type="ukg",
        source_identifier=f"{host.casefold()}:{tenant.casefold()}:{board_id.casefold()}",
        source_config={
            "source_url": board_url,
            "careers_url": careers_url,
        },
        scan_ready=True,
    )


def _workday_detection(
    workday_url: str,
    careers_url: str,
) -> DetectedEmployerSource | None:
    """Build Workday's public JSON endpoint from a public board address."""

    parsed = urlsplit(workday_url)
    host = parsed.hostname or ""
    if not host.endswith(".myworkdayjobs.com"):
        return None
    path_parts = [part for part in parsed.path.split("/") if part]
    if not path_parts:
        return None
    tenant = host.split(".", 1)[0]
    board = path_parts[0]
    source_base_url = f"https://{host}/{board}"
    return DetectedEmployerSource(
        source_type="workday",
        source_identifier=f"{host.casefold()}:{board.casefold()}",
        source_config={
            "source_url": (
                f"https://{host}/wday/cxs/{tenant}/{board}/jobs"
            ),
            "source_base_url": source_base_url,
            "careers_url": careers_url,
        },
        scan_ready=True,
    )


def _detect_supported_family(host: str, path: str) -> str | None:
    patterns = (
        ("myworkdayjobs.com", "workday"),
        ("icims.com", "icims"),
        ("ultipro.com", "ukg"),
        ("oraclecloud.com", "oracle_hcm"),
        ("smartrecruiters.com", "smartrecruiters"),
        ("selectminds.com", "selectminds"),
        ("phenompeople.com", "phenom"),
        ("dayforcehcm.com", "dayforce"),
        ("adp.com", "adp"),
        ("eightfold.ai", "eightfold"),
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
    connection_job_count: int,
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
                    submitted_url, validation_state, creation_source,
                    last_connection_test_at, last_connection_success_at,
                    last_connection_state, last_connection_category,
                    last_connection_message, last_connection_job_count
                ) VALUES (
                    ?, ?, ?, ?, 1, ?, ?, ?, 'scan_ready', ?, ?, ?, 'user',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'success', 'connected',
                    ?, ?
                )
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
                    (
                        "Connection succeeded and returned "
                        f"{connection_job_count} "
                        f"{'job' if connection_job_count == 1 else 'jobs'}."
                    ),
                    connection_job_count,
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


def _create_and_assign_generic(
    database_path: Path,
    *,
    profile_id: str,
    display_name: str,
    normalized_name: str,
    normalized_url: str,
    discovery_observer: Callable[[str, Mapping[str, object]], None] | None,
) -> EmployerResolutionResult:
    """Enable an unfamiliar public careers page only after extracting real jobs."""

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(
        _resolve_generic_source,
        display_name=display_name,
        normalized_url=normalized_url,
        discovery_observer=discovery_observer,
        walmart_scope=walmart_scope_config(
            get_profile(database_path, profile_id).preferences
        ),
    )
    try:
        source_result = future.result(timeout=_COMPANY_DISCOVERY_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        future.cancel()
        return EmployerResolutionResult(
            status=DISCOVERY_TIMED_OUT,
            message=(
                "Junior stopped checking after two minutes and did not add "
                "the company. The careers site may be slow or temporarily "
                "unavailable. You can safely try again later."
            ),
            employer_name=display_name,
            careers_url=normalized_url,
        )
    finally:
        # Discovery performs network reads only. A timed-out worker may finish
        # its current bounded request, but it cannot write durable user data.
        executor.shutdown(wait=False, cancel_futures=True)

    if isinstance(source_result, EmployerResolutionResult):
        return source_result
    discovered, job_count = source_result
    return _create_and_assign_scan_ready(
        database_path,
        profile_id=profile_id,
        display_name=display_name,
        normalized_name=normalized_name,
        normalized_url=normalized_url,
        detection=discovered,
        connection_job_count=job_count,
    )


def _create_and_assign_name_only(
    database_path: Path,
    *,
    profile_id: str,
    display_name: str,
    normalized_name: str,
    discovery_observer: Callable[[str, Mapping[str, object]], None] | None,
) -> EmployerResolutionResult:
    """Resolve a company name without creating unfinished administrator work."""

    return EmployerResolutionResult(
        status=UNSUPPORTED_SITE,
        message=(
            "Junior did not find that name in this installation's company "
            "catalog. To add a new company, paste any official company webpage, "
            "such as its homepage, careers page, or a public job posting."
        ),
        employer_name=display_name,
    )

def _resolve_generic_source(
    *,
    display_name: str,
    normalized_url: str,
    discovery_observer: Callable[[str, Mapping[str, object]], None] | None,
    walmart_scope: Mapping[str, object] | None = None,
) -> EmployerResolutionResult | tuple[DetectedEmployerSource, int]:
    """Run bounded network-only discovery without writing application data."""

    discoveries = _discover_branded_sources(
        normalized_url,
        discovery_observer=discovery_observer,
    )
    discoveries.sort(key=_discovery_priority)
    discoveries.append(
        DetectedEmployerSource(
            source_type="html",
            source_identifier=None,
            source_config={"source_url": normalized_url},
            scan_ready=True,
        )
    )
    discoveries.extend(_domain_slug_ats_candidates(normalized_url))
    tested_source = _first_working_source(
        discoveries,
        display_name=display_name,
        discovery_observer=discovery_observer,
        walmart_scope=walmart_scope,
    )
    if tested_source is None:
        if any(
            "explicit no current openings" in item.evidence
            or item.source_config.get("validate_deadlines") is True
            for item in discoveries
        ):
            return EmployerResolutionResult(
                status=NO_CURRENT_JOBS,
                message=(
                    "Junior reached the employer's live careers page and it "
                    "currently states that there are no open positions. No "
                    "company was added because Junior requires at least one "
                    "actual job before saving a new source. Try this same URL "
                    "again when the employer is hiring."
                ),
                employer_name=display_name,
                careers_url=normalized_url,
            )
        return EmployerResolutionResult(
            status=UNSUPPORTED_SITE,
            message=(
                "Junior confirmed this is a public company website but could "
                "not yet identify and validate its job platform. No company "
                "was added. You do not need to find another URL; this is a "
                "Junior compatibility limitation. Contact Clayton Graves at "
                "claytonmgraves@outlook.com and include the public company "
                "URL. Do not send passwords, access tokens, resumes, or other "
                "private data."
            ),
            employer_name=display_name,
            careers_url=normalized_url,
        )
    return tested_source


def _discovery_priority(discovery: DetectedEmployerSource) -> int:
    """Prefer complete feeds over landing-page teasers without losing order."""

    if "embedded public job data" in discovery.evidence:
        return 0
    source_url = str(discovery.source_config.get("source_url") or "")
    careers_url = str(discovery.source_config.get("careers_url") or "")
    if discovery.source_type == "html" and _same_public_url(source_url, careers_url):
        return 1
    if discovery.source_type != "html":
        return 2
    return 3


def _same_public_url(left: str, right: str) -> bool:
    """Compare user-facing URLs without insignificant trailing slashes."""

    if not left or not right:
        return False
    parsed_left = urlsplit(left)
    parsed_right = urlsplit(right)
    return (
        parsed_left.scheme.casefold() == parsed_right.scheme.casefold()
        and parsed_left.netloc.casefold() == parsed_right.netloc.casefold()
        and parsed_left.path.rstrip("/").casefold()
        == parsed_right.path.rstrip("/").casefold()
        and parsed_left.query == parsed_right.query
    )


def _domain_slug_ats_candidates(careers_url: str) -> list[DetectedEmployerSource]:
    """Build bounded public ATS probes from an official company's domain.

    Some legitimate career pages block automated page reads even though their
    public ATS board remains available. The domain label is used only as an
    exact board identifier; the normal collector must still return real jobs
    before Junior accepts any candidate.
    """

    host = (urlsplit(careers_url).hostname or "").casefold().strip(".")
    labels = [label for label in host.split(".") if label]
    if labels and labels[0] in {"careers", "jobs", "www"}:
        labels.pop(0)
    if len(labels) < 2:
        return []
    suffix_length = 2 if ".".join(labels[-2:]) in _COMMON_SECOND_LEVEL_SUFFIXES else 1
    company_index = len(labels) - suffix_length - 1
    if company_index < 0:
        return []
    slug = labels[company_index]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", slug):
        return []

    slugs = [slug]
    for suffix in _DOMAIN_COMPANY_SUFFIXES:
        shortened = slug.removesuffix(suffix).rstrip("-")
        if shortened != slug and len(shortened) >= 3:
            slugs.append(shortened)
    candidates: list[DetectedEmployerSource] = []
    for candidate_slug in dict.fromkeys(slugs):
        for template in _DOMAIN_SLUG_ATS_URLS:
            detected = detect_employer_source(template.format(slug=candidate_slug))
            if not detected.scan_ready:
                continue
            candidates.append(
                DetectedEmployerSource(
                    source_type=detected.source_type,
                    source_identifier=detected.source_identifier,
                    source_config={
                        **detected.source_config,
                        "careers_url": careers_url,
                    },
                    scan_ready=True,
                    confidence="medium",
                    evidence=("official-domain ATS board probe",),
                )
            )
    return candidates


def _first_working_source(
    discoveries: list[DetectedEmployerSource],
    *,
    display_name: str,
    discovery_observer: Callable[[str, Mapping[str, object]], None] | None = None,
    walmart_scope: Mapping[str, object] | None = None,
) -> tuple[DetectedEmployerSource, int] | None:
    """Probe derived collector configurations and keep the first real job feed."""

    seen: set[tuple[str | None, str]] = set()
    for candidate_number, discovery in enumerate(discoveries, start=1):
        config_key = (
            discovery.source_type,
            json.dumps(discovery.source_config, sort_keys=True),
        )
        if config_key in seen:
            continue
        seen.add(config_key)
        candidate_config: dict[str, object] = {
            "company_key": _employer_id(display_name),
            "name": display_name,
            "source_type": discovery.source_type,
            **discovery.source_config,
            # Company setup must prove the saved collector can traverse its
            # normal result depth, not merely parse a convenient first page.
            "connection_test": True,
        }
        if discovery.source_type == "walmart" and walmart_scope is not None:
            candidate_config.update(walmart_scope)
        try:
            postings = collect_jobs_for_company(candidate_config)
        except (CollectorError, OSError, ValueError, requests.RequestException):
            _observe_discovery(
                discovery_observer,
                "candidate_test",
                candidate_number=candidate_number,
                candidate_host=_source_host(discovery),
                source_type=discovery.source_type or "unknown",
                outcome="failed",
            )
            continue
        if postings:
            _observe_discovery(
                discovery_observer,
                "candidate_test",
                candidate_number=candidate_number,
                candidate_host=_source_host(discovery),
                source_type=discovery.source_type or "unknown",
                outcome="verified",
                job_count=len(postings),
            )
            return discovery, len(postings)
        _observe_discovery(
            discovery_observer,
            "candidate_test",
            candidate_number=candidate_number,
            candidate_host=_source_host(discovery),
            source_type=discovery.source_type or "unknown",
            outcome="no_jobs",
            job_count=0,
        )
    return None


def _source_test_failed() -> EmployerResolutionResult:
    return EmployerResolutionResult(
        status=UNSUPPORTED_SITE,
        message=(
            "Junior accepted this public careers address, but could not verify "
            "a supported source containing actual job postings. No company "
            "was added. You do not need to find a different recruiting-platform "
            "URL. Contact Clayton Graves at claytonmgraves@outlook.com and "
            "include this public careers URL. Do not send passwords, access "
            "tokens, résumés, or other private data."
        ),
    )


def _discover_branded_sources(
    careers_url: str,
    *,
    discovery_observer: Callable[[str, Mapping[str, object]], None] | None = None,
) -> list[DetectedEmployerSource]:
    """Traverse bounded official pages and rank complete platform sources."""

    parsed_input = urlsplit(careers_url)
    official_host = (parsed_input.hostname or "").casefold()
    trusted_hosts = {official_host}
    queue = [careers_url]
    queued = {careers_url.casefold()}
    visited: set[str] = set()
    discoveries = _known_public_handoff_sources(careers_url)
    document_bytes = 0

    while queue and len(visited) < _DISCOVERY_MAX_PAGES:
        page_url = queue.pop(0)
        key = page_url.casefold()
        if key in visited:
            continue
        visited.add(key)
        _observe_discovery(
            discovery_observer,
            "page_fetch_started",
            page_number=len(visited),
            queue_depth=len(queue),
            candidate_host=(urlsplit(page_url).hostname or "").casefold(),
        )
        try:
            response = get_response(
                page_url,
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36 Junior/0.2"
                    ),
                },
                timeout=20,
            )
        except requests.RequestException:
            _observe_discovery(
                discovery_observer,
                "page_fetch_finished",
                page_number=len(visited),
                candidate_host=(urlsplit(page_url).hostname or "").casefold(),
                outcome="failed",
            )
            continue
        html = response.text
        response_host = (urlsplit(response.url).hostname or "").casefold()
        # A server redirect from a URL already trusted for this request is an
        # explicit careers handoff, such as a corporate page moving to its
        # branded recruiting subsite.
        requested_host = (urlsplit(page_url).hostname or "").casefold()
        if any(_hosts_are_related(requested_host, host) for host in trusted_hosts):
            trusted_hosts.add(response_host)
        discoveries.extend(
            _discover_sources_from_document(
                source_url=response.url,
                careers_url=careers_url,
                html=html,
            )
        )
        document_bytes += len(html.encode("utf-8", errors="ignore"))
        _observe_discovery(
            discovery_observer,
            "page_fetch_finished",
            page_number=len(visited),
            candidate_host=(urlsplit(response.url).hostname or "").casefold(),
            document_bytes=document_bytes,
            outcome="inspected",
        )
        if document_bytes > _DISCOVERY_MAX_DOCUMENT_BYTES:
            break
        advertised_urls = _advertised_page_urls(response.url, html)
        for advertised_url in advertised_urls:
            detected = detect_employer_source(advertised_url)
            if detected.scan_ready:
                discoveries.append(
                    DetectedEmployerSource(
                        source_type=detected.source_type,
                        source_identifier=detected.source_identifier,
                        source_config={
                            **detected.source_config,
                            "careers_url": careers_url,
                        },
                        scan_ready=True,
                        confidence=detected.confidence,
                        evidence=detected.evidence,
                    )
                )
            if _should_follow_discovery_page(
                advertised_url,
                source_host=response_host,
                trusted_hosts=trusted_hosts,
                allow_bootstrap_script=(len(visited) == 1 and len(html) < 50_000),
            ):
                candidate_key = advertised_url.casefold()
                if candidate_key not in queued and candidate_key not in visited:
                    queue.append(advertised_url)
                    queued.add(candidate_key)
        if len(visited) == 1:
            origin = urlsplit(response.url)
            root = urlunsplit((origin.scheme, origin.netloc, "/", "", ""))
            for path in (
                "/wp-sitemap.xml",
                "/careers",
                "/jobs",
                "/join-us",
                "/work-with-us",
            ):
                candidate = urljoin(root, path)
                candidate_key = candidate.casefold()
                if candidate_key not in queued:
                    queue.append(candidate)
                    queued.add(candidate_key)
    unique = _deduplicate_discoveries(discoveries)
    _observe_discovery(
        discovery_observer,
        "source_discovery_finished",
        page_number=len(visited),
        document_bytes=document_bytes,
        candidate_number=len(unique),
        outcome="candidates" if unique else "not_found",
    )
    return unique


def _known_public_handoff_sources(
    careers_url: str,
) -> list[DetectedEmployerSource]:
    """Return maintained ATS handoffs for official pages that block discovery."""

    parsed = urlsplit(careers_url)
    handoff = _KNOWN_PUBLIC_CAREER_HANDOFFS.get(
        ((parsed.hostname or "").casefold(), parsed.path.rstrip("/").casefold())
    )
    if handoff is None:
        return []
    detected = detect_employer_source(handoff)
    if not detected.scan_ready:
        return []
    return [
        DetectedEmployerSource(
            source_type=detected.source_type,
            source_identifier=detected.source_identifier,
            source_config={
                **detected.source_config,
                "careers_url": careers_url,
            },
            scan_ready=True,
            confidence="high",
            evidence=("maintained public careers handoff",),
        )
    ]


def _advertised_page_urls(source_url: str, html: str) -> list[str]:
    """Extract linked and embedded URLs without executing page scripts."""

    values = [source_url]
    values.extend(
        urljoin(source_url, unescape(value))
        for value in re.findall(
            r"(?:href|src|action)=[\"']([^\"']+)[\"']",
            html,
            flags=re.IGNORECASE,
        )
    )
    # Modern company sites often lazy-load the careers route. Inspect only
    # explicitly career/job-named same-site modules; the normal page and byte
    # ceilings still bound traversal and no script is executed.
    values.extend(
        urljoin(source_url, unescape(value))
        for value in re.findall(
            r"[\"']([^\"']*(?:career|job)[^\"']*\.js)[\"']",
            html,
            flags=re.IGNORECASE,
        )
    )
    values.extend(
        unescape(value)
        for value in re.findall(
            r"https://[^\"'<>()\s\\]+",
            html,
            flags=re.IGNORECASE,
        )
    )
    normalized: list[str] = []
    for value in values:
        try:
            normalized.append(normalize_careers_url(value))
        except ValueError:
            continue
    return list(dict.fromkeys(normalized))


def _should_follow_discovery_page(
    url: str,
    *,
    source_host: str,
    trusted_hosts: set[str],
    allow_bootstrap_script: bool = False,
) -> bool:
    """Allow bounded same-site traversal and explicit recruiting handoffs."""

    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold()
    if not host or parsed.scheme.casefold() != "https":
        return False
    target = f"{parsed.path}?{parsed.query}".casefold()
    if allow_bootstrap_script and parsed.path.casefold().endswith(".js") and any(
        _hosts_are_related(host, trusted) for trusted in trusted_hosts
    ):
        return True
    if not any(term in target for term in _CAREER_LINK_TERMS):
        return False
    if any(_hosts_are_related(host, trusted) for trusted in trusted_hosts):
        return True
    if not any(_hosts_are_related(source_host, trusted) for trusted in trusted_hosts):
        return False
    blocked = host.removeprefix("www.")
    return not any(
        blocked == denied or blocked.endswith(f".{denied}")
        for denied in _EXTERNAL_HANDOFF_BLOCKED_HOSTS
    )


def _hosts_are_related(left: str, right: str) -> bool:
    return bool(
        left == right
        or left.endswith(f".{right}")
        or right.endswith(f".{left}")
    )


def _deduplicate_discoveries(
    discoveries: list[DetectedEmployerSource],
) -> list[DetectedEmployerSource]:
    unique: dict[tuple[str | None, str], DetectedEmployerSource] = {}
    for discovery in discoveries:
        key = (
            discovery.source_type,
            json.dumps(discovery.source_config, sort_keys=True),
        )
        unique.setdefault(key, discovery)
    return list(unique.values())


def _discover_single_page_sources(
    careers_url: str,
) -> list[DetectedEmployerSource]:
    """Derive credible collector configurations advertised by a public page."""

    try:
        response = get_response(
            careers_url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "JobRadar/0.1 local career-source scanner",
            },
            timeout=30,
        )
    except requests.RequestException:
        return []
    return _discover_sources_from_document(
        source_url=response.url,
        careers_url=careers_url,
        html=response.text,
    )


def _discover_sources_from_document(
    *, source_url: str, careers_url: str, html: str
) -> list[DetectedEmployerSource]:
    """Extract collector configurations from one already-fetched document."""

    discoveries: list[DetectedEmployerSource] = []
    document_text = clean_human_text(html)
    if re.search(
        r"\b(?:there are no current openings|currently there are no openings|"
        r"we are not currently hiring|no current vacancies)\b",
        document_text,
        flags=re.IGNORECASE,
    ) or _document_reports_expired_opening(document_text):
        discoveries.append(
            DetectedEmployerSource(
                source_type=None,
                source_identifier=None,
                source_config={},
                scan_ready=False,
                evidence=("explicit no current openings",),
            )
        )
    advertised_urls = [source_url]
    advertised_urls.extend(
        urljoin(source_url, unescape(match))
        for match in re.findall(
            r'href=["\']([^"\']+)["\']',
            html,
            flags=re.IGNORECASE,
        )
    )
    html_source = _html_detection_from_document(
        source_url=source_url,
        careers_url=careers_url,
        html=html,
        advertised_urls=advertised_urls,
    )
    if html_source is not None:
        discoveries.append(html_source)
    for advertised_url in advertised_urls:
        try:
            normalized_advertised_url = normalize_careers_url(advertised_url)
        except ValueError:
            continue
        detected = detect_employer_source(normalized_advertised_url)
        if detected.scan_ready:
            discoveries.append(
                DetectedEmployerSource(
                    source_type=detected.source_type,
                    source_identifier=detected.source_identifier,
                    source_config={
                        **detected.source_config,
                        "careers_url": careers_url,
                    },
                    scan_ready=True,
                )
            )
    custom_eightfold = _eightfold_detection_from_html(
        source_url=source_url,
        careers_url=careers_url,
        html=html,
    )
    if custom_eightfold is not None:
        discoveries.append(custom_eightfold)
    talentbrew = _talentbrew_detection_from_html(
        source_url=source_url,
        careers_url=careers_url,
        html=html,
    )
    if talentbrew is not None:
        discoveries.append(talentbrew)
    workday_links = re.findall(
        r'https://[^"\'<>\s]+\.myworkdayjobs\.com/[^"\'<>\s?&]+',
        unescape(html),
        flags=re.IGNORECASE,
    )
    for workday_link in workday_links:
        detected = _workday_detection(workday_link, careers_url)
        if detected is not None:
            discoveries.append(detected)
    base_tag = re.search(r"<base\b[^>]*>", html, flags=re.IGNORECASE)
    if base_tag is not None:
        api_match = re.search(
            r'data-apibaseurl=["\']([^"\']+)["\']',
            base_tag.group(0),
            flags=re.IGNORECASE,
        )
        site_match = re.search(
            r'data-sitenumber=["\']([^"\']+)["\']',
            base_tag.group(0),
            flags=re.IGNORECASE,
        )
        if api_match and site_match:
            api_base = api_match.group(1).rstrip("/")
            site_number = site_match.group(1)
            discoveries.append(
                DetectedEmployerSource(
                    source_type="oracle_hcm",
                    source_identifier=(
                        f"{api_base.casefold()}:{site_number.casefold()}"
                    ),
                    source_config={
                        "source_url": (
                            f"{api_base}/hcmRestApi/resources/latest/"
                            "recruitingCEJobRequisitions"
                        ),
                        "site_number": site_number,
                        "referer_url": careers_url,
                        "careers_url": careers_url,
                    },
                    scan_ready=True,
                )
            )
    return discoveries


def _html_detection_from_document(
    *,
    source_url: str,
    careers_url: str,
    html: str,
    advertised_urls: list[str],
) -> DetectedEmployerSource | None:
    """Recognize an authoritative public page containing repeated job records."""

    patterns: list[str] = []
    paths = [urlsplit(url).path for url in advertised_urls]
    for pattern in (
        "/careers/positions/",
        "/hcmUI/CandidateExperience/",
        "/job-post/",
        "/jobs/",
        "/job/",
    ):
        detail_paths = {
            path
            for path in paths
            if pattern.casefold() in path.casefold()
            and path.rstrip("/").casefold()
            != pattern.rstrip("/").casefold()
        }
        if len(detail_paths) >= 2:
            patterns.append(pattern)
    has_embedded_jobs = bool(
        re.search(r"\b(?:const|let|var)\s+jobsData\s*=\s*\[", html)
    )
    if not patterns and not has_embedded_jobs:
        return None
    parsed = urlsplit(source_url)
    if not parsed.hostname:
        return None
    return DetectedEmployerSource(
        source_type="html",
        source_identifier=(
            f"html:{parsed.hostname.casefold()}:{parsed.path.rstrip('/') or '/'}"
        ),
        source_config={
            "source_url": source_url,
            "careers_url": careers_url,
            "job_link_patterns": patterns,
            "validate_deadlines": "/job-post/" in patterns,
        },
        scan_ready=True,
        evidence=(
            "embedded public job data"
            if has_embedded_jobs
            else "repeated public job records",
        ),
    )


def _document_reports_expired_opening(
    text: str,
    *,
    today: date | None = None,
) -> bool:
    """Recognize an explicit application deadline that has already passed."""

    current_date = today or date.today()
    matches = re.findall(
        r"(?:end date for tendering position|application deadline|closing date)"
        r"\s*:?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4}|"
        r"\d{1,2}\s+[A-Za-z]+\s+\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    for value in matches:
        normalized = " ".join(value.replace(",", "").split())
        for date_format in ("%B %d %Y", "%d %B %Y"):
            try:
                deadline = datetime.strptime(normalized, date_format).date()
            except ValueError:
                continue
            if deadline < current_date:
                return True
    return False


def _discover_custom_platform(
    source_url: str,
    *,
    careers_url: str,
) -> DetectedEmployerSource | None:
    """Recognize a supported platform hosted on an employer-owned domain."""

    try:
        response = get_response(
            source_url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "Junior/0.2 local career-source discovery",
            },
            timeout=20,
        )
    except requests.RequestException:
        return None
    return _eightfold_detection_from_html(
        source_url=response.url,
        careers_url=careers_url,
        html=response.text,
    )


def _eightfold_detection_from_html(
    *,
    source_url: str,
    careers_url: str,
    html: str,
) -> DetectedEmployerSource | None:
    """Build Eightfold settings from its public custom-domain page markers."""

    if "eightfold" not in html.casefold() and "vscdn.net" not in html.casefold():
        return None
    domain_match = re.search(
        r'window\._EF_GROUP_ID\s*=\s*["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE,
    )
    if domain_match is None:
        return None
    parsed = urlsplit(source_url)
    if not parsed.hostname:
        return None
    source_root = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    domain = domain_match.group(1).strip()
    return DetectedEmployerSource(
        source_type="eightfold",
        source_identifier=f"{parsed.hostname.casefold()}:{domain.casefold()}",
        source_config={
            "source_url": source_root,
            "domain": domain,
            "careers_url": careers_url,
        },
        scan_ready=True,
    )


def _talentbrew_detection_from_html(
    *,
    source_url: str,
    careers_url: str,
    html: str,
) -> DetectedEmployerSource | None:
    """Recognize TalentBrew sites and test their standard job-search page."""

    lowered = html.casefold()
    if "talentbrew" not in lowered and "tbcdn." not in lowered:
        return None
    parsed = urlsplit(source_url)
    if not parsed.hostname:
        return None
    source_root = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    source_path = parsed.path.rstrip("/")
    if "/search-jobs" in source_path.casefold():
        scope_query = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.casefold() not in _TALENTBREW_NON_SCOPE_QUERY_KEYS
        ]
        search_url = urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                source_path,
                urlencode(scope_query, doseq=True),
                "",
            )
        )
    else:
        search_url = urljoin(source_root, "/search-jobs")
    return DetectedEmployerSource(
        source_type="talentbrew",
        source_identifier=(
            f"talentbrew:{parsed.hostname.casefold()}:{search_url.casefold()}"
        ),
        source_config={
            "source_url": search_url,
            "careers_url": careers_url,
            "job_link_patterns": ["/job/"],
        },
        scan_ready=True,
    )


def _source_host(discovery: DetectedEmployerSource) -> str:
    source_url = str(discovery.source_config.get("source_url", ""))
    return (urlsplit(source_url).hostname or "unknown").casefold()


def _observe_discovery(
    observer: Callable[[str, Mapping[str, object]], None] | None,
    stage: str,
    **fields: object,
) -> None:
    if observer is not None:
        try:
            observer(stage, fields)
        except OSError:
            # Diagnostics are helpful, but a log-write problem must never stop
            # Junior from validating an otherwise usable company source.
            return




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
        "adp": "ADP",
        "recruitee": "Recruitee",
        "icims": "iCIMS",
        "ukg": "UKG Pro Recruiting",
        "eightfold": "Eightfold",
        "google_careers": "Google Careers",
        "walmart": "Walmart Careers",
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
    configured_name = detection.source_config.get("display_name")
    if configured_name:
        return configured_name
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
