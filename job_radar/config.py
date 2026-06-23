from pathlib import Path
from typing import Any

import yaml


SUPPORTED_SOURCE_TYPES = {
    "greenhouse",
    "lever",
    "workday",
    "ashby",
    "html",
}


class ConfigError(Exception):
    """Raised when Job Radar configuration is missing or invalid."""


def load_yaml_file(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)

    if not config_path.exists():
        raise ConfigError(f"Config file does not exist: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if data is None:
        return {}

    if not isinstance(data, dict):
        raise ConfigError(f"Config file must contain a YAML mapping: {config_path}")

    return data


def load_companies(path: str | Path) -> list[dict[str, Any]]:
    data = load_yaml_file(path)

    companies = data.get("companies")
    if companies is None:
        raise ConfigError("companies.yaml must contain a top-level 'companies' list")

    if not isinstance(companies, list):
        raise ConfigError("'companies' must be a list")

    enabled_companies: list[dict[str, Any]] = []

    for index, company in enumerate(companies, start=1):
        if not isinstance(company, dict):
            raise ConfigError(f"Company entry #{index} must be a mapping")

        company_key = company.get("company_key")
        name = company.get("name")
        source_type = company.get("source_type")
        enabled = company.get("enabled", True)

        if not company_key:
            raise ConfigError(f"Company entry #{index} is missing company_key")

        if not name:
            raise ConfigError(f"Company {company_key} is missing name")

        if not source_type:
            raise ConfigError(f"Company {company_key} is missing source_type")

        if source_type not in SUPPORTED_SOURCE_TYPES:
            raise ConfigError(
                f"Unsupported source_type: {source_type} for company {company_key}"
            )

        if not isinstance(enabled, bool):
            raise ConfigError(f"Company {company_key} enabled value must be true or false")

        if enabled:
            enabled_companies.append(company)

    return enabled_companies


def load_settings(path: str | Path = "config/settings.yaml") -> dict[str, Any]:
    data = load_yaml_file(path)

    required_keys = [
        "database_path",
        "reports_path",
        "logs_path",
        "retention",
    ]

    for key in required_keys:
        if key not in data:
            raise ConfigError(f"settings.yaml is missing required key: {key}")

    if not isinstance(data["retention"], dict):
        raise ConfigError("settings.yaml retention section must be a mapping")

    return data