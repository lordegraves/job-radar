"""Change one profile's company scanning state without altering the catalog."""

from dataclasses import dataclass
from pathlib import Path

from job_radar.domain_errors import (
    EmployerAlreadyAssignedError,
    EmployerConfigurationError,
    EmployerNotAssignedError,
    EmployerNotFoundError,
    EmployerUnavailableError,
    NoActiveProfileError,
)
from job_radar.company_catalog_query_service import (
    NEEDS_SETUP,
    UNAVAILABLE,
    evaluate_employer_availability,
)
from job_radar.employer_storage import (
    assign_employer_to_profile,
    get_employer_source,
    list_profile_employer_assignments,
    set_profile_employer_enabled,
    unassign_employer_from_profile,
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


@dataclass(frozen=True)
class CompanyRemovalResult:
    """Describe the profile assignment removed without deleting history."""

    profile_id: str
    profile_name: str
    employer_id: str
    employer_name: str


@dataclass(frozen=True)
class CompanyAssignmentResult:
    """Describe an existing catalog employer assigned to one profile."""

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


def remove_company_from_profile(
    database_path: str | Path,
    profile_id: str,
    employer_id: str,
) -> CompanyRemovalResult:
    """Remove one employer from the active profile's future scans."""

    db_path = initialize_database(database_path)
    active_profile = get_active_profile(db_path)

    if active_profile is None:
        raise NoActiveProfileError(
            "Select a managed profile before removing a company."
        )

    if active_profile.profile_id != profile_id:
        raise EmployerNotAssignedError(
            "This company does not belong to the active profile."
        )

    employer = get_employer_source(db_path, employer_id)
    if employer is None:
        raise EmployerNotFoundError("The requested company no longer exists.")

    removed = unassign_employer_from_profile(
        db_path,
        profile_id,
        employer_id,
    )
    if not removed:
        raise EmployerNotAssignedError(
            "This company does not belong to the active profile."
        )

    return CompanyRemovalResult(
        profile_id=active_profile.profile_id,
        profile_name=active_profile.display_name,
        employer_id=employer.employer_id,
        employer_name=employer.name,
    )


def add_existing_company_to_profile(
    database_path: str | Path,
    profile_id: str,
    employer_id: str,
) -> CompanyAssignmentResult:
    """Assign one scan-ready catalog employer to the active profile."""

    db_path = initialize_database(database_path)
    active_profile = get_active_profile(db_path)

    if active_profile is None:
        raise NoActiveProfileError(
            "Select a managed profile before adding a company."
        )

    if active_profile.profile_id != profile_id:
        raise EmployerNotAssignedError(
            "The requested profile is no longer active."
        )

    employer = get_employer_source(db_path, employer_id)
    if employer is None:
        raise EmployerNotFoundError("The requested company no longer exists.")

    availability = evaluate_employer_availability(employer)
    if availability.state == UNAVAILABLE:
        raise EmployerUnavailableError(availability.explanation)
    if availability.state == NEEDS_SETUP:
        raise EmployerConfigurationError(availability.explanation)

    assigned = assign_employer_to_profile(
        db_path,
        active_profile.profile_id,
        employer.employer_id,
    )
    if not assigned:
        raise EmployerAlreadyAssignedError(
            "This company is already included in the active profile."
        )

    return CompanyAssignmentResult(
        profile_id=active_profile.profile_id,
        profile_name=active_profile.display_name,
        employer_id=employer.employer_id,
        employer_name=employer.name,
        scanning=True,
    )
