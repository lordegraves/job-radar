"""Build the profile-owned company workspace shown to normal users."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from job_radar.employer_connection_service import (
    EmployerConnectionHealth,
    get_employer_connection_health,
)
from job_radar.employer_storage import (
    get_employer_source,
    list_profile_employer_assignments,
)
from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import get_active_profile
from job_radar.storage import initialize_database


@dataclass(frozen=True)
class CompanyWorkspaceItem:
    """Describe one company and whether this profile will scan it."""

    company_key: str
    name: str
    scanning: bool
    source_type: str
    connection_health: EmployerConnectionHealth
    website_url: str | None = None
    careers_url: str | None = None
    linkedin_url: str | None = None
    glassdoor_url: str | None = None

    @property
    def source_label(self) -> str:
        """Return a readable collector name without exposing its settings."""

        return {
            "adp": "ADP Workforce Now",
            "eightfold": "Eightfold",
            "html": "Public careers page",
            "oracle_hcm": "Oracle Recruiting",
        }.get(
            self.source_type,
            self.source_type.replace("_", " ").title(),
        )

    @property
    def last_checked_label(self) -> str:
        """Format SQLite's UTC timestamp for the local desktop user."""

        value = self.connection_health.tested_at
        if not value:
            return "Not tested yet"
        try:
            parsed = datetime.fromisoformat(value).replace(tzinfo=UTC)
        except ValueError:
            return value
        return (
            parsed.astimezone()
            .strftime("%b %d, %Y at %I:%M %p")
            .replace(" 0", " ")
        )


@dataclass(frozen=True)
class CompanyWorkspaceView:
    """Provide one consistent company summary for Profile and Companies."""

    active_profile: ManagedProfile | None
    companies: tuple[CompanyWorkspaceItem, ...]
    total_companies: int
    scanning_companies: int
    paused_companies: int


def build_company_workspace(
    database_path: str | Path,
) -> CompanyWorkspaceView:
    """Build the active profile's user-facing company list and counts."""

    db_path = initialize_database(database_path)
    active_profile = get_active_profile(db_path)

    if active_profile is None:
        return CompanyWorkspaceView(None, (), 0, 0, 0)

    companies: list[CompanyWorkspaceItem] = []
    assignments = list_profile_employer_assignments(
        db_path,
        active_profile.profile_id,
    )

    for assignment in assignments:
        employer = get_employer_source(db_path, assignment.employer_id)

        # A damaged or partially migrated association must not break the page.
        if employer is None:
            continue

        companies.append(
            CompanyWorkspaceItem(
                company_key=employer.employer_id,
                name=employer.name,
                scanning=assignment.enabled,
                source_type=employer.source_type,
                connection_health=get_employer_connection_health(
                    db_path,
                    employer.employer_id,
                ),
                website_url=_optional_url(
                    employer.source_config.get("website_url")
                ),
                careers_url=_optional_url(
                    employer.source_config.get("careers_link_url")
                    or employer.source_config.get("careers_url")
                ),
                linkedin_url=_optional_url(
                    employer.source_config.get("linkedin_url")
                ),
                glassdoor_url=_optional_url(
                    employer.source_config.get("glassdoor_url")
                ),
            )
        )

    companies.sort(key=lambda company: (company.name.casefold(), company.company_key))
    company_items = tuple(companies)
    scanning_companies = sum(1 for company in company_items if company.scanning)

    return CompanyWorkspaceView(
        active_profile=active_profile,
        companies=company_items,
        total_companies=len(company_items),
        scanning_companies=scanning_companies,
        paused_companies=len(company_items) - scanning_companies,
    )


def _optional_url(value: object) -> str | None:
    """Expose only HTTP links to the normal-user template."""

    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if normalized.startswith(("http://", "https://")) else None
