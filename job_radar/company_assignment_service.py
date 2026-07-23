"""Change one profile's company scanning state without altering the catalog."""

from dataclasses import dataclass
from pathlib import Path

from job_radar.domain_errors import (
    EmployerNotAssignedError,
    EmployerNotFoundError,
    NoActiveProfileError,
)
from job_radar.employer_storage import (
    get_employer_source,
    list_profile_employer_assignments,
    set_profile_employer_enabled,
)
from job_radar.profile_storage import get_active_profile
from job_radar.storage import initialize_database


@dataclass(frozen=True)
class CompanyScanningStateResult:
    """Describe the profile-specific state that was durably saved."""

    profile_id: str
    profile_name: str
    employer_id: str
    employer_name: str
    scanning: bool


def set_company_scanning_state(
    database_path: str | Path,
    profile_id: str,
    employer_id: str,
    *,
    scanning: bool,
) -> CompanyScanningStateResult:
    """Pause or resume one company for the active managed profile."""

    if not isinstance(scanning, bool):
        raise ValueError("company scanning state must be a boolean")

    db_path = initialize_database(database_path)
    active_profile = get_active_profile(db_path)

    if active_profile is None:
        raise NoActiveProfileError(
            "Select a managed profile before changing a company."
        )

    # Reject stale or cross-profile requests instead of changing whichever
    # profile happens to be active when the request reaches the service.
    if active_profile.profile_id != profile_id:
        raise EmployerNotAssignedError(
            "This company does not belong to the active profile."
        )

    employer = get_employer_source(db_path, employer_id)
    if employer is None:
        raise EmployerNotFoundError("The requested company no longer exists.")

    assignment = next(
        (
            item
            for item in list_profile_employer_assignments(db_path, profile_id)
            if item.employer_id == employer_id
        ),
        None,
    )
    if assignment is None:
        raise EmployerNotAssignedError(
            "This company does not belong to the active profile."
        )

    if assignment.enabled != scanning:
        updated = set_profile_employer_enabled(
            db_path,
            profile_id,
            employer_id,
            enabled=scanning,
        )
        if not updated:
            raise EmployerNotAssignedError(
                "This company does not belong to the active profile."
            )

    return CompanyScanningStateResult(
        profile_id=active_profile.profile_id,
        profile_name=active_profile.display_name,
        employer_id=employer.employer_id,
        employer_name=employer.name,
        scanning=scanning,
    )
