"""Manage global employer definitions behind the Administration boundary."""

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from job_radar.config import SUPPORTED_SOURCE_TYPES
from job_radar.database import connect_database
from job_radar.domain_errors import EmployerInUseError
from job_radar.employer_models import EmployerSource
from job_radar.employer_resolution_service import (
    normalize_careers_url,
    normalize_company_name,
)
from job_radar.employer_storage import (
    assign_employer_to_profile,
    delete_employer_source,
    get_employer_source,
    list_profile_employer_assignments,
    unassign_employer_from_profile,
)
from job_radar.profile_storage import get_profile, list_profiles
from job_radar.storage import initialize_database


NOT_CHECKED = "not_checked"
VALID = "valid"
INVALID = "invalid"


@dataclass(frozen=True)
class SourceField:
    """Describe one structured collector field shown to an administrator."""

    key: str
    label: str
    help_text: str
    required: bool = True


@dataclass(frozen=True)
class EmployerAdminRecord:
    """Present one employer with global state and safe operational metadata."""

    employer: EmployerSource
    retired: bool
    validation_state: str
    validation_issues: tuple[str, ...]
    last_validated_at: str | None
    creation_source: str
    created_at: str
    updated_at: str
    assigned_profile_count: int

    @property
    def configured(self) -> bool:
        return not validate_source_configuration(self.employer)

    @property
    def availability_label(self) -> str:
        if self.retired:
            return "Retired"
        return "Available" if self.employer.enabled else "Disabled"

    @property
    def configuration_label(self) -> str:
        return "Configured" if self.configured else "Needs setup"

    @property
    def validation_label(self) -> str:
        return {
            NOT_CHECKED: "Not checked",
            VALID: "Valid",
            INVALID: "Has issues",
        }.get(self.validation_state, "Not checked")


@dataclass(frozen=True)
class EmployerProfileAssignment:
    """Show whether one managed profile currently scans an employer."""

    profile_id: str
    profile_name: str
    assigned: bool
    scanning: bool


class EmployerAdminError(ValueError):
    """Explain an administrator action that cannot be completed safely."""


_SLUG_SOURCES = {"ashby", "greenhouse", "lever", "rippling"}
_URL_SOURCES = {
    "dayforce",
    "html",
    "icims",
    "jibe",
    "jobsyn",
    "oracle_hcm",
    "phenom",
    "recruitee",
    "selectminds",
    "smartrecruiters",
    "weka",
    "workday",
}


def source_fields(source_type: str) -> tuple[SourceField, ...]:
    """Return the supported structured fields for one collector."""

    if source_type in _SLUG_SOURCES:
        fields = (
            SourceField(
                "source_slug",
                "Career-site identifier",
                "The employer identifier used in the public career-site address.",
            ),
        )
    elif source_type == "eightfold":
        fields = (
            SourceField(
                "source_url",
                "Eightfold site URL",
                "The public base address hosting the Eightfold career site.",
            ),
            SourceField(
                "domain",
                "Eightfold employer domain",
                "The public employer domain used by Eightfold job search.",
            ),
        )
    elif source_type in _URL_SOURCES:
        fields = (
            SourceField(
                "source_url",
                "Job source URL",
                "The complete HTTPS address Junior uses to retrieve job listings.",
            ),
        )
    elif source_type == "activate":
        fields = (
            SourceField("source_url", "Job source URL", "The job-listing endpoint."),
            SourceField(
                "source_base_url",
                "Public job URL base",
                "The address used to build links to individual jobs.",
            ),
        )
    elif source_type == "adp":
        fields = (
            SourceField("source_url", "Job source URL", "The ADP job-search address."),
            SourceField(
                "cid",
                "ADP company identifier",
                "The cid value from the employer's ADP address.",
            ),
            SourceField(
                "ccId",
                "ADP career-center identifier",
                "The ccId value from the employer's ADP address.",
            ),
        )
    elif source_type == "schoolspring":
        fields = (
            SourceField(
                "domain_name",
                "SchoolSpring domain",
                "The employer's SchoolSpring domain name.",
            ),
        )
    elif source_type == "usajobs":
        fields = (
            SourceField(
                "organization",
                "USAJOBS organization code",
                "The federal organization code used to limit results.",
            ),
        )
    else:
        fields = ()

    return fields + (
        SourceField(
            "careers_url",
            "Public careers page",
            "Optional public page normal users may open.",
            required=False,
        ),
    )


