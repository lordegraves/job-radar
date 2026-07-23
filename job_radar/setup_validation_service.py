"""Validate first-run profile and company setup without importing jobs."""

from dataclasses import dataclass
from pathlib import Path

from job_radar.company_workspace_service import build_company_workspace
from job_radar.database import connect_database
from job_radar.employer_connection_service import test_employer_connection
from job_radar.employer_storage import get_employer_source
from job_radar.setup_progress_service import get_setup_progress
from job_radar.storage import initialize_database


MAX_COMPANIES_TO_TEST = 25


@dataclass(frozen=True)
class SetupValidationCompany:
    """Describe one safe company connection result shown during setup."""

    name: str
    connected: bool
    message: str


@dataclass(frozen=True)
class SetupValidationResult:
    """Summarize whether first-run setup is ready for normal operation."""

    passed: bool
    message: str
    issues: tuple[str, ...]
    companies: tuple[SetupValidationCompany, ...]
    validated_employer_id: str | None = None


def validate_first_run_setup(
    database_path: str | Path,
) -> SetupValidationResult:
    """Check saved profile rules and prove at least one source can connect."""

    workspace = build_company_workspace(database_path)
    profile = workspace.active_profile
    progress = get_setup_progress(database_path)
    issues: list[str] = []
    if profile is None:
        issues.append("Create and select a profile.")
    elif progress is None or progress.profile_id != profile.profile_id:
        issues.append(
            "Return to profile setup and select the profile being configured."
        )
    else:
        preferences = profile.preferences
        if not preferences.target_roles:
            issues.append("Add at least one target role to the profile.")
        if not preferences.work_arrangements:
            issues.append("Choose at least one workplace arrangement.")
        office_modes = {"Hybrid", "On-site"}
        if (
            office_modes.intersection(preferences.work_arrangements)
            and not preferences.location_selections
        ):
            issues.append(
                "Add a location for hybrid or on-site commuting."
            )

    selected = [
        item for item in workspace.companies if item.scanning
    ][:MAX_COMPANIES_TO_TEST]
    if not selected:
        issues.append("Add at least one company and leave it set to Scanning.")

    company_results: list[SetupValidationCompany] = []
    successful_employer_id: str | None = None
    successful_employer_name: str | None = None
    for item in selected:
        employer = get_employer_source(database_path, item.company_key)
        if employer is None or not employer.enabled:
            company_results.append(
                SetupValidationCompany(
                    name=item.name,
                    connected=False,
                    message=(
                        "This company is not currently available for scans. "
                        "Review it in Companies or Administration."
                    ),
                )
            )
            continue
        health = test_employer_connection(database_path, item.company_key)
        connected = health.state == "success"
        company_results.append(
            SetupValidationCompany(
                name=item.name,
                connected=connected,
                message=health.message or "Connection test completed.",
            )
        )
        if connected and successful_employer_id is None:
            successful_employer_id = item.company_key
            successful_employer_name = item.name

    if selected and successful_employer_id is None:
        issues.append(
            "Junior could not confirm a working source for any selected company."
        )
    passed = not issues and successful_employer_id is not None
    message = (
        f"Setup validation passed. Junior connected to "
        f"{successful_employer_name} without importing jobs."
        if passed
        else "Setup needs attention before Junior can finish."
    )
    result = SetupValidationResult(
        passed=passed,
        message=message,
        issues=tuple(issues),
        companies=tuple(company_results),
        validated_employer_id=successful_employer_id,
    )
    _store_result(database_path, result)
    return result


def _store_result(
    database_path: str | Path,
    result: SetupValidationResult,
) -> None:
    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.execute(
            """
            UPDATE setup_progress
            SET validation_state = ?,
                validation_message = ?,
                validated_employer_id = ?,
                validated_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE singleton_id = 1
              AND completed_at IS NULL
            """,
            (
                "passed" if result.passed else "failed",
                result.message,
                result.validated_employer_id,
            ),
        )
