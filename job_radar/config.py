"""Load and validate Junior's YAML configuration into typed settings.

This module rejects malformed company, path, profile, and email configuration
before application work begins. Its mapping-compatible settings objects preserve
released callers while newer code uses explicit, easier-to-understand fields.
"""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from job_radar.collector_catalog import COLLECTOR_CAPABILITIES


SUPPORTED_SOURCE_TYPES = {
    capability.source_type for capability in COLLECTOR_CAPABILITIES
}


class ConfigError(Exception):
    """Raised when Junior configuration is missing or invalid."""


@dataclass(frozen=True)
class EmailSettings(Mapping[str, Any]):
    """Validated email configuration without containing the secret itself."""

    enabled: bool
    sender: str
    sender_name: str
    recipients: tuple[str, ...]
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password_env: str
    smtp_credential_key: str
    smtp_provider: str
    smtp_tls_mode: str
    _data: dict[str, Any] = field(repr=False, compare=False)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)


@dataclass(frozen=True)
class ActiveProfileSettings:
    """Application-owned selection of the profile used for the current run.

    The selected profile path belongs to application configuration. Candidate
    identity, resume, preferences, strengths, gaps, and exclusions remain owned
    by the profile file itself.
    """

    candidate_profile_path: str | None


@dataclass(frozen=True)
class RetentionPolicySettings:
    """Describe how many current and prior Junior-owned outputs to keep."""

    mode: str
    count: int

    @property
    def total_to_keep(self) -> int:
        if self.mode == "latest_only":
            return 1
        if self.mode == "latest_plus_previous":
            return 2
        return self.count


@dataclass(frozen=True)
class RetentionSettings:
    reports: RetentionPolicySettings
    logs: RetentionPolicySettings


@dataclass(frozen=True)
class LlmSettings:
    """Optional external advisory settings without containing an API key."""

    enabled: bool
    provider: str
    model: str
    credential_key: str
    privacy_acknowledged: bool
    max_reviews_per_scan: int


@dataclass(frozen=True)
class ApplicationSettings(Mapping[str, Any]):
    """Application-owned settings loaded from the current settings YAML file.

    Mapping behavior is retained temporarily so released callers continue to
    work while they are migrated to explicit attributes in controlled steps.
    Unknown YAML keys are also preserved so upgrades do not silently discard
    settings introduced by older or newer versions.
    """

    database_path: str
    reports_path: str
    logs_path: str
    active_profile: ActiveProfileSettings
    email: EmailSettings
    retention: RetentionSettings
    llm: LlmSettings
    _data: dict[str, Any] = field(repr=False, compare=False)

    @property
    def candidate_profile_path(self) -> str | None:
        """Compatibility access for the released flat settings interface."""

        return self.active_profile.candidate_profile_path

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)


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
        raise ConfigError("company config must contain a top-level 'companies' list")

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


def load_settings(
    path: str | Path = "config/settings.yaml",
) -> ApplicationSettings:
    data = load_yaml_file(path)

    required_keys = (
        "database_path",
        "reports_path",
        "logs_path",
    )

    for key in required_keys:
        if key not in data:
            raise ConfigError(f"settings.yaml is missing required key: {key}")

    database_path = _required_settings_string(data["database_path"], "database_path")
    reports_path = _required_settings_string(data["reports_path"], "reports_path")
    logs_path = _required_settings_string(data["logs_path"], "logs_path")

    candidate_profile_path = _optional_settings_string(
        data.get("candidate_profile_path"),
        "candidate_profile_path",
    )
    active_profile = ActiveProfileSettings(
        candidate_profile_path=candidate_profile_path,
    )
    email = _validate_email_settings(data.get("email", {}))
    retention = _validate_retention_settings(data.get("retention", {}))
    llm = _validate_llm_settings(data.get("llm", {}))

    # Preserve the original mapping shape during the compatibility migration.
    # Existing CLI and GUI callers can keep using [] and .get() until each
    # boundary is deliberately converted to typed attribute access.
    normalized_data = dict(data)
    normalized_data["database_path"] = database_path
    normalized_data["reports_path"] = reports_path
    normalized_data["logs_path"] = logs_path
    normalized_data["email"] = email

    if "candidate_profile_path" in data:
        normalized_data["candidate_profile_path"] = candidate_profile_path

    return ApplicationSettings(
        database_path=database_path,
        reports_path=reports_path,
        logs_path=logs_path,
        active_profile=active_profile,
        email=email,
        retention=retention,
        llm=llm,
        _data=normalized_data,
    )


