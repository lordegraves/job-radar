"""Manage global employers and their profile assignments."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from job_radar.employer_models import EmployerSource
from job_radar.employer_storage import (
    assign_employer_to_profile,
    list_employer_sources,
    upsert_employer_source,
)
from job_radar.profile_storage import get_active_profile


class EmployerManagementError(RuntimeError):
    """Raised when a requested employer-management action cannot be completed."""


@dataclass(frozen=True)
class EmployerCreationResult:
    """Describe the employer selected or created for the active profile."""

    employer: EmployerSource
    created: bool
    assigned: bool


def add_employer_to_active_profile(
    database_path: str | Path,
    *,
    name: str,
    source_type: str,
    source_config: dict[str, Any],
    notes: str | None = None,
    enabled: bool = True,
) -> EmployerCreationResult:
    """Create or reuse a global employer and assign it to the active profile."""

    normalized_name = name.strip()

    if not normalized_name:
        raise EmployerManagementError("Employer name cannot be empty.")

    active_profile = get_active_profile(database_path)

    if active_profile is None:
        raise EmployerManagementError(
            "An active profile is required before an employer can be added."
        )

    existing_employer = _find_employer_by_name(
        database_path,
        normalized_name,
    )

    if existing_employer is not None:
        assigned = assign_employer_to_profile(
            database_path,
            active_profile.profile_id,
            existing_employer.employer_id,
        )
        return EmployerCreationResult(
            employer=existing_employer,
            created=False,
            assigned=assigned,
        )

    employer = EmployerSource(
        employer_id=_build_unique_employer_id(
            database_path,
            normalized_name,
        ),
        name=normalized_name,
        source_type=source_type,
        enabled=enabled,
        source_config=source_config,
        notes=notes.strip() if notes and notes.strip() else None,
    )
    upsert_employer_source(database_path, employer)
    assigned = assign_employer_to_profile(
        database_path,
        active_profile.profile_id,
        employer.employer_id,
    )

    return EmployerCreationResult(
        employer=employer,
        created=True,
        assigned=assigned,
    )


def _find_employer_by_name(
    database_path: str | Path,
    name: str,
) -> EmployerSource | None:
    normalized_name = name.casefold()

    for employer in list_employer_sources(database_path):
        if employer.name.strip().casefold() == normalized_name:
            return employer

    return None


def _build_unique_employer_id(
    database_path: str | Path,
    name: str,
) -> str:
    base_id = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")

    if not base_id:
        base_id = "employer"

    existing_ids = {
        employer.employer_id
        for employer in list_employer_sources(database_path)
    }

    if base_id not in existing_ids:
        return base_id

    suffix = 2

    while f"{base_id}_{suffix}" in existing_ids:
        suffix += 1

    return f"{base_id}_{suffix}"
