"""Load and atomically save consent for external company-source lookup."""

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Any

import yaml

from job_radar.config import ConfigError, load_settings, load_yaml_file


class CompanyDiscoverySettingsError(ValueError):
    """Explain a company-discovery setting problem in normal language."""


@dataclass(frozen=True)
class CompanyDiscoverySettingsForm:
    external_lookup_enabled: bool


def load_company_discovery_settings_form(
    settings_path: str | Path,
) -> CompanyDiscoverySettingsForm:
    settings = load_settings(settings_path).company_discovery
    return CompanyDiscoverySettingsForm(
        external_lookup_enabled=settings.external_lookup_enabled,
    )


def save_company_discovery_settings(
    settings_path: str | Path,
    *,
    external_lookup_enabled: bool,
) -> CompanyDiscoverySettingsForm:
    """Replace only the external-lookup choice after validating the file."""

    if not isinstance(external_lookup_enabled, bool):
        raise CompanyDiscoverySettingsError(
            "External lookup must be turned on or off."
        )
    path = Path(settings_path)
    data = load_yaml_file(path)
    discovery_data = data.get("company_discovery", {})
    if not isinstance(discovery_data, dict):
        raise CompanyDiscoverySettingsError(
            "Junior cannot update an invalid company-discovery section."
        )
    discovery_data = dict(discovery_data)
    discovery_data["external_lookup"] = external_lookup_enabled
    data["company_discovery"] = discovery_data
    temporary_path = _validated_temporary_settings(path, data)
    try:
        os.replace(temporary_path, path)
    except OSError as error:
        temporary_path.unlink(missing_ok=True)
        raise CompanyDiscoverySettingsError(
            "Junior could not save the external lookup choice. "
            "The previous setting remains active."
        ) from error
    return load_company_discovery_settings_form(path)


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
        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
            newline="\n",
        ) as stream:
            yaml.safe_dump(data, stream, sort_keys=False)
            stream.flush()
            os.fsync(stream.fileno())
        load_settings(temporary_path)
    except (ConfigError, OSError, yaml.YAMLError) as error:
        temporary_path.unlink(missing_ok=True)
        raise CompanyDiscoverySettingsError(str(error)) from error
    return temporary_path
