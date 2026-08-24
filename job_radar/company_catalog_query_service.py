"""Present safe employer-catalog choices to normal profile users."""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import (
    list_employer_sources,
    list_profile_employer_assignments,
)
from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import get_active_profile
from job_radar.storage import initialize_database


AVAILABLE = "available"
ALREADY_ADDED = "already_added"
NEEDS_SETUP = "needs_setup"
UNAVAILABLE = "unavailable"

_SLUG_SOURCE_TYPES = {"ashby", "greenhouse", "lever", "rippling"}
_URL_SOURCE_TYPES = {
    "avature",
    "dayforce",
    "eightfold",
    "html",
    "icims",
    "jibe",
    "jobsyn",
    "google_careers",
    "oracle_hcm",
    "phenom",
    "recruitee",
    "selectminds",
    "smartrecruiters",
    "talentbrew",
    "walmart",
    "weka",
    "workday",
}


@dataclass(frozen=True)
class EmployerAvailability:
    """Describe whether one catalog employer can be assigned for scanning."""

    state: str
    can_assign: bool
    explanation: str


@dataclass(frozen=True)
class CompanyCatalogItem:
    """Expose only normal-user-safe catalog fields."""

    employer_id: str
    name: str
    state: str
    state_label: str
    explanation: str
    careers_url: str | None
    can_assign: bool


@dataclass(frozen=True)
class CompanyCatalogView:
    """Provide the active profile and its filtered catalog choices."""

    active_profile: ManagedProfile | None
    companies: tuple[CompanyCatalogItem, ...]
    search_query: str


def build_company_catalog_view(
    database_path: str | Path,
    *,
    search_query: str = "",
) -> CompanyCatalogView:
    """Build a safe, searchable catalog for the active profile."""

    db_path = initialize_database(database_path)
    active_profile = get_active_profile(db_path)
    normalized_query = search_query.strip()

    if active_profile is None:
        return CompanyCatalogView(None, (), normalized_query)

    assigned_ids = {
        assignment.employer_id
        for assignment in list_profile_employer_assignments(
            db_path,
            active_profile.profile_id,
        )
    }
    items: list[CompanyCatalogItem] = []

    for employer in list_employer_sources(db_path):
        if (
            normalized_query
            and normalized_query.casefold() not in employer.name.casefold()
        ):
            continue

        if employer.employer_id in assigned_ids:
            availability = EmployerAvailability(
                state=ALREADY_ADDED,
                can_assign=False,
                explanation="Already included in this profile.",
            )
        else:
            availability = evaluate_employer_availability(employer)

        items.append(
            CompanyCatalogItem(
                employer_id=employer.employer_id,
                name=employer.name,
                state=availability.state,
                state_label=_state_label(availability.state),
                explanation=availability.explanation,
                careers_url=_safe_careers_url(employer),
                can_assign=availability.can_assign,
            )
        )

    items.sort(key=lambda item: (item.name.casefold(), item.employer_id))
    return CompanyCatalogView(
        active_profile=active_profile,
        companies=tuple(items),
        search_query=normalized_query,
    )


def evaluate_employer_availability(
    employer: EmployerSource,
) -> EmployerAvailability:
    """Determine scan readiness once, outside routes and templates."""

    if not employer.enabled:
        return EmployerAvailability(
            state=UNAVAILABLE,
            can_assign=False,
            explanation="This company is currently unavailable for scanning.",
        )

    if not _has_complete_source_config(employer):
        return EmployerAvailability(
            state=NEEDS_SETUP,
            can_assign=False,
            explanation=(
                "This company needs administrator setup before junior can scan it."
            ),
        )

    return EmployerAvailability(
        state=AVAILABLE,
        can_assign=True,
        explanation="Ready to add and scan for this profile.",
    )


def _has_complete_source_config(employer: EmployerSource) -> bool:
    config = employer.source_config
    source_type = employer.source_type

    if source_type in _SLUG_SOURCE_TYPES:
        return _has_text(config.get("source_slug"))

    if source_type == "eightfold":
        return _has_http_url(config.get("source_url")) and bool(
            str(config.get("domain") or "").strip()
        )
    if source_type in _URL_SOURCE_TYPES:
        return _has_http_url(config.get("source_url"))

    if source_type == "activate":
        return _has_http_url(config.get("source_url")) and _has_http_url(
            config.get("source_base_url")
        )

    if source_type == "adp":
        source_url = config.get("source_url")
        if not _has_http_url(source_url):
            return False
        query = parse_qs(urlparse(str(source_url)).query)
        return (
            _has_text(config.get("cid")) or _has_text(query.get("cid", [None])[0])
        ) and (
            _has_text(config.get("ccId"))
            or _has_text(query.get("ccId", [None])[0])
        )

    if source_type == "schoolspring":
        return _has_text(config.get("domain_name")) or _has_text(
            config.get("source_slug")
        )

    if source_type == "usajobs":
        query_params = config.get("query_params")
        return isinstance(query_params, dict) and bool(query_params)

    return False


def _safe_careers_url(employer: EmployerSource) -> str | None:
    careers_url = employer.source_config.get("careers_url")
    if _has_http_url(careers_url):
        return str(careers_url).strip()

    # Generic HTML sources are public career pages. Other source URLs may be
    # collector API endpoints and must stay out of the normal-user view.
    source_url = employer.source_config.get("source_url")
    if employer.source_type == "html" and _has_http_url(source_url):
        return str(source_url).strip()
    return None


def _has_http_url(value: object) -> bool:
    if not _has_text(value):
        return False
    parsed = urlparse(str(value).strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _state_label(state: str) -> str:
    return {
        AVAILABLE: "Available",
        ALREADY_ADDED: "Already added",
        NEEDS_SETUP: "Needs setup",
        UNAVAILABLE: "Unavailable",
    }[state]
