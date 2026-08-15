"""Import and resolve scoring rules owned by managed profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from job_radar.database import connect_database
from job_radar.profile_storage import get_active_profile
from job_radar.scoring import load_scoring_config
from job_radar.storage import initialize_database


def build_neutral_scoring_config() -> dict[str, Any]:
    """Return occupation-neutral scoring structure for a new managed profile."""

    return {
        "positive_keywords": {},
        "negative_keywords": {},
        "location_preferences": {
            "allowed": {},
            "conditional": {},
            "skipped": {},
        },
        "top_matches": {
            "min_score": 120,
            "excluded_title_keywords": [],
            "strong_signals": [],
            "review_signals": [],
        },
        "review_needed": {
            "min_score": 100,
            "excluded_location_statuses": [
                "skipped",
                "unknown",
            ],
            "strong_signals": [],
        },
    }


def import_pending_legacy_scoring(
    database_path: str | Path,
    scoring_path: str | Path,
) -> str | None:
    """Import legacy YAML scoring into the marked active managed profile once."""

    db_path = initialize_database(database_path)

    with connect_database(db_path) as connection:
        pending_profile = connection.execute(
            """
            SELECT profiles.profile_id
            FROM active_profile_selection
            JOIN profiles
              ON profiles.profile_id = active_profile_selection.profile_id
            WHERE active_profile_selection.singleton_id = 1
              AND profiles.archived = 0
              AND profiles.legacy_scoring_import_pending = 1
              AND profiles.scoring_config_json IS NULL
            """
        ).fetchone()

        if pending_profile is None:
            return None

        scoring_config = load_scoring_config(scoring_path)
        scoring_config_json = json.dumps(
            scoring_config,
            separators=(",", ":"),
            sort_keys=True,
        )

        cursor = connection.execute(
            """
            UPDATE profiles
            SET scoring_config_json = ?,
                legacy_scoring_import_pending = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE profile_id = ?
              AND legacy_scoring_import_pending = 1
              AND scoring_config_json IS NULL
            """,
            (
                scoring_config_json,
                pending_profile[0],
            ),
        )

        if cursor.rowcount != 1:
            return None

        return str(pending_profile[0])


def resolve_effective_scoring_config(
    database_path: str | Path,
    scoring_path: str | Path,
) -> dict[str, Any]:
    """Use active profile scoring and preserve YAML fallback for legacy users."""

    import_pending_legacy_scoring(database_path, scoring_path)

    active_profile = get_active_profile(database_path)

    if active_profile is not None and active_profile.scoring_config is not None:
        if active_profile.fit_signals:
            # Re-derive only the user-owned Job Fit terms so profiles saved by
            # older builds receive corrected title-versus-skill scoping too.
            from job_radar.profile_fit_service import (
                _apply_fit_signals_to_scoring_config,
            )

            return _apply_fit_signals_to_scoring_config(
                active_profile.scoring_config,
                active_profile.fit_signals,
                target_roles=active_profile.preferences.target_roles,
            )
        return active_profile.scoring_config

    return load_scoring_config(scoring_path)
