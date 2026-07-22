"""Resolve the employer sources used by a scan from the active profile."""

from pathlib import Path
from typing import Any

from job_radar.config import ConfigError, load_companies
from job_radar.employer_import import import_pending_legacy_employers
from job_radar.employer_storage import (
    get_employer_source,
    is_profile_employer_enabled,
)
from job_radar.profile_storage import get_active_profile
from job_radar.storage import initialize_database


def resolve_scan_companies(
    database_path: str | Path,
    company_config_path: str | Path,
) -> list[dict[str, Any]]:
    """Resolve enabled scan sources without leaking employers across profiles."""

    db_path = initialize_database(database_path)

    import_pending_legacy_employers(
        db_path,
        company_config_path,
    )

    active_profile = get_active_profile(db_path)

    if active_profile is None:
        return load_companies(company_config_path)

    companies: list[dict[str, Any]] = []

    for employer_id in active_profile.company_ids:
        employer = get_employer_source(db_path, employer_id)

        if employer is None:
            raise ConfigError(
                "The active profile references an employer source that no "
                f"longer exists: {employer_id}"
            )

        if (
            is_profile_employer_enabled(
                db_path,
                active_profile.profile_id,
                employer_id,
            )
            and employer.enabled
        ):
            companies.append(employer.to_company_config())

    if not companies:
        raise ConfigError(
            f'The active profile "{active_profile.display_name}" has no enabled '
            "employers. Add or enable at least one employer before running a scan."
        )

    return companies
