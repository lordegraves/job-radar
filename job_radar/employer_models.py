"""Define app-owned employers and their complete collector source settings."""

from dataclasses import dataclass, field
from typing import Any

from job_radar.config import SUPPORTED_SOURCE_TYPES


@dataclass(frozen=True)
class ProfileEmployerAssignment:
    """Represent one profile's scanning state for a global employer source."""

    profile_id: str
    employer_id: str
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.profile_id.strip():
            raise ValueError("profile_id cannot be empty")

        if not self.employer_id.strip():
            raise ValueError("employer_id cannot be empty")

        if not isinstance(self.enabled, bool):
            raise ValueError("profile employer enabled state must be a boolean")


@dataclass(frozen=True)
class EmployerSource:
    """Represent one employer and the source junior can scan for its jobs."""

    employer_id: str
    name: str
    source_type: str
    enabled: bool = True
    source_config: dict[str, Any] = field(default_factory=dict)
    notes: str | None = None

    def __post_init__(self) -> None:
        if not self.employer_id.strip():
            raise ValueError("employer_id cannot be empty")

        if not self.name.strip():
            raise ValueError("employer name cannot be empty")

        if self.source_type not in SUPPORTED_SOURCE_TYPES:
            raise ValueError(f"unsupported employer source type: {self.source_type}")

        if not isinstance(self.enabled, bool):
            raise ValueError("employer enabled state must be a boolean")

        if not isinstance(self.source_config, dict):
            raise ValueError("employer source config must be a mapping")

        if self.notes is not None and not isinstance(self.notes, str):
            raise ValueError("employer notes must be text")

    def to_company_config(self) -> dict[str, Any]:
        """Return the complete collector mapping expected by existing collectors."""

        config = dict(self.source_config)
        config.update(
            {
                "company_key": self.employer_id,
                "name": self.name,
                "source_type": self.source_type,
                "enabled": self.enabled,
            }
        )

        if self.notes is not None:
            config["notes"] = self.notes
        else:
            config.pop("notes", None)

        return config
