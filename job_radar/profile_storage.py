"""Persist managed profiles through one transaction-safe SQLite boundary.

This service stores profile identity, preferences, company associations, and
app-owned resume file names. It never accepts or resolves an external resume
path; resume bytes will be managed separately under the user-data resume root.
"""

import json
import sqlite3
from pathlib import Path

from job_radar.database import connect_database
from job_radar.profile_models import (
    FitSignal,
    LocationPreference,
    ManagedProfile,
    ManagedResume,
    OccupationPreference,
    ProfilePreferences,
)
from job_radar.storage import initialize_database


class ProfileStorageError(RuntimeError):
    """Raised when managed profile data cannot be stored or reconstructed."""


class ProfileAlreadyExistsError(ProfileStorageError):
    """Raised when a create operation would reuse an existing stable ID."""


class ProfileSelectionError(ProfileStorageError):
    """Raised when an unavailable profile is selected for normal use."""


def profile_has_job_search_activity(
    database_path: str | Path,
    profile_id: str,
) -> bool:
    """Protect tracker and history records from profile deletion."""
    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        tracker_count = connection.execute(
            "SELECT COUNT(*) FROM application_tracker WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()[0]
        history_count = connection.execute(
            "SELECT COUNT(*) FROM job_history WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()[0]
    return bool(tracker_count or history_count)


def delete_profile(database_path: str | Path, profile_id: str) -> bool:
    """Permanently delete one profile and its database-owned child records."""

    db_path = initialize_database(database_path)
    with connect_database(db_path) as connection:
        existing = connection.execute(
            "SELECT 1 FROM profiles WHERE profile_id = ?", (profile_id,)
        ).fetchone()
        if existing is None:
            return False

        # This table predates cascade deletion, so clear the active pointer first.
        connection.execute(
            "DELETE FROM active_profile_selection WHERE profile_id = ?",
            (profile_id,),
        )
        connection.execute("DELETE FROM profiles WHERE profile_id = ?", (profile_id,))
    return True


def create_profile(
    database_path: str | Path,
    profile: ManagedProfile,
) -> ManagedProfile:
    """Create one profile and all of its owned settings atomically."""

    db_path = initialize_database(database_path)

    try:
        with connect_database(db_path) as connection:
            _insert_profile(connection, profile)
    except sqlite3.IntegrityError as error:
        raise ProfileAlreadyExistsError(
            f"profile already exists: {profile.profile_id}"
        ) from error

    return profile


def create_and_select_profile(
    database_path: str | Path,
    profile: ManagedProfile,
) -> ManagedProfile:
    """Create and select an imported profile in one database transaction."""

    db_path = initialize_database(database_path)

    try:
        with connect_database(db_path) as connection:
            _insert_profile(connection, profile)
            connection.execute(
                """
                INSERT INTO active_profile_selection (
                    singleton_id,
                    profile_id,
                    updated_at
                )
                VALUES (1, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    profile_id = excluded.profile_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (profile.profile_id,),
            )
    except sqlite3.IntegrityError as error:
        raise ProfileAlreadyExistsError(
            f"profile already exists: {profile.profile_id}"
        ) from error

    return profile


def get_profile(
    database_path: str | Path,
    profile_id: str,
) -> ManagedProfile | None:
    """Load one profile by its stable ID."""

    db_path = initialize_database(database_path)

    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM profiles WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()

        if row is None:
            return None

        return _row_to_profile(connection, row)


def list_profiles(
    database_path: str | Path,
    *,
    include_archived: bool = False,
) -> list[ManagedProfile]:
    """List profiles in a stable user-facing order."""

    db_path = initialize_database(database_path)
    query = "SELECT * FROM profiles"
    parameters: tuple[object, ...] = ()

    if not include_archived:
        query += " WHERE archived = ?"
        parameters = (0,)

    query += " ORDER BY display_name COLLATE NOCASE, profile_id"

    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, parameters).fetchall()
        return [_row_to_profile(connection, row) for row in rows]


def get_active_profile(database_path: str | Path) -> ManagedProfile | None:
    """Load the selected non-archived profile, if the user chose one."""

    db_path = initialize_database(database_path)

    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT profiles.*
            FROM active_profile_selection
            JOIN profiles
              ON profiles.profile_id = active_profile_selection.profile_id
            WHERE active_profile_selection.singleton_id = 1
              AND profiles.archived = 0
            """
        ).fetchone()

        if row is None:
            return None

        return _row_to_profile(connection, row)


def set_active_profile(
    database_path: str | Path,
    profile_id: str | None,
) -> None:
    """Select one active profile, or clear the selection for YAML fallback."""

    db_path = initialize_database(database_path)

    with connect_database(db_path) as connection:
        if profile_id is None:
            connection.execute(
                "DELETE FROM active_profile_selection WHERE singleton_id = 1"
            )
            return

        available = connection.execute(
            """
            SELECT 1
            FROM profiles
            WHERE profile_id = ? AND archived = 0
            """,
            (profile_id,),
        ).fetchone()

        if available is None:
            raise ProfileSelectionError(
                f"active profile is missing or archived: {profile_id}"
            )

        connection.execute(
            """
            INSERT INTO active_profile_selection (
                singleton_id,
                profile_id,
                updated_at
            )
            VALUES (1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(singleton_id) DO UPDATE SET
                profile_id = excluded.profile_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (profile_id,),
        )


def update_profile(
    database_path: str | Path,
    profile: ManagedProfile,
) -> bool:
    """Replace one profile's editable values without changing its stable ID."""

    db_path = initialize_database(database_path)

    with connect_database(db_path) as connection:
        existing = connection.execute(
            "SELECT 1 FROM profiles WHERE profile_id = ?",
            (profile.profile_id,),
        ).fetchone()

        if existing is None:
            return False

        _update_profile_row(connection, profile)
        _replace_profile_preferences(connection, profile)
        _replace_company_associations(connection, profile)

    return True


def set_profile_archived(
    database_path: str | Path,
    profile_id: str,
    *,
    archived: bool,
) -> bool:
    """Archive or restore a profile without deleting its data."""

    db_path = initialize_database(database_path)

    with connect_database(db_path) as connection:
        if archived:
            # An archived profile cannot remain selected for future scans.
            connection.execute(
                "DELETE FROM active_profile_selection WHERE profile_id = ?",
                (profile_id,),
            )
        cursor = connection.execute(
            """
            UPDATE profiles
            SET archived = ?, updated_at = CURRENT_TIMESTAMP
            WHERE profile_id = ?
            """,
            (int(archived), profile_id),
        )

    return cursor.rowcount > 0


def _insert_profile(
    connection: sqlite3.Connection,
    profile: ManagedProfile,
) -> None:
    resume_source_file_name = None
    resume_normalized_text_file_name = None

    if profile.resume is not None:
        resume_source_file_name = profile.resume.source_file_name
        resume_normalized_text_file_name = (
            profile.resume.normalized_text_file_name
        )

    connection.execute(
        """
        INSERT INTO profiles (
            profile_id,
            schema_version,
            display_name,
            archived,
            resume_source_file_name,
            resume_normalized_text_file_name,
            scoring_config_file_name,
            scoring_config_json,
            fit_signals_json,
            report_settings_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            profile.profile_id,
            profile.schema_version,
            profile.display_name.strip(),
            int(profile.archived),
            resume_source_file_name,
            resume_normalized_text_file_name,
            profile.scoring_config_file_name,
            (
                _dump_json(profile.scoring_config)
                if profile.scoring_config is not None
                else None
            ),
            _dump_fit_signals(profile.fit_signals),
            _dump_json(profile.report_settings),
        ),
    )
    _replace_profile_preferences(connection, profile)
    _replace_company_associations(connection, profile)


def _update_profile_row(
    connection: sqlite3.Connection,
    profile: ManagedProfile,
) -> None:
    resume_source_file_name = None
    resume_normalized_text_file_name = None

    if profile.resume is not None:
        resume_source_file_name = profile.resume.source_file_name
        resume_normalized_text_file_name = (
            profile.resume.normalized_text_file_name
        )

    connection.execute(
        """
        UPDATE profiles
        SET
            schema_version = ?,
            display_name = ?,
            archived = ?,
            resume_source_file_name = ?,
            resume_normalized_text_file_name = ?,
            scoring_config_file_name = ?,
            scoring_config_json = ?,
            fit_signals_json = ?,
            report_settings_json = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE profile_id = ?
        """,
        (
            profile.schema_version,
            profile.display_name.strip(),
            int(profile.archived),
            resume_source_file_name,
            resume_normalized_text_file_name,
            profile.scoring_config_file_name,
            (
                _dump_json(profile.scoring_config)
                if profile.scoring_config is not None
                else None
            ),
            _dump_fit_signals(profile.fit_signals),
            _dump_json(profile.report_settings),
            profile.profile_id,
        ),
    )


def _replace_profile_preferences(
    connection: sqlite3.Connection,
    profile: ManagedProfile,
) -> None:
    preferences = profile.preferences
    connection.execute(
        "DELETE FROM profile_preferences WHERE profile_id = ?",
        (profile.profile_id,),
    )
    connection.execute(
        """
        INSERT INTO profile_preferences (
            profile_id,
            target_roles_json,
            seniority_levels_json,
            core_strengths_json,
            credible_adjacent_json,
            learning_or_gap_json,
            exclusions_json,
            preferred_locations_json,
            work_arrangements_json,
            employment_types_json,
            compensation_floor_usd,
            compensation_target_usd,
            travel_tolerance,
            schedule_preference,
            on_call_preference,
            occupation_selections_json,
            location_selections_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            profile.profile_id,
            _dump_json(preferences.target_roles),
            _dump_json(preferences.seniority_levels),
            _dump_json(preferences.core_strengths),
            _dump_json(preferences.credible_adjacent),
            _dump_json(preferences.learning_or_gap),
            _dump_json(preferences.exclusions),
            _dump_json(preferences.preferred_locations),
            _dump_json(preferences.work_arrangements),
            _dump_json(preferences.employment_types),
            preferences.compensation_floor_usd,
            preferences.compensation_target_usd,
            preferences.travel_tolerance,
            preferences.schedule_preference,
            preferences.on_call_preference,
            _dump_json(
                [
                    {"value": item.value, "label": item.label}
                    for item in preferences.occupation_selections
                ]
            ),
            _dump_json(
                [
                    {
                        "value": item.value,
                        "label": item.label,
                        "latitude": item.latitude,
                        "longitude": item.longitude,
                        "radius_miles": item.radius_miles,
                    }
                    for item in preferences.location_selections
                ]
            ),
        ),
    )


def _replace_company_associations(
    connection: sqlite3.Connection,
    profile: ManagedProfile,
) -> None:
    connection.execute(
        "DELETE FROM profile_company_associations WHERE profile_id = ?",
        (profile.profile_id,),
    )
    connection.executemany(
        """
        INSERT INTO profile_company_associations (profile_id, company_id)
        VALUES (?, ?)
        """,
        [
            (profile.profile_id, company_id)
            for company_id in profile.company_ids
        ],
    )


def _row_to_profile(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
) -> ManagedProfile:
    preference_row = connection.execute(
        "SELECT * FROM profile_preferences WHERE profile_id = ?",
        (row["profile_id"],),
    ).fetchone()

    if preference_row is None:
        raise ProfileStorageError(
            f"profile preferences are missing: {row['profile_id']}"
        )

    company_rows = connection.execute(
        """
        SELECT company_id
        FROM profile_company_associations
        WHERE profile_id = ?
        ORDER BY company_id
        """,
        (row["profile_id"],),
    ).fetchall()

    try:
        preferences = ProfilePreferences(
            target_roles=_load_string_tuple(preference_row["target_roles_json"]),
            seniority_levels=_load_string_tuple(
                preference_row["seniority_levels_json"]
            ),
            core_strengths=_load_string_tuple(
                preference_row["core_strengths_json"]
            ),
            credible_adjacent=_load_string_tuple(
                preference_row["credible_adjacent_json"]
            ),
            learning_or_gap=_load_string_tuple(
                preference_row["learning_or_gap_json"]
            ),
            exclusions=_load_string_tuple(preference_row["exclusions_json"]),
            preferred_locations=_load_string_tuple(
                preference_row["preferred_locations_json"]
            ),
            work_arrangements=_load_string_tuple(
                preference_row["work_arrangements_json"]
            ),
            employment_types=_load_string_tuple(
                preference_row["employment_types_json"]
            ),
            compensation_floor_usd=preference_row["compensation_floor_usd"],
            compensation_target_usd=preference_row["compensation_target_usd"],
            travel_tolerance=preference_row["travel_tolerance"],
            schedule_preference=preference_row["schedule_preference"],
            on_call_preference=preference_row["on_call_preference"],
            occupation_selections=_load_occupation_preferences(
                preference_row["occupation_selections_json"]
            ),
            location_selections=_load_location_preferences(
                preference_row["location_selections_json"]
            ),
        )
        resume = _build_resume_from_row(row)
        report_settings = _load_json_object(row["report_settings_json"])

        return ManagedProfile(
            profile_id=row["profile_id"],
            display_name=row["display_name"],
            preferences=preferences,
            resume=resume,
            company_ids=tuple(company_row["company_id"] for company_row in company_rows),
            scoring_config_file_name=row["scoring_config_file_name"],
            scoring_config=_load_optional_json_object(row["scoring_config_json"]),
            fit_signals=_load_fit_signals(row["fit_signals_json"]),
            report_settings=report_settings,
            archived=bool(row["archived"]),
            schema_version=row["schema_version"],
        )
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ProfileStorageError(
            f"stored profile is invalid: {row['profile_id']}"
        ) from error


def _build_resume_from_row(row: sqlite3.Row) -> ManagedResume | None:
    source_file_name = row["resume_source_file_name"]
    normalized_text_file_name = row["resume_normalized_text_file_name"]

    if source_file_name is None and normalized_text_file_name is None:
        return None

    if source_file_name is None or normalized_text_file_name is None:
        raise ValueError("stored resume record is incomplete")

    return ManagedResume(
        source_file_name=source_file_name,
        normalized_text_file_name=normalized_text_file_name,
    )


def _dump_json(value: object) -> str:
    try:
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as error:
        raise ProfileStorageError("profile data is not JSON serializable") from error


def _load_string_tuple(raw_value: str) -> tuple[str, ...]:
    value = json.loads(raw_value)

    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise ValueError("stored profile preference must be a list of strings")

    return tuple(value)


def _load_occupation_preferences(
    raw_value: str,
) -> tuple[OccupationPreference, ...]:
    value = json.loads(raw_value)
    if not isinstance(value, list):
        raise ValueError("stored occupations must be a list")
    return tuple(
        OccupationPreference(value=item["value"], label=item["label"])
        for item in value
        if isinstance(item, dict)
    )


def _load_location_preferences(
    raw_value: str,
) -> tuple[LocationPreference, ...]:
    value = json.loads(raw_value)
    if not isinstance(value, list):
        raise ValueError("stored locations must be a list")
    return tuple(
        LocationPreference(
            value=item["value"],
            label=item["label"],
            latitude=item.get("latitude"),
            longitude=item.get("longitude"),
            radius_miles=item["radius_miles"],
        )
        for item in value
        if isinstance(item, dict)
    )


def _dump_fit_signals(signals: tuple[FitSignal, ...]) -> str:
    return _dump_json(
        [
            {
                "term": signal.term,
                "category": signal.category,
                "explanation": signal.explanation,
                "evidence_source": signal.evidence_source,
                "user_overridden": signal.user_overridden,
            }
            for signal in signals
        ]
    )


def _load_fit_signals(raw_value: str) -> tuple[FitSignal, ...]:
    value = json.loads(raw_value)
    if not isinstance(value, list):
        raise ValueError("stored fit signals must be a list")

    signals = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("stored fit signal must be a mapping")
        signals.append(
            FitSignal(
                term=item["term"],
                category=item["category"],
                explanation=item.get("explanation", ""),
                evidence_source=item.get("evidence_source", "profile"),
                user_overridden=item.get("user_overridden", False),
            )
        )
    return tuple(signals)


def _load_optional_json_object(
    raw_value: str | None,
) -> dict[str, object] | None:
    if raw_value is None:
        return None

    value = json.loads(raw_value)

    if not isinstance(value, dict):
        raise ValueError("stored profile scoring config must be a mapping")

    return value


def _load_json_object(raw_value: str) -> dict[str, object]:
    value = json.loads(raw_value)

    if not isinstance(value, dict):
        raise ValueError("stored report settings must be a mapping")

    return value
