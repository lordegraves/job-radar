"""Validate and atomically save Junior's report and log retention choices."""

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Any

import yaml

from job_radar.config import (
    ConfigError,
    RetentionPolicySettings,
    load_settings,
    load_yaml_file,
)


POLICY_OPTIONS = (
    ("latest_only", "Keep latest only"),
    ("latest_plus_previous", "Keep latest and previous"),
    ("keep_last_n", "Keep a chosen number of runs"),
)


class RetentionSettingsError(ValueError):
    """Explain a retention setup problem without exposing local contents."""


@dataclass(frozen=True)
class RetentionSettingsForm:
    reports: RetentionPolicySettings
    logs: RetentionPolicySettings
    policy_options: tuple[tuple[str, str], ...] = POLICY_OPTIONS


def load_retention_settings_form(
    settings_path: str | Path,
) -> RetentionSettingsForm:
    retention = load_settings(settings_path).retention
    return RetentionSettingsForm(
        reports=retention.reports,
        logs=retention.logs,
    )


def save_retention_settings(
    settings_path: str | Path,
    *,
    report_policy: str,
    report_count_text: str,
    log_policy: str,
    log_count_text: str,
) -> RetentionSettingsForm:
    """Replace only known retention keys after validating the whole file."""
    path = Path(settings_path)
    data = load_yaml_file(path)
    retention_data = data.get("retention", {})
    if not isinstance(retention_data, dict):
        raise RetentionSettingsError(
            "Junior cannot update an invalid retention section."
        )
    retention_data = dict(retention_data)
    retention_data.update(
        {
            "report_policy": report_policy,
            "report_count": _parse_count(report_count_text, "report"),
            "log_policy": log_policy,
            "log_count": _parse_count(log_count_text, "log"),
        }
    )
    data["retention"] = retention_data
    temporary_path = _validated_temporary_settings(path, data)
    try:
        os.replace(temporary_path, path)
    except OSError as error:
        temporary_path.unlink(missing_ok=True)
        raise RetentionSettingsError(
            "Junior could not save retention settings. "
            "The previous settings remain active."
        ) from error
    return load_retention_settings_form(path)


def _parse_count(value: str, label: str) -> int:
    try:
        count = int(value)
    except ValueError as error:
        raise RetentionSettingsError(
            f"The {label} retention count must be a number."
        ) from error
    if not 1 <= count <= 50:
        raise RetentionSettingsError(
            f"The {label} retention count must be between 1 and 50."
        )
    return count


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
        raise RetentionSettingsError(str(error)) from error
    return temporary_path