def list_admin_employers(
    database_path: str | Path,
    *,
    search: str = "",
    source_type: str = "",
    configuration: str = "",
    availability: str = "",
    assignment: str = "",
    validation: str = "",
) -> tuple[EmployerAdminRecord, ...]:
    """List filtered employer records for the Administration catalog."""

    records = _load_records(database_path)
    normalized_search = search.strip().casefold()
    filtered = []
    for record in records:
        if normalized_search and normalized_search not in (
            f"{record.employer.name} "
            f"{record.employer.employer_id} "
            f"{record.employer.source_config.get('careers_url', '')}"
        ).casefold():
            continue
        if source_type and record.employer.source_type != source_type:
            continue
        if configuration == "configured" and not record.configured:
            continue
        if configuration == "incomplete" and record.configured:
            continue
        if availability and record.availability_label.casefold() != availability:
            continue
        if assignment == "assigned" and not record.assigned_profile_count:
            continue
        if assignment == "unassigned" and record.assigned_profile_count:
            continue
        if validation and record.validation_state != validation:
            continue
        filtered.append(record)
    return tuple(filtered)


def get_admin_employer(
    database_path: str | Path,
    employer_id: str,
) -> EmployerAdminRecord | None:
    """Load one complete employer administration record."""

    for record in _load_records(database_path):
        if record.employer.employer_id == employer_id:
            return record
    return None


def create_employer(
    database_path: str | Path,
    *,
    name: str,
    source_type: str,
    source_config: dict[str, str],
    notes: str,
) -> EmployerAdminRecord:
    """Create one disabled employer pending explicit validation and enablement."""

    normalized_name = name.strip()
    if not normalized_name:
        raise EmployerAdminError("Enter an employer name.")
    if source_type not in SUPPORTED_SOURCE_TYPES:
        raise EmployerAdminError("Choose a supported job source.")

    employer_id = _unique_employer_id(database_path, normalized_name)
    employer = EmployerSource(
        employer_id=employer_id,
        name=normalized_name,
        source_type=source_type,
        enabled=False,
        source_config=_normalize_source_config(source_type, source_config),
        notes=notes.strip() or None,
    )
    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.execute(
            """
            INSERT INTO employer_sources (
                employer_id, name, source_type, enabled, source_config_json,
                notes, creation_source, normalized_name,
                normalized_careers_url, source_identifier
            ) VALUES (?, ?, ?, 0, ?, ?, 'administration', ?, ?, ?)
            """,
            (
                employer.employer_id,
                employer.name,
                employer.source_type,
                _dump_config(employer.source_config),
                employer.notes,
                normalize_company_name(employer.name),
                _normalized_careers_url(employer.source_config),
                _source_identifier(employer),
            ),
        )
        _record_audit(connection, employer_id, "create", {}, employer, False)
    return get_admin_employer(db_path, employer_id)  # type: ignore[return-value]