def _validate_llm_settings(raw_llm: Any) -> LlmSettings:
    if raw_llm is None:
        raw_llm = {}
    if not isinstance(raw_llm, dict):
        raise ConfigError("settings.yaml llm section must be a mapping")
    enabled = raw_llm.get("enabled", False)
    provider = raw_llm.get("provider", "openai")
    model = raw_llm.get("model", "gpt-5.6-sol")
    credential_key = raw_llm.get("credential_key", "")
    acknowledged = raw_llm.get("privacy_acknowledged", False)
    max_reviews = raw_llm.get("max_reviews_per_scan", 25)
    if not isinstance(enabled, bool):
        raise ConfigError("settings.yaml llm.enabled must be true or false")
    if provider != "openai":
        raise ConfigError("settings.yaml llm.provider must currently be openai")
    if not isinstance(model, str) or not model.strip():
        raise ConfigError("settings.yaml llm.model must be a non-empty string")
    if not isinstance(credential_key, str):
        raise ConfigError("settings.yaml llm.credential_key must be a string")
    if not isinstance(acknowledged, bool):
        raise ConfigError(
            "settings.yaml llm.privacy_acknowledged must be true or false"
        )
    if isinstance(max_reviews, bool) or not isinstance(max_reviews, int):
        raise ConfigError("settings.yaml llm.max_reviews_per_scan must be a number")
    if not 1 <= max_reviews <= 100:
        raise ConfigError(
            "settings.yaml llm.max_reviews_per_scan must be between 1 and 100"
        )
    if enabled and (not acknowledged or not credential_key.strip()):
        raise ConfigError(
            "settings.yaml llm requires privacy acknowledgement and a secure "
            "credential reference when enabled"
        )
    return LlmSettings(
        enabled=enabled,
        provider=provider,
        model=model.strip(),
        credential_key=credential_key.strip(),
        privacy_acknowledged=acknowledged,
        max_reviews_per_scan=max_reviews,
    )


def _validate_retention_settings(raw_retention: Any) -> RetentionSettings:
    if raw_retention is None:
        raw_retention = {}
    if not isinstance(raw_retention, dict):
        raise ConfigError("settings.yaml retention section must be a mapping")

    return RetentionSettings(
        reports=_validate_retention_policy(
            raw_retention.get("report_policy", "latest_only"),
            raw_retention.get("report_count", 1),
            label="report",
        ),
        logs=_validate_retention_policy(
            raw_retention.get("log_policy", "latest_only"),
            raw_retention.get("log_count", 1),
            label="log",
        ),
    )


def _validate_retention_policy(
    raw_mode: Any,
    raw_count: Any,
    *,
    label: str,
) -> RetentionPolicySettings:
    modes = {"latest_only", "latest_plus_previous", "keep_last_n"}
    if not isinstance(raw_mode, str) or raw_mode not in modes:
        raise ConfigError(
            f"settings.yaml {label}_policy must be a supported retention policy"
        )
    if isinstance(raw_count, bool) or not isinstance(raw_count, int):
        raise ConfigError(f"settings.yaml {label}_count must be a number")
    if not 1 <= raw_count <= 50:
        raise ConfigError(
            f"settings.yaml {label}_count must be between 1 and 50"
        )
    return RetentionPolicySettings(mode=raw_mode, count=raw_count)


def _required_settings_string(raw_value: Any, key: str) -> str:
    value = _optional_settings_string(raw_value, key)

    if value is None:
        raise ConfigError(f"settings.yaml {key} is required")

    return value


def _optional_settings_string(raw_value: Any, key: str) -> str | None:
    if raw_value is None:
        return None

    if not isinstance(raw_value, str):
        raise ConfigError(f"settings.yaml {key} must be a string")

    value = raw_value.strip()

    if not value:
        raise ConfigError(f"settings.yaml {key} cannot be empty")

    return value


def _validate_email_settings(raw_email_settings: Any) -> EmailSettings:
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
    smtp_credential_key = raw_email_settings.get("smtp_credential_key", "")
    smtp_provider = raw_email_settings.get(
        "smtp_provider",
        _infer_smtp_provider(smtp_host),
    )
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

    if not isinstance(smtp_credential_key, str):
        raise ConfigError("settings.yaml email.smtp_credential_key must be a string")

    if smtp_provider not in {"gmail", "outlook", "custom"}:
        raise ConfigError(
            "settings.yaml email.smtp_provider must be gmail, outlook, or custom"
        )
    
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
            smtp_credential_key=smtp_credential_key,
        )

    normalized_data = {
        "enabled": enabled,
        "sender": sender,
        "sender_name": sender_name,
        "recipients": recipients,
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "smtp_username": smtp_username,
        "smtp_password_env": smtp_password_env,
        "smtp_credential_key": smtp_credential_key,
        "smtp_provider": smtp_provider,
        "smtp_tls_mode": smtp_tls_mode,
    }

    return EmailSettings(
        enabled=enabled,
        sender=sender,
        sender_name=sender_name,
        recipients=tuple(recipients),
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_username=smtp_username,
        smtp_password_env=smtp_password_env,
        smtp_credential_key=smtp_credential_key,
        smtp_provider=smtp_provider,
        smtp_tls_mode=smtp_tls_mode,
        _data=normalized_data,
    )

def _validate_enabled_email_settings(
    sender: str,
    recipients: list[str],
    smtp_host: str,
    smtp_username: str,
    smtp_password_env: str,
    smtp_credential_key: str,
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

    if not smtp_password_env and not smtp_credential_key:
        raise ConfigError(
            "settings.yaml email requires smtp_password_env or "
            "smtp_credential_key when email is enabled"
        )


def _infer_smtp_provider(host: str) -> str:
    return {
        "smtp.gmail.com": "gmail",
        "smtp-mail.outlook.com": "outlook",
    }.get(host.strip().lower(), "custom")
