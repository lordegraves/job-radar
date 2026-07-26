"""Build safe, read-only installation details for the About page."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from job_radar import __build__, __version__
from job_radar.database import connect_database
from job_radar.profile_models import PROFILE_SCHEMA_VERSION


@dataclass(frozen=True)
class ApplicationInfo:
    """Expose useful version and storage facts without private user content."""

    version: str
    release_channel: str
    user_data_location: str
    database_schema_version: str
    profile_schema_version: str
    build_label: str = __build__


def build_application_info(
    *,
    database_path: str | Path,
    user_data_location: str | Path,
) -> ApplicationInfo:
    """Read bounded application metadata without changing the database."""

    version = __version__
    return ApplicationInfo(
        version=version,
        release_channel=f"{_release_channel(version)} ({__build__})",
        user_data_location=str(Path(user_data_location).resolve()),
        database_schema_version=_database_schema_version(database_path),
        profile_schema_version=str(PROFILE_SCHEMA_VERSION),
    )


def _release_channel(version: str) -> str:
    lowered = version.lower()
    if any(marker in lowered for marker in ("dev", "a", "b", "rc")):
        return "Development or pre-release"
    return "Stable"


def _database_schema_version(database_path: str | Path) -> str:
    try:
        with connect_database(database_path) as connection:
            row = connection.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()
    except sqlite3.Error:
        return "Unavailable"
    if row is None or row[0] is None:
        return "Not initialized"
    return str(row[0])
