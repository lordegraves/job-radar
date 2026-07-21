"""Resolve company-page records from an active profile or legacy YAML."""

from dataclasses import dataclass
from pathlib import Path

from job_radar.company_config_service import (
    CompanyConfigView,
    build_company_config_views,
    build_company_config_views_from_mappings,
)
from job_radar.employer_import import import_pending_legacy_employers
from job_radar.employer_storage import get_employer_source
from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import get_active_profile
from job_radar.storage import initialize_database


@dataclass(frozen=True)
class CompanyPageSource:
    """Describe the records and ownership context shown on company pages."""

    companies: list[CompanyConfigView]
    active_profile: ManagedProfile | None
    uses_legacy_yaml: bool
    company_config_path: str


def resolve_company_page_source(
    database_path: str | Path,
    company_config_path: str | Path,
) -> CompanyPageSource:
    """Resolve all employers visible to the current profile."""

    db_path = initialize_database(database_path)
    config_path = str(Path(company_config_path))

    import_pending_legacy_employers(
        db_path,
        company_config_path,
    )

    active_profile = get_active_profile(db_path)

    if active_profile is None:
        return CompanyPageSource(
            companies=build_company_config_views(config_path),
            active_profile=None,
            uses_legacy_yaml=True,
            company_config_path=config_path,
        )

    company_mappings: list[dict[str, object]] = []

    for employer_id in active_profile.company_ids:
        employer = get_employer_source(db_path, employer_id)

        if employer is None:
            continue

        company_mappings.append(employer.to_company_config())

    return CompanyPageSource(
        companies=build_company_config_views_from_mappings(
            company_mappings
        ),
        active_profile=active_profile,
        uses_legacy_yaml=False,
        company_config_path=config_path,
    )
