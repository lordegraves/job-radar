"""Tests for importing and resolving managed-profile scoring."""

from pathlib import Path

from job_radar.database import connect_database
from job_radar.profile_models import ManagedProfile
from job_radar.profile_scoring import (
    import_pending_legacy_scoring,
    resolve_effective_scoring_config,
)
from job_radar.profile_storage import (
    create_profile,
    get_profile,
    set_active_profile,
)
from job_radar.storage import initialize_database


def write_scoring_file(path: Path) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
positive_keywords:
  linux: 10
  hpc: 10
negative_keywords:
  sales: -15
location_preferences:
  allowed:
    remote: 100
  conditional: {}
  skipped: {}
top_matches:
  min_score: 120
  excluded_title_keywords:
    - sales
  strong_signals:
    - title:linux
review_needed:
  min_score: 100
  excluded_location_statuses:
    - skipped
    - unknown
  strong_signals:
    - body:hpc
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return {
        "positive_keywords": {
            "linux": 10,
            "hpc": 10,
        },
        "negative_keywords": {
            "sales": -15,
        },
        "location_preferences": {
            "allowed": {
                "remote": 100,
            },
            "conditional": {},
            "skipped": {},
        },
        "top_matches": {
            "min_score": 120,
            "excluded_title_keywords": [
                "sales",
            ],
            "strong_signals": [
                "title:linux",
            ],
        },
        "review_needed": {
            "min_score": 100,
            "excluded_location_statuses": [
                "skipped",
                "unknown",
            ],
            "strong_signals": [
                "body:hpc",
            ],
        },
    }


def test_import_pending_legacy_scoring_updates_only_marked_active_profile(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    scoring_path = tmp_path / "config" / "scoring.yaml"
    expected_scoring = write_scoring_file(scoring_path)

    initialize_database(database_path)

    active_profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Existing Active Profile",
    )
    other_profile = ManagedProfile(
        profile_id="profile_bbbbbbbb",
        display_name="Existing Other Profile",
    )

    create_profile(database_path, active_profile)
    create_profile(database_path, other_profile)
    set_active_profile(database_path, active_profile.profile_id)

    with connect_database(database_path) as connection:
        connection.execute(
            """
            UPDATE profiles
            SET legacy_scoring_import_pending = 1
            WHERE profile_id = ?
            """,
            (active_profile.profile_id,),
        )

    imported_profile_id = import_pending_legacy_scoring(
        database_path,
        scoring_path,
    )

    imported_profile = get_profile(database_path, active_profile.profile_id)
    unchanged_profile = get_profile(database_path, other_profile.profile_id)

    assert imported_profile_id == active_profile.profile_id
    assert imported_profile is not None
    assert imported_profile.scoring_config == expected_scoring
    assert unchanged_profile is not None
    assert unchanged_profile.scoring_config is None

    with connect_database(database_path) as connection:
        import_pending = connection.execute(
            """
            SELECT legacy_scoring_import_pending
            FROM profiles
            WHERE profile_id = ?
            """,
            (active_profile.profile_id,),
        ).fetchone()

    assert import_pending == (0,)


def test_import_pending_legacy_scoring_does_nothing_without_pending_profile(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    initialize_database(database_path)

    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="New Profile",
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)

    imported_profile_id = import_pending_legacy_scoring(
        database_path,
        tmp_path / "missing-scoring.yaml",
    )

    stored_profile = get_profile(database_path, profile.profile_id)

    assert imported_profile_id is None
    assert stored_profile is not None
    assert stored_profile.scoring_config is None


def test_resolve_effective_scoring_uses_profile_owned_config(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    profile_scoring = {
        "positive_keywords": {"baker": 10},
        "negative_keywords": {},
        "location_preferences": {
            "allowed": {},
            "conditional": {},
            "skipped": {},
        },
        "top_matches": {
            "min_score": 30,
            "excluded_title_keywords": [],
            "strong_signals": ["title:baker"],
        },
        "review_needed": {
            "min_score": 10,
            "excluded_location_statuses": [],
            "strong_signals": ["body:baker"],
        },
    }

    profile = ManagedProfile(
        profile_id="profile_aaaaaaaa",
        display_name="Baker Profile",
        scoring_config=profile_scoring,
    )
    create_profile(database_path, profile)
    set_active_profile(database_path, profile.profile_id)

    resolved = resolve_effective_scoring_config(
        database_path,
        tmp_path / "missing-scoring.yaml",
    )

    assert resolved == profile_scoring


def test_resolve_effective_scoring_preserves_yaml_fallback(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "job_radar.sqlite3"
    scoring_path = tmp_path / "config" / "scoring.yaml"
    expected_scoring = write_scoring_file(scoring_path)

    resolved = resolve_effective_scoring_config(
        database_path,
        scoring_path,
    )

    assert resolved == expected_scoring