def update_employer(
    database_path: str | Path,
    employer_id: str,
    *,
    name: str,
    source_type: str,
    source_config: dict[str, str],
    notes: str,
) -> EmployerAdminRecord:
    """Update structured source settings and require revalidation."""

    previous = get_admin_employer(database_path, employer_id)
    if previous is None:
        raise EmployerAdminError("That employer no longer exists.")
    if not name.strip():
        raise EmployerAdminError("Enter an employer name.")
    if source_type not in SUPPORTED_SOURCE_TYPES:
        raise EmployerAdminError("Choose a supported job source.")

    employer = EmployerSource(
        employer_id=employer_id,
        name=name.strip(),
        source_type=source_type,
        enabled=previous.employer.enabled,
        source_config=_normalize_source_config(source_type, source_config),
        notes=notes.strip() or None,
    )
    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.execute(
            """
            UPDATE employer_sources
            SET name = ?, source_type = ?, source_config_json = ?, notes = ?,
                validation_state = ?, validation_issues_json = '[]',
                last_validated_at = NULL, normalized_name = ?,
                normalized_careers_url = ?, source_identifier = ?,
                last_connection_test_at = NULL,
                last_connection_success_at = NULL,
                last_connection_error_at = NULL,
                last_connection_state = 'not_tested',
                last_connection_category = NULL,
                last_connection_message = NULL,
                last_connection_job_count = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE employer_id = ?
            """,
            (
                employer.name,
                employer.source_type,
                _dump_config(employer.source_config),
                employer.notes,
                NOT_CHECKED,
                normalize_company_name(employer.name),
                _normalized_careers_url(employer.source_config),
                _source_identifier(employer),
                employer_id,
            ),
        )
        _record_audit(
            connection, employer_id, "edit", previous, employer, previous.retired
        )
    return get_admin_employer(db_path, employer_id)  # type: ignore[return-value]


def rename_employer(
    database_path: str | Path,
    employer_id: str,
    *,
    name: str,
) -> EmployerAdminRecord:
    """Correct a shared display name without disturbing its working collector."""

    previous = get_admin_employer(database_path, employer_id)
    if previous is None:
        raise EmployerAdminError("That employer no longer exists.")
    normalized_name = " ".join(name.strip().split())
    if not normalized_name:
        raise EmployerAdminError("Enter the corrected company name.")
    employer = EmployerSource(
        employer_id=previous.employer.employer_id,
        name=normalized_name,
        source_type=previous.employer.source_type,
        enabled=previous.employer.enabled,
        source_config=previous.employer.source_config,
        notes=previous.employer.notes,
    )
    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.execute(
            """
            UPDATE employer_sources
            SET name = ?, normalized_name = ?, updated_at = CURRENT_TIMESTAMP
            WHERE employer_id = ?
            """,
            (
                employer.name,
                normalize_company_name(employer.name),
                employer_id,
            ),
        )
        _record_audit(
            connection,
            employer_id,
            "rename",
            previous,
            employer,
            previous.retired,
        )
    return get_admin_employer(db_path, employer_id)  # type: ignore[return-value]


def validate_employer(
    database_path: str | Path,
    employer_id: str,
) -> EmployerAdminRecord:
    """Run bounded local validation without scanning or contacting a website."""

    record = get_admin_employer(database_path, employer_id)
    if record is None:
        raise EmployerAdminError("That employer no longer exists.")
    issues = validate_source_configuration(record.employer)
    state = INVALID if issues else VALID
    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.execute(
            """
            UPDATE employer_sources
            SET validation_state = ?, validation_issues_json = ?,
                last_validated_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE employer_id = ?
            """,
            (state, json.dumps(issues), employer_id),
        )
        _record_audit(
            connection,
            employer_id,
            "validate",
            record,
            record.employer,
            record.retired,
            validation_state=state,
        )
    return get_admin_employer(db_path, employer_id)  # type: ignore[return-value]


def set_employer_lifecycle(
    database_path: str | Path,
    employer_id: str,
    operation: str,
) -> EmployerAdminRecord:
    """Enable, disable, or retire globally while preserving assignments."""

    record = get_admin_employer(database_path, employer_id)
    if record is None:
        raise EmployerAdminError("That employer no longer exists.")
    if operation == "enable":
        if record.retired:
            raise EmployerAdminError("A retired employer cannot be enabled.")
        if record.validation_state != VALID:
            raise EmployerAdminError("Validate this employer before enabling it.")
        enabled, retired = True, False
    elif operation == "disable":
        enabled, retired = False, record.retired
    elif operation == "retire":
        enabled, retired = False, True
    else:
        raise EmployerAdminError("Unsupported employer operation.")

    updated = EmployerSource(
        employer_id=record.employer.employer_id,
        name=record.employer.name,
        source_type=record.employer.source_type,
        enabled=enabled,
        source_config=record.employer.source_config,
        notes=record.employer.notes,
    )
    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.execute(
            """
            UPDATE employer_sources
            SET enabled = ?, retired = ?, updated_at = CURRENT_TIMESTAMP
            WHERE employer_id = ?
            """,
            (int(enabled), int(retired), employer_id),
        )
        _record_audit(
            connection, employer_id, operation, record, updated, retired
        )
    return get_admin_employer(db_path, employer_id)  # type: ignore[return-value]


