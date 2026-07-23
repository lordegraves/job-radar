"""Import legacy YAML employers into app-owned profile storage exactly once."""

import json
from pathlib import Path
from typing import Any

from job_radar.backup_service import create_database_safety_backup
from job_radar.config import (
    SUPPORTED_SOURCE_TYPES,
    ConfigError,
    load_yaml_file,
)
from job_radar.database import connect_database
from job_radar.employer_models import EmployerSource
from job_radar.storage import initialize_database


_LEGACY_CORE_KEYS = {
    "company_key",
    "name",
    "source_type",
    "enabled",
    "notes",
}


def import_pending_legacy_employers(
    database_path: str | Path,
    company_config_path: str | Path,
) -> str | None:
    """Import legacy YAML employers into the marked active profile once."""

    db_path = initialize_database(database_path)

    with connect_database(db_path) as connection:
        pending_profile = connection.execute(
            """
            SELECT profiles.profile_id
            FROM active_profile_selection
            JOIN profiles
              ON profiles.profile_id = active_profile_selection.profile_id
            WHERE active_profile_selection.singleton_id = 1
              AND profiles.archived = 0
              AND profiles.legacy_company_import_pending = 1
            """
        ).fetchone()

        if pending_profile is None:
            return None

        employers = _load_legacy_employers(company_config_path)
        profile_id = str(pending_profile[0])
        create_database_safety_backup(
            db_path,
            reason="legacy-company-import",
        )

        for employer in employers:
            connection.execute(
                """
                INSERT INTO employer_sources (
                    employer_id,
                    name,
                    source_type,
                    enabled,
                    source_config_json,
                    notes
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(employer_id) DO NOTHING
                """,
                (
                    employer.employer_id,
                    employer.name,
                    employer.source_type,
                    int(employer.enabled),
                    json.dumps(
                        employer.source_config,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    employer.notes,
                ),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO profile_company_associations (
                    profile_id,
                    company_id
                )
                VALUES (?, ?)
                """,
                (
                    profile_id,
                    employer.employer_id,
                ),
            )

        cursor = connection.execute(
            """
            UPDATE profiles
            SET legacy_company_import_pending = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE profile_id = ?
              AND legacy_company_import_pending = 1
            """,
            (profile_id,),
        )

        if cursor.rowcount != 1:
            return None

        return profile_id


def _load_legacy_employers(
    company_config_path: str | Path,
) -> tuple[EmployerSource, ...]:
    data = load_yaml_file(company_config_path)
    companies = data.get("companies")

    if companies is None:
        raise ConfigError(
            "company config must contain a top-level 'companies' list"
        )

    if not isinstance(companies, list):
        raise ConfigError("'companies' must be a list")

    employers: list[EmployerSource] = []
    seen_ids: set[str] = set()

    for index, company in enumerate(companies, start=1):
        if not isinstance(company, dict):
            raise ConfigError(f"Company entry #{index} must be a mapping")

        employer = _legacy_company_to_employer(company, index=index)

        if employer.employer_id in seen_ids:
            raise ConfigError(
                f"Duplicate company_key in company config: "
                f"{employer.employer_id}"
            )

        seen_ids.add(employer.employer_id)
        employers.append(employer)

    return tuple(employers)


def _legacy_company_to_employer(
    company: dict[str, Any],
    *,
    index: int,
) -> EmployerSource:
    employer_id = company.get("company_key")
    name = company.get("name")
    source_type = company.get("source_type")
    enabled = company.get("enabled", True)
    notes = company.get("notes")

    if not isinstance(employer_id, str) or not employer_id.strip():
        raise ConfigError(f"Company entry #{index} is missing company_key")

    if not isinstance(name, str) or not name.strip():
        raise ConfigError(f"Company {employer_id} is missing name")

    if not isinstance(source_type, str) or not source_type.strip():
        raise ConfigError(f"Company {employer_id} is missing source_type")

    if source_type not in SUPPORTED_SOURCE_TYPES:
        raise ConfigError(
            f"Unsupported source_type: {source_type} "
            f"for company {employer_id}"
        )

    if not isinstance(enabled, bool):
        raise ConfigError(
            f"Company {employer_id} enabled value must be true or false"
        )

    if notes is not None and not isinstance(notes, str):
        raise ConfigError(f"Company {employer_id} notes must be text")

    source_config = {
        key: value
        for key, value in company.items()
        if key not in _LEGACY_CORE_KEYS
    }

    return EmployerSource(
        employer_id=employer_id.strip(),
        name=name.strip(),
        source_type=source_type,
        enabled=enabled,
        source_config=source_config,
        notes=notes,
    )
