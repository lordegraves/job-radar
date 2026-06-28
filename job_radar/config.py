import os
from pathlib import Path
from typing import Any

import yaml


SUPPORTED_SOURCE_TYPES = {
    "greenhouse",
    "lever",
    "workday",
    "ashby",
    "usajobs",
    "icims",
    "jibe",
    "jobsyn",
    "oracle_hcm",
    "dayforce",
    "adp",
    "smartrecruiters",
    "selectminds",
    "phenom",
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

    email_settings = data.get("email", {})
    data["email"] = _validate_email_settings(email_settings)

    return data


def _validate_email_settings(raw_email_settings: Any) -> dict[str, Any]:
    if raw_email_settings is None:
        raw_email_settings = {}

    if not isinstance(raw_email_settings, dict):
        raise ConfigError("settings.yaml email section must be a mapping")

    enabled = raw_email_settings.get("enabled", False)
    sender = raw_email_settings.get("sender", "")
    sender_name = raw_email_settings.get("sender_name", "")
    recipients = raw_email_settings.get("recipients", [])
    smtp_host = raw_email_settings.get("smtp_host", "")
    smtp_port = raw_email_settings.get("smtp_port", 587)
    smtp_username = raw_email_settings.get("smtp_username", "")
    smtp_password_env = raw_email_settings.get("smtp_password_env", "")
    smtp_tls_mode = raw_email_settings.get("smtp_tls_mode", "starttls")

    if not isinstance(enabled, bool):
        raise ConfigError("settings.yaml email.enabled must be true or false")

    if not isinstance(sender, str):
        raise ConfigError("settings.yaml email.sender must be a string")

    if not isinstance(sender_name, str):
        raise ConfigError("settings.yaml email.sender_name must be a string")

    if not isinstance(recipients, list):
        raise ConfigError("settings.yaml email.recipients must be a list")

    for index, recipient in enumerate(recipients, start=1):
        if not isinstance(recipient, str):
            raise ConfigError(
                f"settings.yaml email.recipients entry #{index} must be a string"
            )

    if not isinstance(smtp_host, str):
        raise ConfigError("settings.yaml email.smtp_host must be a string")

    if not isinstance(smtp_port, int) or isinstance(smtp_port, bool):
        raise ConfigError("settings.yaml email.smtp_port must be an integer")
    
    if not isinstance(smtp_username, str):
        raise ConfigError("settings.yaml email.smtp_username must be a string")
    
    if not isinstance(smtp_password_env, str):
        raise ConfigError("settings.yaml email.smtp_password_env must be a string")
    
    if not isinstance(smtp_tls_mode, str):
        raise ConfigError("settings.yaml email.smtp_tls_mode must be a string")

    if smtp_tls_mode not in {"starttls", "ssl", "none"}:
        raise ConfigError(
            "settings.yaml email.smtp_tls_mode must be one of: starttls, ssl, none"
        )

    if enabled:
        _validate_enabled_email_settings(
            sender=sender,
            recipients=recipients,
            smtp_host=smtp_host,
            smtp_username=smtp_username,
            smtp_password_env=smtp_password_env,
        )

    return {
        "enabled": enabled,
        "sender": sender,
        "sender_name": sender_name,
        "recipients": recipients,
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "smtp_username": smtp_username,
        "smtp_password_env": smtp_password_env,
        "smtp_tls_mode": smtp_tls_mode,
    }

def _validate_enabled_email_settings(
    sender: str,
    recipients: list[str],
    smtp_host: str,
    smtp_username: str,
    smtp_password_env: str,
) -> None:
    if not sender:
        raise ConfigError("settings.yaml email.sender is required when email is enabled")

    if not recipients:
        raise ConfigError(
            "settings.yaml email.recipients is required when email is enabled"
        )

    if not smtp_host:
        raise ConfigError("settings.yaml email.smtp_host is required when email is enabled")
    
    if not smtp_username:
        raise ConfigError(
            "settings.yaml email.smtp_username is required when email is enabled"
        )

    if not smtp_password_env:
        raise ConfigError(
            "settings.yaml email.smtp_password_env is required when email is enabled"
        )

    if smtp_password_env not in os.environ:
        raise ConfigError(
            f"Email password environment variable is not set: {smtp_password_env}"
        )