def list_employer_profile_assignments(
    database_path: str | Path,
    employer_id: str,
) -> tuple[EmployerProfileAssignment, ...]:
    """List every active profile and its assignment to one employer."""

    if get_admin_employer(database_path, employer_id) is None:
        raise EmployerAdminError("That employer no longer exists.")
    records = []
    for profile in list_profiles(database_path):
        assignment = next(
            (
                item
                for item in list_profile_employer_assignments(
                    database_path, profile.profile_id
                )
                if item.employer_id == employer_id
            ),
            None,
        )
        records.append(
            EmployerProfileAssignment(
                profile_id=profile.profile_id,
                profile_name=profile.display_name,
                assigned=assignment is not None,
                scanning=bool(assignment and assignment.enabled),
            )
        )
    return tuple(records)


def set_employer_profile_assignment(
    database_path: str | Path,
    employer_id: str,
    profile_id: str,
    *,
    assigned: bool,
) -> bool:
    """Assign or remove one employer without changing another profile."""

    record = get_admin_employer(database_path, employer_id)
    if record is None:
        raise EmployerAdminError("That employer no longer exists.")
    profile = get_profile(database_path, profile_id)
    if profile is None or profile.archived:
        raise EmployerAdminError("That profile is no longer available.")
    if assigned:
        if (
            record.retired
            or not record.employer.enabled
            or record.validation_state != VALID
        ):
            raise EmployerAdminError(
                "Validate and enable this employer before assigning it."
            )
        return assign_employer_to_profile(
            database_path, profile_id, employer_id
        )
    return unassign_employer_from_profile(
        database_path, profile_id, employer_id
    )


def permanently_delete_employer(
    database_path: str | Path,
    employer_id: str,
    *,
    confirmation: str,
) -> bool:
    """Delete only an unused employer after explicit typed confirmation."""

    if get_admin_employer(database_path, employer_id) is None:
        raise EmployerAdminError("That employer no longer exists.")
    if confirmation != "DELETE":
        raise EmployerAdminError("Type DELETE to confirm permanent deletion.")
    try:
        deleted = delete_employer_source(database_path, employer_id)
    except EmployerInUseError as error:
        raise EmployerAdminError(
            "This employer cannot be deleted because a profile or collected "
            "job still uses it. Disable or retire it instead."
        ) from error
    if not deleted:
        raise EmployerAdminError("That employer no longer exists.")
    return True


def validate_source_configuration(employer: EmployerSource) -> tuple[str, ...]:
    """Return plain-language issues for the collector's required fields."""

    issues = []
    config = employer.source_config
    for field in source_fields(employer.source_type):
        value = config.get(field.key)
        if field.required and not _has_text(value):
            issues.append(f"{field.label} is required.")
        elif _has_text(value) and field.key.endswith("url") and not _http_url(value):
            issues.append(f"{field.label} must be a complete HTTP or HTTPS address.")
    if employer.source_type == "adp" and _http_url(config.get("source_url")):
        query = parse_qs(urlparse(str(config["source_url"])).query)
        if not _has_text(config.get("cid")) and query.get("cid"):
            issues = [issue for issue in issues if not issue.startswith("ADP company")]
        if not _has_text(config.get("ccId")) and query.get("ccId"):
            issues = [
                issue
                for issue in issues
                if not issue.startswith("ADP career-center")
            ]
    return tuple(issues)


