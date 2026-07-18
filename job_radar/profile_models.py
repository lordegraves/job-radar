"""Define managed profiles without depending on files outside Job Radar.

Profiles use stable application-owned IDs. Resume records contain only names
inside Job Radar's managed resume directory, so moving or renaming an original
file in Documents, Downloads, or cloud storage cannot break an active profile.
"""

from dataclasses import dataclass, field
from pathlib import Path
import re


PROFILE_SCHEMA_VERSION = 1
PROFILE_ID_PATTERN = re.compile(r"^profile_[a-z0-9]{8,32}$")
SUPPORTED_MANAGED_RESUME_EXTENSIONS = {".docx", ".md", ".pdf", ".txt"}
MANAGED_RESUME_BASENAME = "resume"
NORMALIZED_RESUME_FILENAME = "resume.normalized.txt"


@dataclass(frozen=True)
class ManagedResume:
    """Identify resume files stored inside Job Radar's managed user-data area."""

    source_file_name: str
    normalized_text_file_name: str = NORMALIZED_RESUME_FILENAME

    def __post_init__(self) -> None:
        source_path = Path(self.source_file_name)
        normalized_path = Path(self.normalized_text_file_name)

        if source_path.name != self.source_file_name:
            raise ValueError("managed resume source must be a file name, not a path")

        if source_path.stem != MANAGED_RESUME_BASENAME:
            raise ValueError("managed resume source must use the app-owned name 'resume'")

        if source_path.suffix.lower() not in SUPPORTED_MANAGED_RESUME_EXTENSIONS:
            raise ValueError("managed resume source uses an unsupported file type")

        if normalized_path.name != self.normalized_text_file_name:
            raise ValueError("normalized resume must be a file name, not a path")

        if self.normalized_text_file_name != NORMALIZED_RESUME_FILENAME:
            raise ValueError(
                "normalized resume must use the app-owned name "
                f"'{NORMALIZED_RESUME_FILENAME}'"
            )


@dataclass(frozen=True)
class ProfilePreferences:
    """Hold the user-editable job-search preferences owned by one profile."""

    target_roles: tuple[str, ...] = ()
    seniority_levels: tuple[str, ...] = ()
    core_strengths: tuple[str, ...] = ()
    credible_adjacent: tuple[str, ...] = ()
    learning_or_gap: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()
    preferred_locations: tuple[str, ...] = ()
    work_arrangements: tuple[str, ...] = ()
    employment_types: tuple[str, ...] = ()
    compensation_floor_usd: int | None = None
    compensation_target_usd: int | None = None
    travel_tolerance: str | None = None

    def __post_init__(self) -> None:
        list_fields = (
            self.target_roles,
            self.seniority_levels,
            self.core_strengths,
            self.credible_adjacent,
            self.learning_or_gap,
            self.exclusions,
            self.preferred_locations,
            self.work_arrangements,
            self.employment_types,
        )

        for values in list_fields:
            if not all(isinstance(value, str) and value.strip() for value in values):
                raise ValueError("profile preference lists require non-empty strings")

        for value in (
            self.compensation_floor_usd,
            self.compensation_target_usd,
        ):
            if value is not None and (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                raise ValueError(
                    "profile compensation values must be non-negative integers"
                )

        if self.travel_tolerance is not None and (
            not isinstance(self.travel_tolerance, str)
            or not self.travel_tolerance.strip()
        ):
            raise ValueError("travel_tolerance must be a non-empty string")


@dataclass(frozen=True)
class ManagedProfile:
    """Represent one portable job search with stable application-owned identity."""

    profile_id: str
    display_name: str
    preferences: ProfilePreferences = field(default_factory=ProfilePreferences)
    resume: ManagedResume | None = None
    company_ids: tuple[str, ...] = ()
    scoring_config_file_name: str = "scoring.yaml"
    report_settings: dict[str, object] = field(default_factory=dict)
    archived: bool = False
    schema_version: int = PROFILE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not PROFILE_ID_PATTERN.fullmatch(self.profile_id):
            raise ValueError(
                "profile_id must use the form profile_ followed by 8 to 32 "
                "lowercase letters or numbers"
            )

        if not self.display_name.strip():
            raise ValueError("display_name cannot be empty")

        scoring_path = Path(self.scoring_config_file_name)

        if scoring_path.name != self.scoring_config_file_name:
            raise ValueError("scoring config must be a file name, not a path")

        if self.scoring_config_file_name != "scoring.yaml":
            raise ValueError("scoring config must use the app-owned name 'scoring.yaml'")

        if len(set(self.company_ids)) != len(self.company_ids):
            raise ValueError("company_ids cannot contain duplicates")

        if not all(
            isinstance(company_id, str) and company_id.strip()
            for company_id in self.company_ids
        ):
            raise ValueError("company_ids require non-empty strings")

        if self.schema_version != PROFILE_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported profile schema version: {self.schema_version}"
            )


def get_managed_resume_directory(profile_id: str) -> Path:
    """Return the relative user-data directory reserved for one profile's resume."""

    if not PROFILE_ID_PATTERN.fullmatch(profile_id):
        raise ValueError("cannot build a resume directory for an invalid profile_id")

    return Path("resumes") / profile_id


def build_managed_resume(extension: str) -> ManagedResume:
    """Build the app-owned resume names used after a validated upload."""

    normalized_extension = extension.lower()

    if normalized_extension not in SUPPORTED_MANAGED_RESUME_EXTENSIONS:
        raise ValueError("managed resume source uses an unsupported file type")

    return ManagedResume(
        source_file_name=f"{MANAGED_RESUME_BASENAME}{normalized_extension}",
    )
