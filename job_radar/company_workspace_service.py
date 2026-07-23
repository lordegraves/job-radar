"""Build the profile-owned company workspace shown to normal users."""

from dataclasses import dataclass
from pathlib import Path

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