def list_employer_audit(
    database_path: str | Path,
    employer_id: str,
) -> tuple[dict[str, str], ...]:
    """Return recent sanitized operations without collector settings."""

    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT operation, change_source, created_at
            FROM employer_catalog_audit
            WHERE employer_id = ?
            ORDER BY audit_id DESC
            LIMIT 20
            """,
            (employer_id,),
        ).fetchall()
    return tuple(dict(row) for row in rows)


def _load_records(database_path: str | Path) -> list[EmployerAdminRecord]:
    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT employer.*, COUNT(association.profile_id) AS assigned_count
            FROM employer_sources AS employer
            LEFT JOIN profile_company_associations AS association
              ON association.company_id = employer.employer_id
            GROUP BY employer.employer_id
            ORDER BY employer.name COLLATE NOCASE, employer.employer_id
            """
        ).fetchall()
    records = []
    for row in rows:
        employer = get_employer_source(db_path, row["employer_id"])
        if employer is None:
            continue
        try:
            issues = json.loads(row["validation_issues_json"])
        except (TypeError, json.JSONDecodeError):
            issues = []
        records.append(
            EmployerAdminRecord(
                employer=employer,
                retired=bool(row["retired"]),
                validation_state=row["validation_state"],
                validation_issues=tuple(
                    str(issue) for issue in issues if isinstance(issue, str)
                ),
                last_validated_at=row["last_validated_at"],
                creation_source=row["creation_source"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                assigned_profile_count=int(row["assigned_count"]),
            )
        )
    return records


def _unique_employer_id(database_path: str | Path, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "employer"
    candidate = base
    suffix = 2
    while get_employer_source(database_path, candidate) is not None:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _normalize_source_config(
    source_type: str,
    submitted: dict[str, str],
) -> dict[str, object]:
    config: dict[str, object] = {}
    for field in source_fields(source_type):
        value = submitted.get(field.key, "").strip()
        if value:
            config[field.key] = value
    if source_type == "usajobs" and "organization" in config:
        config["query_params"] = {"Organization": config.pop("organization")}
    return config


def form_source_config(employer: EmployerSource) -> dict[str, str]:
    """Convert stored configuration to the structured edit fields."""

    values = {
        field.key: str(employer.source_config.get(field.key, ""))
        for field in source_fields(employer.source_type)
    }
    if employer.source_type == "usajobs":
        query = employer.source_config.get("query_params")
        if isinstance(query, dict):
            values["organization"] = str(query.get("Organization", ""))
    return values


def _record_audit(
    connection: sqlite3.Connection,
    employer_id: str,
    operation: str,
    previous: object,
    employer: EmployerSource,
    retired: bool,
    *,
    validation_state: str = NOT_CHECKED,
) -> None:
    # Audit only lifecycle labels; collector configuration and notes can contain
    # private operational context and must never be copied into diagnostics.
    previous_state = _safe_state(previous)
    new_state = {
        "name": employer.name,
        "source_type": employer.source_type,
        "enabled": employer.enabled,
        "retired": retired,
        "validation_state": validation_state,
    }
    connection.execute(
        """
        INSERT INTO employer_catalog_audit (
            employer_id, operation, previous_state_json,
            new_state_json, change_source
        ) VALUES (?, ?, ?, ?, 'administration')
        """,
        (
            employer_id,
            operation,
            json.dumps(previous_state, sort_keys=True),
            json.dumps(new_state, sort_keys=True),
        ),
    )


def _safe_state(value: object) -> dict[str, object]:
    if not isinstance(value, EmployerAdminRecord):
        return {}
    return {
        "name": value.employer.name,
        "source_type": value.employer.source_type,
        "enabled": value.employer.enabled,
        "retired": value.retired,
        "validation_state": value.validation_state,
    }


def _dump_config(config: dict[str, object]) -> str:
    return json.dumps(config, separators=(",", ":"), sort_keys=True)


def _has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _http_url(value: object) -> bool:
    if not _has_text(value):
        return False
    parsed = urlparse(str(value).strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _normalized_careers_url(config: dict[str, object]) -> str | None:
    value = config.get("careers_url")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return normalize_careers_url(value)
    except ValueError:
        return None


def _source_identifier(employer: EmployerSource) -> str | None:
    for key in ("source_slug", "domain_name", "cid"):
        value = employer.source_config.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().casefold()
    return None
