"""Move public company collector definitions without replacing local records."""

from dataclasses import dataclass
import json
from pathlib import Path

from job_radar.config import ConfigError, SUPPORTED_SOURCE_TYPES
from job_radar.employer_admin_service import (
    form_source_config,
    source_fields,
    validate_source_configuration,
)
from job_radar.employer_models import EmployerSource
from job_radar.employer_resolution_service import normalize_company_name
from job_radar.employer_storage import append_employer_sources, list_employer_sources


TRANSFER_FORMAT = "junior-company-catalog"
TRANSFER_SCHEMA_VERSION = 1
MAX_TRANSFER_BYTES = 2_000_000
MAX_COMPANIES = 2_000
MAX_TEXT_LENGTH = 2_048


@dataclass(frozen=True)
class CompanyImportResult:
    """Summarize additions while proving existing catalog entries were untouched."""

    added: int
    skipped_duplicates: int


def export_company_catalog(database_path: str | Path) -> tuple[str, bytes]:
    """Export public collector settings, excluding notes and operational history."""

    companies = []
    for employer in list_employer_sources(database_path):
        companies.append(
            {
                "employer_id": employer.employer_id,
                "name": employer.name,
                "source_type": employer.source_type,
                "enabled": employer.enabled,
                "public_source_config": form_source_config(employer),
            }
        )
    payload = {
        "format": TRANSFER_FORMAT,
        "transfer_schema_version": TRANSFER_SCHEMA_VERSION,
        "companies": companies,
        "excluded": [
            "profile assignments and scanning selections",
            "company notes, health history, jobs, scans, and diagnostics",
            "credentials, request data, and private operational metadata",
        ],
    }
    return (
        "junior-company-catalog.json",
        json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"),
    )


def import_company_catalog(
    database_path: str | Path,
    content: bytes,
) -> CompanyImportResult:
    """Append missing companies and never modify existing catalog definitions."""

    if not content:
        raise ConfigError("The selected company file is empty.")
    if len(content) > MAX_TRANSFER_BYTES:
        raise ConfigError("The company file is larger than Junior supports.")
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ConfigError("The selected file is not a valid Junior company file.") from error
    if not isinstance(payload, dict) or set(payload) != {
        "format",
        "transfer_schema_version",
        "companies",
        "excluded",
    }:
        raise ConfigError("The company file has missing or unsupported fields.")
    if payload["format"] != TRANSFER_FORMAT:
        raise ConfigError("The selected file is not a Junior company catalog.")
    if payload["transfer_schema_version"] != TRANSFER_SCHEMA_VERSION:
        raise ConfigError("This company file uses an unsupported transfer version.")
    raw_companies = payload["companies"]
    if not isinstance(raw_companies, list) or len(raw_companies) > MAX_COMPANIES:
        raise ConfigError("The imported company list is invalid or too large.")

    existing = list_employer_sources(database_path)
    existing_ids = {employer.employer_id.casefold() for employer in existing}
    existing_names = {normalize_company_name(employer.name) for employer in existing}
    pending_ids: set[str] = set()
    pending_names: set[str] = set()
    additions: list[EmployerSource] = []
    skipped = 0
    for raw in raw_companies:
        employer = _employer_from_payload(raw)
        employer_id = employer.employer_id.casefold()
        name = normalize_company_name(employer.name)
        if (
            employer_id in existing_ids
            or name in existing_names
            or employer_id in pending_ids
            or name in pending_names
        ):
            skipped += 1
            continue
        additions.append(employer)
        pending_ids.add(employer_id)
        pending_names.add(name)

    # The storage boundary uses INSERT-only behavior as a second no-overwrite guard.
    added = append_employer_sources(database_path, additions)
    return CompanyImportResult(
        added=added,
        skipped_duplicates=skipped + len(additions) - added,
    )


def _employer_from_payload(value: object) -> EmployerSource:
    if not isinstance(value, dict) or set(value) != {
        "employer_id",
        "name",
        "source_type",
        "enabled",
        "public_source_config",
    }:
        raise ConfigError("An imported company has missing or unsupported fields.")
    employer_id = _text(value["employer_id"], "company ID")
    name = _text(value["name"], "company name")
    source_type = _text(value["source_type"], "collector type")
    if source_type not in SUPPORTED_SOURCE_TYPES:
        raise ConfigError("An imported company uses an unsupported collector type.")
    if not isinstance(value["enabled"], bool):
        raise ConfigError("An imported company has an invalid availability state.")
    raw_config = value["public_source_config"]
    if not isinstance(raw_config, dict) or not all(
        isinstance(key, str) and isinstance(item, str)
        for key, item in raw_config.items()
    ):
        raise ConfigError("An imported company has invalid public source settings.")
    allowed = {field.key for field in source_fields(source_type)}
    if not set(raw_config).issubset(allowed):
        raise ConfigError("An imported company contains unsupported source settings.")
    public_config: dict[str, object] = {
        key: _text(item, f"company {key}")
        for key, item in raw_config.items()
        if item.strip()
    }
    validation_employer = EmployerSource(
        employer_id=employer_id,
        name=name,
        source_type=source_type,
        enabled=value["enabled"],
        source_config=public_config,
        notes=None,
    )
    issues = validate_source_configuration(validation_employer)
    if issues:
        raise ConfigError(
            f"{name} cannot be imported because its public collector settings are incomplete."
        )
    stored_config = dict(public_config)
    if source_type == "usajobs" and "organization" in stored_config:
        stored_config["query_params"] = {
            "Organization": stored_config.pop("organization")
        }
    return EmployerSource(
        employer_id=employer_id,
        name=name,
        source_type=source_type,
        enabled=value["enabled"],
        source_config=stored_config,
        notes=None,
    )


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT_LENGTH:
        raise ConfigError(f"The imported {label} is invalid.")
    return value.strip()
