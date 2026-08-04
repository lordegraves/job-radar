"""Manage disabled-by-default LLM consent and secure credentials."""

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Any

import yaml

from job_radar.config import ConfigError, load_settings, load_yaml_file
from job_radar.credential_store import (
    CredentialStoreError,
    get_credential,
    store_credential,
)


class LlmSettingsError(ValueError):
    """Explain an LLM setting problem without exposing a credential."""


@dataclass(frozen=True)
class LlmSettingsForm:
    enabled: bool
    provider: str
    model: str
    privacy_acknowledged: bool
    max_reviews_per_scan: int
    credential_saved: bool


def load_llm_settings_form(settings_path: str | Path) -> LlmSettingsForm:
    settings = load_settings(settings_path).llm
    saved = False
    if settings.credential_key:
        try:
            saved = bool(get_credential(settings.credential_key))
        except CredentialStoreError:
            saved = False
    return LlmSettingsForm(
        enabled=settings.enabled,
        provider=settings.provider,
        model=settings.model,
        privacy_acknowledged=settings.privacy_acknowledged,
        max_reviews_per_scan=settings.max_reviews_per_scan,
        credential_saved=saved,
    )


def save_llm_settings(
    settings_path: str | Path,
    *,
    enabled: bool,
    provider: str,
    model: str,
    privacy_acknowledged: bool,
    max_reviews_per_scan: int,
    credential: str,
) -> LlmSettingsForm:
    """Atomically save consent/settings and store a new key only in keyring."""

    if provider != "openai":
        raise LlmSettingsError("OpenAI is the only supported provider right now.")
    model = model.strip()
    if not model:
        raise LlmSettingsError("Choose an OpenAI model.")
    if not 1 <= max_reviews_per_scan <= 100:
        raise LlmSettingsError("Reviews per scan must be between 1 and 100.")
    path = Path(settings_path)
    data = load_yaml_file(path)
    existing = load_settings(path).llm
    credential_key = existing.credential_key
    previous_credential = None
    if credential:
        credential_key = "llm:openai:api-key"
        try:
            previous_credential = get_credential(credential_key)
        except CredentialStoreError as error:
            raise LlmSettingsError(str(error)) from error
    credential_available = bool(credential)
    if not credential_available and credential_key:
        try:
            credential_available = bool(get_credential(credential_key))
        except CredentialStoreError as error:
            raise LlmSettingsError(str(error)) from error
    if enabled and not privacy_acknowledged:
        raise LlmSettingsError(
            "Read and accept the data-privacy warning before enabling LLM assistance."
        )
    if enabled and not credential_available:
        raise LlmSettingsError(
            "Store an OpenAI API key securely before enabling LLM assistance."
        )

    data["llm"] = {
        "enabled": enabled,
        "provider": provider,
        "model": model,
        "credential_key": credential_key,
        "privacy_acknowledged": privacy_acknowledged,
        "max_reviews_per_scan": max_reviews_per_scan,
    }
    temporary_path = _validated_temporary_settings(path, data)
    try:
        if credential:
            store_credential(credential_key, credential)
        os.replace(temporary_path, path)
    except (CredentialStoreError, OSError) as error:
        if credential and previous_credential:
            store_credential(credential_key, previous_credential)
        temporary_path.unlink(missing_ok=True)
        raise LlmSettingsError(
            "Junior could not save LLM settings. The previous settings remain active."
        ) from error
    return load_llm_settings_form(path)


def _validated_temporary_settings(
    settings_path: Path,
    data: dict[str, Any],
) -> Path:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{settings_path.name}.",
        suffix=".tmp",
        dir=settings_path.parent,
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            yaml.safe_dump(data, stream, sort_keys=False)
            stream.flush()
            os.fsync(stream.fileno())
        load_settings(temporary_path)
    except (ConfigError, OSError, yaml.YAMLError) as error:
        temporary_path.unlink(missing_ok=True)
        raise LlmSettingsError(str(error)) from error
    return temporary_path
