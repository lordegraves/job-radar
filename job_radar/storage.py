"""Own Job Radar's main SQLite schema, migrations, and stored scan history.

This module creates and upgrades the database, records scan lifecycle state,
stores job postings, and preserves application history. Existing databases are
backed up before numbered migrations, and pending migrations run atomically so
a failure cannot leave only part of an upgrade applied.
"""

import sqlite3
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

from job_radar.database import connect_database
from job_radar.history_models import JobHistoryRecord
from job_radar.models import JobPosting
from job_radar.tracker.tracker_storage import (
    initialize_tracker_schema,
    migrate_tracker_schema,
)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS companies (
    company_key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_slug TEXT,
    source_url TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_postings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_key TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_job_id TEXT,
    source_url TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT,
    remote_status TEXT,
    salary_text TEXT,
    description TEXT,
    canonical_key TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_changed_at TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_key) REFERENCES companies(company_key)
);

CREATE TABLE IF NOT EXISTS job_status (
    job_posting_id INTEGER PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'new',
    user_notes TEXT,
    applied_at TEXT,
    rejected_at TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_posting_id) REFERENCES job_postings(id)
);

CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    requested_at TEXT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'completed',
    current_stage TEXT,
    failure_summary TEXT,
    report_status TEXT NOT NULL DEFAULT 'not_started',
    email_status TEXT NOT NULL DEFAULT 'not_requested',
    companies_requested INTEGER NOT NULL DEFAULT 0,
    companies_scanned INTEGER NOT NULL DEFAULT 0,
    companies_enabled INTEGER NOT NULL DEFAULT 0,
    jobs_found INTEGER NOT NULL DEFAULT 0,
    jobs_collected INTEGER NOT NULL DEFAULT 0,
    actionable_jobs_stored INTEGER NOT NULL DEFAULT 0,
    jobs_not_actionable INTEGER NOT NULL DEFAULT 0,
    jobs_new INTEGER NOT NULL DEFAULT 0,
    jobs_seen INTEGER NOT NULL DEFAULT 0,
    jobs_changed INTEGER NOT NULL DEFAULT 0,
    collector_errors INTEGER NOT NULL DEFAULT 0,
    errors_count INTEGER NOT NULL DEFAULT 0,
    top_matches_count INTEGER NOT NULL DEFAULT 0,
    review_needed_count INTEGER NOT NULL DEFAULT 0,
    trigger_source TEXT NOT NULL DEFAULT 'manual'
);

CREATE TABLE IF NOT EXISTS scan_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id INTEGER,
    company_key TEXT,
    source_type TEXT,
    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (scan_run_id) REFERENCES scan_runs(id)
);

CREATE TABLE IF NOT EXISTS job_seen_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_posting_id INTEGER,
    scan_run_id INTEGER,
    event_type TEXT NOT NULL,
    event_details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_posting_id) REFERENCES job_postings(id),
    FOREIGN KEY (scan_run_id) REFERENCES scan_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_job_postings_company_key
ON job_postings(company_key);

CREATE INDEX IF NOT EXISTS idx_job_postings_canonical_key
ON job_postings(canonical_key);

CREATE INDEX IF NOT EXISTS idx_job_postings_content_hash
ON job_postings(content_hash);

CREATE INDEX IF NOT EXISTS idx_job_seen_events_created_at
ON job_seen_events(created_at);

CREATE INDEX IF NOT EXISTS idx_job_postings_source_job_id
ON job_postings(source_type, source_job_id);

CREATE INDEX IF NOT EXISTS idx_job_postings_source_url
ON job_postings(source_url);

CREATE TABLE IF NOT EXISTS job_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    history_type TEXT NOT NULL,
    company TEXT NOT NULL,
    role TEXT NOT NULL,
    source TEXT,
    ats_platform TEXT,
    work_arrangement TEXT,
    location TEXT,
    comp_range TEXT,
    event_date TEXT,
    status TEXT,
    outcome_category TEXT,
    recruiter_contact TEXT,
    technical_match TEXT,
    hiring_probability TEXT,
    skills_signals TEXT,
    primary_blocker TEXT,
    secondary_blocker TEXT,
    revisit TEXT,
    include_in_job_radar INTEGER NOT NULL DEFAULT 1,
    import_key TEXT NOT NULL UNIQUE,
    notes TEXT,
    applied_on TEXT,
    last_activity_on TEXT,
    follow_up_on TEXT,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_job_history_history_type
ON job_history(history_type);

CREATE INDEX IF NOT EXISTS idx_job_history_company
ON job_history(company);

CREATE INDEX IF NOT EXISTS idx_job_history_outcome_category
ON job_history(outcome_category);

CREATE INDEX IF NOT EXISTS idx_job_history_primary_blocker
ON job_history(primary_blocker);
"""


SCHEMA_MIGRATIONS_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def _schema_migrations() -> tuple:
    return (
        (
            1,
            "baseline current schema",
            _migrate_baseline_schema,
        ),
        (
            2,
            "backfill companies for stored jobs",
            _backfill_companies_for_stored_jobs,
        ),
        (
            3,
            "add durable scan lifecycle fields",
            _migrate_scan_runs_table,
        ),
        (
            4,
            "add managed profile storage",
            _migrate_managed_profile_tables,
        ),
        (
            5,
            "add active profile selection",
            _migrate_active_profile_selection,
        ),
        (
            6,
            "add structured search preferences",
            _migrate_structured_search_preferences,
        ),
        (
            7,
            "add on-call profile preference",
            _migrate_on_call_profile_preference,
        ),
        (
            8,
            "add profile-owned scoring config",
            _migrate_profile_scoring_config,
        ),
        (
            9,
            "add profile job-fit signals",
            _migrate_profile_fit_signals,
        ),
        (
            10,
            "add app-owned employer sources",
            _migrate_employer_sources,
        ),
        (
            11,
            "add profile-owned tracker and history",
            _migrate_profile_owned_activity,
        ),
        (
            12,
            "add profile employer assignment state",
            _migrate_profile_employer_assignment_state,
        ),
        (
            13,
            "add employer catalog administration state",
            _migrate_employer_catalog_administration,
        ),
        (
            14,
            "add employer identity resolution and review requests",
            _migrate_employer_resolution,
        ),
        (
            15,
            "add employer review audit",
            _migrate_employer_review_audit,
        ),
        (
            16,
            "add profile company recommendations",
            _migrate_company_recommendations,
        ),
        (
            17,
            "add profile ownership to scan runs",
            _migrate_profile_owned_scan_runs,
        ),
        (
            18,
            "add external employer discovery candidates",
            _migrate_external_employer_discoveries,
        ),
        (
            19,
            "add recommendation administration metadata",
            _migrate_recommendation_administration,
        ),
        (
            20,
            "add resumable first-run setup",
            _migrate_resumable_setup,
        ),
        (
            21,
            "add profile-owned role discovery",
            _migrate_role_discovery,
        ),
        (
            22,
            "add employer source health",
            _migrate_employer_source_health,
        ),
        (
            23,
            "add first-run validation result",
            _migrate_first_run_validation,
        ),
        (
            24,
            "add scan scheduling configuration",
            _migrate_scan_scheduling,
        ),
        (
            25,
            "add long-term scale indexes",
            _migrate_long_term_scale_indexes,
        ),
        (
            26,
            "add security-clearance profile preference",
            _migrate_clearance_profile_preference,
        ),
        (
            27,
            "add profile-owned job decisions",
            _migrate_profile_job_decisions,
        ),
        (
            28,
            "add profile job-decision reasons",
            _migrate_profile_job_decision_reasons,
        ),
        (
            29,
            "add strong location-outlier preference",
            _migrate_strong_location_outlier_preference,
        ),
    )


def _read_applied_schema_versions(database_path: Path) -> set[int]:
    with connect_database(database_path) as connection:
        migration_table_exists = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table'
            AND name = 'schema_migrations'
            """
        ).fetchone()

        if migration_table_exists is None:
            return set()

        return {
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations"
            ).fetchall()
        }


def _backup_database_before_migrations(
    database_path: Path,
    pending_versions: list[int],
) -> Path:
    backup_directory = database_path.parent / "backups"
    backup_directory.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backup_directory / (
        f"{database_path.name}.pre-migration-"
        f"v{min(pending_versions)}-v{max(pending_versions)}-"
        f"{timestamp}.bak"
    )

    with connect_database(database_path) as source_connection:
        with connect_database(backup_path) as backup_connection:
            source_connection.backup(backup_connection)

    return backup_path


def initialize_database(database_path: str | Path) -> Path:
    db_path = Path(database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        applied_versions = _read_applied_schema_versions(db_path)
        pending_versions = [
            version
            for version, _name, _migration in _schema_migrations()
            if version not in applied_versions
        ]

        if pending_versions:
            _backup_database_before_migrations(
                db_path,
                pending_versions,
            )

    with connect_database(db_path) as connection:
        connection.executescript(SCHEMA_SQL)
        initialize_tracker_schema(connection)
        connection.executescript(SCHEMA_MIGRATIONS_SQL)
        _apply_schema_migrations(connection)

    return db_path


def _apply_schema_migrations(connection: sqlite3.Connection) -> None:
    applied_versions = {
        row[0]
        for row in connection.execute(
            "SELECT version FROM schema_migrations"
        ).fetchall()
    }

    # Keep the entire pending upgrade atomic so a failed migration cannot leave
    # a user's database with only part of the new schema applied.
    connection.execute("SAVEPOINT apply_schema_migrations")

    try:
        for version, name, migration in _schema_migrations():
            if version in applied_versions:
                continue

            migration(connection)
            connection.execute(
                """
                INSERT INTO schema_migrations (
                    version,
                    name
                )
                VALUES (?, ?)
                """,
                (version, name),
            )
    except BaseException:
        connection.execute("ROLLBACK TO SAVEPOINT apply_schema_migrations")
        connection.execute("RELEASE SAVEPOINT apply_schema_migrations")
        raise
    else:
        connection.execute("RELEASE SAVEPOINT apply_schema_migrations")


def _migrate_baseline_schema(connection: sqlite3.Connection) -> None:
    _migrate_scan_runs_table(connection)
    _migrate_job_history_table(connection)
    migrate_tracker_schema(connection)


def _migrate_profile_employer_assignment_state(
    connection: sqlite3.Connection,
) -> None:
    """Add profile-specific enabled state to employer assignments."""

    columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(profile_company_associations)"
        ).fetchall()
    }

    if "enabled" not in columns:
        connection.execute(
            """
            ALTER TABLE profile_company_associations
            ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1
            """
        )


def _migrate_profile_owned_activity(connection: sqlite3.Connection) -> None:
    active_profile_row = connection.execute(
        """
        SELECT profile_id
        FROM active_profile_selection
        WHERE singleton_id = 1
        """
    ).fetchone()
    active_profile_id = active_profile_row[0] if active_profile_row else None

    connection.execute("DROP INDEX IF EXISTS idx_application_tracker_status")
    connection.execute("DROP INDEX IF EXISTS idx_application_tracker_follow_up_on")
    connection.execute(
        """
        CREATE TABLE application_tracker_profile_owned (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id TEXT,
            job_radar_id TEXT NOT NULL,
            company_name TEXT NOT NULL,
            role_title TEXT NOT NULL,
            source_url TEXT,
            status TEXT NOT NULL DEFAULT 'review_needed',
            follow_up_on TEXT,
            outcome TEXT,
            notes TEXT,
            applied_on TEXT,
            last_activity_on TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (profile_id) REFERENCES profiles(profile_id)
                ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        """
        INSERT INTO application_tracker_profile_owned (
            profile_id, job_radar_id, company_name, role_title, source_url,
            status, follow_up_on, outcome, notes, applied_on,
            last_activity_on, created_at, updated_at
        )
        SELECT ?, job_radar_id, company_name, role_title, source_url,
               status, follow_up_on, outcome, notes, applied_on,
               last_activity_on, created_at, updated_at
        FROM application_tracker
        """,
        (active_profile_id,),
    )
    connection.execute("DROP TABLE application_tracker")
    connection.execute(
        "ALTER TABLE application_tracker_profile_owned RENAME TO application_tracker"
    )
    connection.execute(
        "CREATE INDEX idx_application_tracker_status ON application_tracker(status)"
    )
    connection.execute(
        "CREATE INDEX idx_application_tracker_follow_up_on "
        "ON application_tracker(follow_up_on)"
    )
    connection.execute(
        "CREATE UNIQUE INDEX idx_application_tracker_profile_job "
        "ON application_tracker(COALESCE(profile_id, ''), job_radar_id)"
    )

    for index_name in (
        "idx_job_history_history_type",
        "idx_job_history_company",
        "idx_job_history_outcome_category",
        "idx_job_history_primary_blocker",
    ):
        connection.execute(f"DROP INDEX IF EXISTS {index_name}")

    history_columns = [
        row[1]
        for row in connection.execute("PRAGMA table_info(job_history)").fetchall()
        if row[1] not in {"id", "profile_id"}
    ]
    history_column_sql = ", ".join(history_columns)
    connection.execute(
        """
        CREATE TABLE job_history_profile_owned (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id TEXT,
            history_type TEXT NOT NULL,
            company TEXT NOT NULL,
            role TEXT NOT NULL,
            source TEXT,
            ats_platform TEXT,
            work_arrangement TEXT,
            location TEXT,
            comp_range TEXT,
            event_date TEXT,
            status TEXT,
            outcome_category TEXT,
            recruiter_contact TEXT,
            technical_match TEXT,
            hiring_probability TEXT,
            skills_signals TEXT,
            primary_blocker TEXT,
            secondary_blocker TEXT,
            revisit TEXT,
            include_in_job_radar INTEGER NOT NULL DEFAULT 1,
            import_key TEXT NOT NULL,
            notes TEXT,
            applied_on TEXT,
            last_activity_on TEXT,
            follow_up_on TEXT,
            job_radar_id TEXT,
            posting_url TEXT,
            lead_source TEXT,
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (profile_id) REFERENCES profiles(profile_id)
                ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        f"""
        INSERT INTO job_history_profile_owned (profile_id, {history_column_sql})
        SELECT ?, {history_column_sql}
        FROM job_history
        """,
        (active_profile_id,),
    )
    connection.execute("DROP TABLE job_history")
    connection.execute(
        "ALTER TABLE job_history_profile_owned RENAME TO job_history"
    )
    connection.execute(
        "CREATE INDEX idx_job_history_history_type ON job_history(history_type)"
    )
    connection.execute(
        "CREATE INDEX idx_job_history_company ON job_history(company)"
    )
    connection.execute(
        "CREATE INDEX idx_job_history_outcome_category "
        "ON job_history(outcome_category)"
    )
    connection.execute(
        "CREATE INDEX idx_job_history_primary_blocker "
        "ON job_history(primary_blocker)"
    )
    connection.execute(
        "CREATE UNIQUE INDEX idx_job_history_profile_import_key "
        "ON job_history(COALESCE(profile_id, ''), import_key)"
    )


def _backfill_companies_for_stored_jobs(
    connection: sqlite3.Connection,
) -> None:
    connection.execute(
        """
        INSERT INTO companies (
            company_key,
            name,
            source_type,
            enabled
        )
        SELECT DISTINCT
            company_key,
            company_key,
            source_type,
            1
        FROM job_postings
        WHERE company_key NOT IN (
            SELECT company_key
            FROM companies
        )
        """
    )


def _migrate_scan_runs_table(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(scan_runs)").fetchall()
    }

    required_columns = {
        "generated_at": "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "requested_at": "TEXT",
        "current_stage": "TEXT",
        "failure_summary": "TEXT",
        "report_status": "TEXT NOT NULL DEFAULT 'not_started'",
        "email_status": "TEXT NOT NULL DEFAULT 'not_requested'",
        "companies_enabled": "INTEGER NOT NULL DEFAULT 0",
        "jobs_collected": "INTEGER NOT NULL DEFAULT 0",
        "actionable_jobs_stored": "INTEGER NOT NULL DEFAULT 0",
        "jobs_not_actionable": "INTEGER NOT NULL DEFAULT 0",
        "jobs_seen": "INTEGER NOT NULL DEFAULT 0",
        "collector_errors": "INTEGER NOT NULL DEFAULT 0",
        "top_matches_count": "INTEGER NOT NULL DEFAULT 0",
        "review_needed_count": "INTEGER NOT NULL DEFAULT 0",
    }

    for column_name, column_definition in required_columns.items():
        if column_name in existing_columns:
            continue

        connection.execute(
            f"ALTER TABLE scan_runs ADD COLUMN {column_name} {column_definition}"
        )


def _migrate_job_history_table(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(job_history)").fetchall()
    }

    required_columns = {
        "applied_on": "TEXT",
        "last_activity_on": "TEXT",
        "follow_up_on": "TEXT",
    }

    for column_name, column_definition in required_columns.items():
        if column_name in existing_columns:
            continue

        connection.execute(
            f"ALTER TABLE job_history ADD COLUMN {column_name} {column_definition}"
        )


def _migrate_profile_fit_signals(connection: sqlite3.Connection) -> None:
    """Add ordered user-visible fit signals without changing existing scoring."""

    existing_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(profiles)").fetchall()
    }
    if "fit_signals_json" not in existing_columns:
        connection.execute(
            "ALTER TABLE profiles "
            "ADD COLUMN fit_signals_json TEXT NOT NULL DEFAULT '[]'"
        )


def _migrate_employer_sources(connection: sqlite3.Connection) -> None:
    """Add complete app-owned employer sources and legacy import state."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS employer_sources (
            employer_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            source_config_json TEXT NOT NULL DEFAULT '{}',
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_employer_sources_enabled_name
        ON employer_sources(enabled, name)
        """
    )

    existing_profile_columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(profiles)"
        ).fetchall()
    }

    if "legacy_company_import_pending" not in existing_profile_columns:
        connection.execute(
            "ALTER TABLE profiles "
            "ADD COLUMN legacy_company_import_pending INTEGER NOT NULL "
            "DEFAULT 0"
        )
        connection.execute(
            """
            UPDATE profiles
            SET legacy_company_import_pending = 1
            WHERE profile_id = (
                SELECT profile_id
                FROM active_profile_selection
                WHERE singleton_id = 1
            )
            """
        )


def _migrate_employer_catalog_administration(
    connection: sqlite3.Connection,
) -> None:
    """Add reversible global lifecycle state and a sanitized change audit."""

    existing_columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(employer_sources)"
        ).fetchall()
    }
    required_columns = {
        "retired": "INTEGER NOT NULL DEFAULT 0",
        "validation_state": "TEXT NOT NULL DEFAULT 'not_checked'",
        "validation_issues_json": "TEXT NOT NULL DEFAULT '[]'",
        "last_validated_at": "TEXT",
        "creation_source": "TEXT NOT NULL DEFAULT 'existing_catalog'",
    }
    for column_name, definition in required_columns.items():
        if column_name not in existing_columns:
            connection.execute(
                f"ALTER TABLE employer_sources ADD COLUMN "
                f"{column_name} {definition}"
            )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS employer_catalog_audit (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            employer_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            previous_state_json TEXT NOT NULL,
            new_state_json TEXT NOT NULL,
            change_source TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_employer_catalog_audit_employer
        ON employer_catalog_audit(employer_id, audit_id DESC)
        """
    )


def _migrate_employer_source_health(connection: sqlite3.Connection) -> None:
    """Store safe connection-test outcomes without raw collector failures."""

    existing_columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(employer_sources)"
        ).fetchall()
    }
    required_columns = {
        "last_connection_test_at": "TEXT",
        "last_connection_success_at": "TEXT",
        "last_connection_error_at": "TEXT",
        "last_connection_state": "TEXT NOT NULL DEFAULT 'not_tested'",
        "last_connection_category": "TEXT",
        "last_connection_message": "TEXT",
        "last_connection_job_count": "INTEGER",
    }
    for column_name, definition in required_columns.items():
        if column_name not in existing_columns:
            connection.execute(
                f"ALTER TABLE employer_sources ADD COLUMN "
                f"{column_name} {definition}"
            )


def _migrate_first_run_validation(connection: sqlite3.Connection) -> None:
    """Persist the latest bounded setup-validation result."""

    existing_columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(setup_progress)"
        ).fetchall()
    }
    required_columns = {
        "validation_state": "TEXT NOT NULL DEFAULT 'not_tested'",
        "validation_message": "TEXT",
        "validated_employer_id": "TEXT",
        "validated_at": "TEXT",
    }
    for column_name, definition in required_columns.items():
        if column_name not in existing_columns:
            connection.execute(
                f"ALTER TABLE setup_progress ADD COLUMN "
                f"{column_name} {definition}"
            )


def _migrate_employer_resolution(connection: sqlite3.Connection) -> None:
    """Add normalized identity and unresolved user-submission storage."""

    existing_columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(employer_sources)"
        ).fetchall()
    }
    required_columns = {
        "normalized_name": "TEXT",
        "normalized_careers_url": "TEXT",
        "source_identifier": "TEXT",
        "resolution_status": "TEXT NOT NULL DEFAULT 'existing'",
        "submitted_name": "TEXT",
        "submitted_url": "TEXT",
    }
    for column_name, definition in required_columns.items():
        if column_name not in existing_columns:
            connection.execute(
                f"ALTER TABLE employer_sources ADD COLUMN "
                f"{column_name} {definition}"
            )

    for employer_id, name in connection.execute(
        """
        SELECT employer_id, name
        FROM employer_sources
        WHERE normalized_name IS NULL
        """
    ).fetchall():
        normalized_name = unicodedata.normalize(
            "NFKC",
            " ".join(str(name).strip().split()),
        ).casefold()
        connection.execute(
            """
            UPDATE employer_sources
            SET normalized_name = ?
            WHERE employer_id = ?
            """,
            (normalized_name, employer_id),
        )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_employer_normalized_careers_url
        ON employer_sources(normalized_careers_url)
        WHERE normalized_careers_url IS NOT NULL
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_employer_source_identifier
        ON employer_sources(source_type, source_identifier)
        WHERE source_identifier IS NOT NULL
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS employer_aliases (
            employer_id TEXT NOT NULL,
            alias TEXT NOT NULL,
            normalized_alias TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (employer_id, normalized_alias),
            FOREIGN KEY (employer_id) REFERENCES employer_sources(employer_id)
                ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS employer_review_requests (
            request_id TEXT PRIMARY KEY,
            submitted_company_name TEXT,
            submitted_careers_url TEXT,
            normalized_company_name TEXT NOT NULL DEFAULT '',
            normalized_careers_url TEXT NOT NULL DEFAULT '',
            requesting_profile_id TEXT NOT NULL,
            detection_result TEXT NOT NULL,
            possible_employer_ids_json TEXT NOT NULL DEFAULT '[]',
            safe_summary TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TEXT,
            resolved_employer_id TEXT,
            UNIQUE (
                requesting_profile_id,
                normalized_company_name,
                normalized_careers_url,
                status
            ),
            FOREIGN KEY (requesting_profile_id) REFERENCES profiles(profile_id)
                ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_employer_review_status_created
        ON employer_review_requests(status, created_at)
        """
    )


def _migrate_employer_review_audit(connection: sqlite3.Connection) -> None:
    """Record safe review-queue decisions without raw collector failures."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS employer_review_audit (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            previous_status TEXT NOT NULL,
            new_status TEXT NOT NULL,
            resolved_employer_id TEXT,
            assignment_requested INTEGER NOT NULL DEFAULT 0,
            assignment_completed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_employer_review_audit_request
        ON employer_review_audit(request_id, audit_id DESC)
        """
    )


def _migrate_company_recommendations(connection: sqlite3.Connection) -> None:
    """Store profile-owned recommendation state and bounded cooldowns."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS company_recommendations (
            profile_id TEXT NOT NULL,
            employer_id TEXT NOT NULL,
            recommendation_score INTEGER NOT NULL,
            evidence_json TEXT NOT NULL DEFAULT '[]',
            availability_state TEXT NOT NULL,
            recommendation_state TEXT NOT NULL DEFAULT 'NEW',
            generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_evaluated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            hidden_until TEXT,
            PRIMARY KEY (profile_id, employer_id)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_company_recommendations_profile_state
        ON company_recommendations(
            profile_id, recommendation_state, recommendation_score DESC
        )
        """
    )


def _migrate_profile_owned_scan_runs(connection: sqlite3.Connection) -> None:
    """Label future scan evidence without guessing ownership of old scans."""

    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(scan_runs)").fetchall()
    }
    if "profile_id" not in columns:
        connection.execute("ALTER TABLE scan_runs ADD COLUMN profile_id TEXT")
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_scan_runs_profile_finished
        ON scan_runs(profile_id, finished_at DESC)
        """
    )


def _migrate_scan_scheduling(connection: sqlite3.Connection) -> None:
    """Add one durable schedule and distinguish scheduled scan history."""
    scan_columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(scan_runs)").fetchall()
    }
    if "trigger_source" not in scan_columns:
        connection.execute(
            """
            ALTER TABLE scan_runs
            ADD COLUMN trigger_source TEXT NOT NULL DEFAULT 'manual'
            """
        )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS scan_schedule (
            singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
            enabled INTEGER NOT NULL DEFAULT 0,
            run_time TEXT NOT NULL DEFAULT '09:00',
            weekdays_json TEXT NOT NULL DEFAULT '[]',
            email_delivery INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO scan_schedule (
            singleton_id, enabled, run_time, weekdays_json, email_delivery
        )
        VALUES (1, 0, '09:00', '[]', 0)
        """
    )


def _migrate_long_term_scale_indexes(connection: sqlite3.Connection) -> None:
    """Keep profile-owned history and current-job lookups bounded as data grows."""

    statements = (
        """
        CREATE INDEX IF NOT EXISTS idx_tracker_profile_updated
        ON application_tracker(profile_id, updated_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_history_profile_included_event
        ON job_history(profile_id, include_in_job_radar, event_date DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_job_postings_company_active_seen
        ON job_postings(company_key, is_active, last_seen_at DESC)
        """,
    )
    for statement in statements:
        connection.execute(statement)


def _migrate_external_employer_discoveries(
    connection: sqlite3.Connection,
) -> None:
    """Cache bounded external candidates and their review disposition."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS external_employer_discoveries (
            profile_id TEXT NOT NULL,
            candidate_key TEXT NOT NULL,
            proposed_name TEXT NOT NULL,
            proposed_careers_url TEXT,
            discovery_source TEXT NOT NULL,
            evidence_json TEXT NOT NULL DEFAULT '[]',
            possible_employer_id TEXT,
            detection_result TEXT NOT NULL,
            confidence TEXT NOT NULL,
            readiness_state TEXT NOT NULL,
            discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_evaluated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            review_request_id TEXT,
            PRIMARY KEY (profile_id, candidate_key)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_external_discoveries_profile_state
        ON external_employer_discoveries(
            profile_id, readiness_state, last_evaluated_at DESC
        )
        """
    )


def _migrate_recommendation_administration(
    connection: sqlite3.Connection,
) -> None:
    """Store global recommendation metadata and a sanitized admin audit."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS employer_recommendation_metadata (
            employer_id TEXT PRIMARY KEY,
            industries_json TEXT NOT NULL DEFAULT '[]',
            occupation_families_json TEXT NOT NULL DEFAULT '[]',
            employer_type TEXT NOT NULL DEFAULT '',
            geographic_presence_json TEXT NOT NULL DEFAULT '[]',
            remote_hiring_metadata TEXT NOT NULL DEFAULT '',
            eligibility TEXT NOT NULL DEFAULT 'needs_review',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (employer_id) REFERENCES employer_sources(employer_id)
                ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS recommendation_admin_audit (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            employer_id TEXT NOT NULL,
            profile_id TEXT,
            operation TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_recommendation_admin_audit_employer
        ON recommendation_admin_audit(employer_id, audit_id DESC)
        """
    )


def _migrate_resumable_setup(connection: sqlite3.Connection) -> None:
    """Store one installation-local onboarding checkpoint."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS setup_progress (
            singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
            current_step TEXT NOT NULL,
            profile_id TEXT,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT
        )
        """
    )


def _migrate_role_discovery(connection: sqlite3.Connection) -> None:
    """Store explained title suggestions and profile-specific feedback."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS role_discovery_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id TEXT NOT NULL,
            suggested_title TEXT NOT NULL,
            normalized_title TEXT NOT NULL,
            occupation_code TEXT,
            employer_context TEXT,
            context_key TEXT NOT NULL,
            source_type TEXT NOT NULL CHECK (
                source_type IN ('occupation_catalog', 'observed_posting')
            ),
            explanation TEXT NOT NULL,
            evidence_json TEXT NOT NULL DEFAULT '[]',
            feedback_state TEXT NOT NULL DEFAULT 'pending' CHECK (
                feedback_state IN (
                    'pending',
                    'relevant',
                    'not_relevant',
                    'different_discipline'
                )
            ),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TEXT,
            UNIQUE (profile_id, normalized_title, context_key),
            FOREIGN KEY (profile_id) REFERENCES profiles(profile_id)
                ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_role_discovery_profile_feedback
        ON role_discovery_suggestions(profile_id, feedback_state, updated_at)
        """
    )


def _migrate_managed_profile_tables(connection: sqlite3.Connection) -> None:
    """Create profile records without assigning existing user data yet."""

    # sqlite3.executescript() commits implicitly and would end the migration
    # savepoint. Execute each statement separately so failure rolls back every
    # profile table and index as one atomic migration.
    statements = (
        """
        CREATE TABLE IF NOT EXISTS profiles (
            profile_id TEXT PRIMARY KEY,
            schema_version INTEGER NOT NULL,
            display_name TEXT NOT NULL,
            archived INTEGER NOT NULL DEFAULT 0,
            resume_source_file_name TEXT,
            resume_normalized_text_file_name TEXT,
            scoring_config_file_name TEXT NOT NULL DEFAULT 'scoring.yaml',
            report_settings_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS profile_preferences (
            profile_id TEXT PRIMARY KEY,
            target_roles_json TEXT NOT NULL DEFAULT '[]',
            seniority_levels_json TEXT NOT NULL DEFAULT '[]',
            core_strengths_json TEXT NOT NULL DEFAULT '[]',
            credible_adjacent_json TEXT NOT NULL DEFAULT '[]',
            learning_or_gap_json TEXT NOT NULL DEFAULT '[]',
            exclusions_json TEXT NOT NULL DEFAULT '[]',
            preferred_locations_json TEXT NOT NULL DEFAULT '[]',
            work_arrangements_json TEXT NOT NULL DEFAULT '[]',
            employment_types_json TEXT NOT NULL DEFAULT '[]',
            compensation_floor_usd INTEGER,
            compensation_target_usd INTEGER,
            travel_tolerance TEXT,
            FOREIGN KEY (profile_id) REFERENCES profiles(profile_id)
                ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS profile_company_associations (
            profile_id TEXT NOT NULL,
            company_id TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (profile_id, company_id),
            FOREIGN KEY (profile_id) REFERENCES profiles(profile_id)
                ON DELETE CASCADE
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_profiles_archived_display_name
        ON profiles(archived, display_name)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_profile_company_associations_company_id
        ON profile_company_associations(company_id)
        """,
    )

    for statement in statements:
        connection.execute(statement)


def _migrate_profile_job_decisions(connection: sqlite3.Connection) -> None:
    """Store bookmarks and passes without turning them into applications."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS profile_job_decisions (
            profile_id TEXT NOT NULL,
            job_radar_id TEXT NOT NULL,
            decision TEXT NOT NULL CHECK (decision IN ('saved', 'passed')),
            company TEXT NOT NULL,
            title TEXT NOT NULL,
            source_url TEXT,
            location TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (profile_id, job_radar_id),
            FOREIGN KEY (profile_id) REFERENCES profiles(profile_id)
                ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_profile_job_decisions_state
        ON profile_job_decisions(profile_id, decision, updated_at)
        """
    )


def _migrate_profile_job_decision_reasons(
    connection: sqlite3.Connection,
) -> None:
    """Keep a bounded user reason separate from free-form job notes."""

    existing_columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(profile_job_decisions)"
        ).fetchall()
    }
    if "decision_reason" not in existing_columns:
        connection.execute(
            "ALTER TABLE profile_job_decisions "
            "ADD COLUMN decision_reason TEXT"
        )


def _migrate_active_profile_selection(connection: sqlite3.Connection) -> None:
    """Add one optional active-profile choice without selecting existing data."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS active_profile_selection (
            singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
            profile_id TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (profile_id) REFERENCES profiles(profile_id)
        )
        """
    )


def _migrate_structured_search_preferences(
    connection: sqlite3.Connection,
) -> None:
    """Add normalized GUI selections without changing existing preference data."""

    existing_columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(profile_preferences)"
        ).fetchall()
    }
    required_columns = {
        "schedule_preference": "TEXT",
        "occupation_selections_json": "TEXT NOT NULL DEFAULT '[]'",
        "location_selections_json": "TEXT NOT NULL DEFAULT '[]'",
    }

    for column_name, column_definition in required_columns.items():
        if column_name not in existing_columns:
            connection.execute(
                f"ALTER TABLE profile_preferences "
                f"ADD COLUMN {column_name} {column_definition}"
            )


def _migrate_on_call_profile_preference(
    connection: sqlite3.Connection,
) -> None:
    """Add explicit on-call handling while preserving existing behavior."""

    existing_columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(profile_preferences)"
        ).fetchall()
    }
    if "on_call_preference" not in existing_columns:
        connection.execute(
            "ALTER TABLE profile_preferences "
            "ADD COLUMN on_call_preference TEXT NOT NULL "
            "DEFAULT 'Review each job'"
        )


def _migrate_clearance_profile_preference(
    connection: sqlite3.Connection,
) -> None:
    """Make clearance handling explicit without weakening legacy exclusions."""

    existing_columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(profile_preferences)"
        ).fetchall()
    }
    if "clearance_preference" not in existing_columns:
        connection.execute(
            "ALTER TABLE profile_preferences "
            "ADD COLUMN clearance_preference TEXT NOT NULL "
            "DEFAULT 'Review each job'"
        )
        # Profiles that already excluded clearance-only roles retain that
        # behavior after the preference becomes visible in the GUI.
        connection.execute(
            "UPDATE profile_preferences "
            "SET clearance_preference = "
            "'Exclude jobs requiring an existing active clearance' "
            "WHERE replace(lower(exclusions_json), '-', ' ') "
            "LIKE '%cleared only roles%'"
        )


def _migrate_strong_location_outlier_preference(
    connection: sqlite3.Connection,
) -> None:
    """Add an opt-in exception without changing any existing profile behavior."""

    existing_columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(profile_preferences)"
        ).fetchall()
    }
    if "include_strong_location_outliers" not in existing_columns:
        connection.execute(
            "ALTER TABLE profile_preferences "
            "ADD COLUMN include_strong_location_outliers INTEGER NOT NULL "
            "DEFAULT 0"
        )


def _migrate_profile_scoring_config(
    connection: sqlite3.Connection,
) -> None:
    """Mark existing profiles for one-time legacy scoring import."""

    existing_columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(profiles)").fetchall()
    }

    if "scoring_config_json" not in existing_columns:
        connection.execute(
            "ALTER TABLE profiles ADD COLUMN scoring_config_json TEXT"
        )

    if "legacy_scoring_import_pending" not in existing_columns:
        connection.execute(
            "ALTER TABLE profiles "
            "ADD COLUMN legacy_scoring_import_pending INTEGER NOT NULL "
            "DEFAULT 0"
        )
        connection.execute(
            "UPDATE profiles "
            "SET legacy_scoring_import_pending = 1 "
            "WHERE scoring_config_json IS NULL "
            "AND profile_id = ("
            "SELECT profile_id "
            "FROM active_profile_selection "
            "WHERE singleton_id = 1"
            ")"
        )


def fetch_active_scan_run(
    database_path: str | Path,
) -> sqlite3.Row | None:
    db_path = Path(database_path)

    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row

        return connection.execute(
            """
            SELECT *
            FROM scan_runs
            WHERE status = 'running'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()


def fetch_latest_scan_run(
    database_path: str | Path,
) -> sqlite3.Row | None:
    db_path = Path(database_path)

    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row

        return connection.execute(
            """
            SELECT *
            FROM scan_runs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()


def start_scan_run(
    database_path: str | Path,
    *,
    requested_at: str,
    companies_requested: int,
    companies_enabled: int,
    current_stage: str = "initialization",
    profile_id: str | None = None,
    trigger_source: str = "manual",
) -> int:
    db_path = Path(database_path)

    with connect_database(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO scan_runs (
                generated_at,
                requested_at,
                started_at,
                status,
                current_stage,
                companies_requested,
                companies_enabled,
                profile_id,
                trigger_source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                requested_at,
                requested_at,
                requested_at,
                "running",
                current_stage,
                companies_requested,
                companies_enabled,
                profile_id,
                trigger_source,
            ),
        )

        return int(cursor.lastrowid)


def update_scan_run_progress(
    database_path: str | Path,
    *,
    scan_run_id: int,
    current_stage: str,
    companies_scanned: int | None = None,
    jobs_found: int | None = None,
    collector_errors: int | None = None,
) -> bool:
    db_path = Path(database_path)

    with connect_database(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE scan_runs
            SET
                current_stage = ?,
                companies_scanned = COALESCE(?, companies_scanned),
                jobs_found = COALESCE(?, jobs_found),
                jobs_collected = COALESCE(?, jobs_collected),
                collector_errors = COALESCE(?, collector_errors),
                errors_count = COALESCE(?, errors_count)
            WHERE id = ?
            AND status = 'running'
            """,
            (
                current_stage,
                companies_scanned,
                jobs_found,
                jobs_found,
                collector_errors,
                collector_errors,
                scan_run_id,
            ),
        )

        return cursor.rowcount == 1


def complete_scan_run(
    database_path: str | Path,
    *,
    scan_run_id: int,
    generated_at: str,
    finished_at: str,
    companies_scanned: int,
    jobs_collected: int,
    actionable_jobs_stored: int,
    jobs_not_actionable: int,
    jobs_new: int,
    jobs_seen: int,
    jobs_changed: int,
    collector_errors: int,
    top_matches_count: int,
    review_needed_count: int,
    report_status: str,
    email_status: str,
) -> bool:
    status = (
        "completed_with_warnings"
        if collector_errors
        else "completed"
    )
    db_path = Path(database_path)

    with connect_database(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE scan_runs
            SET
                generated_at = ?,
                finished_at = ?,
                status = ?,
                current_stage = 'completed',
                failure_summary = NULL,
                report_status = ?,
                email_status = ?,
                companies_scanned = ?,
                jobs_found = ?,
                jobs_collected = ?,
                actionable_jobs_stored = ?,
                jobs_not_actionable = ?,
                jobs_new = ?,
                jobs_seen = ?,
                jobs_changed = ?,
                collector_errors = ?,
                errors_count = ?,
                top_matches_count = ?,
                review_needed_count = ?
            WHERE id = ?
            AND status = 'running'
            """,
            (
                generated_at,
                finished_at,
                status,
                report_status,
                email_status,
                companies_scanned,
                jobs_collected,
                jobs_collected,
                actionable_jobs_stored,
                jobs_not_actionable,
                jobs_new,
                jobs_seen,
                jobs_changed,
                collector_errors,
                collector_errors,
                top_matches_count,
                review_needed_count,
                scan_run_id,
            ),
        )

        return cursor.rowcount == 1


def fail_scan_run(
    database_path: str | Path,
    *,
    scan_run_id: int,
    finished_at: str,
    failed_stage: str,
    failure_summary: str,
    companies_scanned: int = 0,
    jobs_found: int = 0,
    collector_errors: int = 0,
) -> bool:
    db_path = Path(database_path)

    with connect_database(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE scan_runs
            SET
                finished_at = ?,
                status = 'failed',
                current_stage = ?,
                failure_summary = ?,
                companies_scanned = ?,
                jobs_found = ?,
                jobs_collected = ?,
                collector_errors = ?,
                errors_count = ?
            WHERE id = ?
            AND status = 'running'
            """,
            (
                finished_at,
                failed_stage,
                failure_summary,
                companies_scanned,
                jobs_found,
                jobs_found,
                collector_errors,
                collector_errors,
                scan_run_id,
            ),
        )

        return cursor.rowcount == 1


def record_scan_error(
    database_path: str | Path,
    *,
    scan_run_id: int,
    error_type: str,
    error_message: str,
    company_key: str | None = None,
    source_type: str | None = None,
) -> int:
    db_path = Path(database_path)

    with connect_database(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO scan_errors (
                scan_run_id,
                company_key,
                source_type,
                error_type,
                error_message
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                scan_run_id,
                company_key,
                source_type,
                error_type,
                error_message,
            ),
        )

        return int(cursor.lastrowid)


def record_scan_run(
    database_path: str | Path,
    *,
    generated_at: str,
    companies_enabled: int,
    jobs_collected: int,
    actionable_jobs_stored: int,
    jobs_not_actionable: int,
    jobs_new: int,
    jobs_seen: int,
    jobs_changed: int,
    collector_errors: int,
    top_matches_count: int,
    review_needed_count: int,
) -> int:
    db_path = Path(database_path)

    with connect_database(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO scan_runs (
                generated_at,
                finished_at,
                status,
                companies_requested,
                companies_scanned,
                companies_enabled,
                jobs_found,
                jobs_collected,
                actionable_jobs_stored,
                jobs_not_actionable,
                jobs_new,
                jobs_seen,
                jobs_changed,
                collector_errors,
                errors_count,
                top_matches_count,
                review_needed_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                generated_at,
                generated_at,
                "completed",
                companies_enabled,
                companies_enabled,
                companies_enabled,
                jobs_collected,
                jobs_collected,
                actionable_jobs_stored,
                jobs_not_actionable,
                jobs_new,
                jobs_seen,
                jobs_changed,
                collector_errors,
                collector_errors,
                top_matches_count,
                review_needed_count,
            ),
        )

        return int(cursor.lastrowid)


def _find_existing_job(
    connection: sqlite3.Connection,
    posting: JobPosting,
) -> sqlite3.Row | None:
    if posting.source_job_id:
        return connection.execute(
            """
            SELECT id, content_hash
            FROM job_postings
            WHERE source_type = ?
            AND source_job_id = ?
            """,
            (posting.source_type, posting.source_job_id),
        ).fetchone()

    if posting.source_url:
        return connection.execute(
            """
            SELECT id, content_hash
            FROM job_postings
            WHERE source_url = ?
            """,
            (posting.source_url,),
        ).fetchone()

    return connection.execute(
        """
        SELECT id, content_hash
        FROM job_postings
        WHERE canonical_key = ?
        """,
        (posting.canonical_key,),
    ).fetchone()


def _upsert_company_for_posting(
    connection: sqlite3.Connection,
    posting: JobPosting,
) -> None:
    connection.execute(
        """
        INSERT INTO companies (
            company_key,
            name,
            source_type,
            enabled
        )
        VALUES (?, ?, ?, 1)
        ON CONFLICT(company_key) DO UPDATE SET
            name = excluded.name,
            source_type = excluded.source_type,
            enabled = 1,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            posting.company_key,
            posting.company_name,
            posting.source_type,
        ),
    )


def upsert_job_posting(
    database_path: str | Path,
    posting: JobPosting,
    *,
    scan_run_id: int | None = None,
) -> str:
    db_path = Path(database_path)

    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row

        _upsert_company_for_posting(connection, posting)
        existing = _find_existing_job(connection, posting)

        if existing is None:
            cursor = connection.execute(
                """
                INSERT INTO job_postings (
                    company_key,
                    source_type,
                    source_job_id,
                    source_url,
                    title,
                    location,
                    remote_status,
                    salary_text,
                    description,
                    canonical_key,
                    content_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    posting.company_key,
                    posting.source_type,
                    posting.source_job_id,
                    posting.source_url,
                    posting.title,
                    posting.location,
                    posting.remote_status,
                    posting.salary_text,
                    posting.description,
                    posting.canonical_key,
                    posting.content_hash,
                ),
            )

            job_posting_id = cursor.lastrowid

            connection.execute(
                """
                INSERT INTO job_status (
                    job_posting_id,
                    status
                )
                VALUES (?, 'new')
                """,
                (job_posting_id,),
            )

            result = "new"
        elif existing["content_hash"] != posting.content_hash:
            connection.execute(
                """
                UPDATE job_postings
                SET
                    company_key = ?,
                    source_type = ?,
                    source_job_id = ?,
                    source_url = ?,
                    title = ?,
                    location = ?,
                    remote_status = ?,
                    salary_text = ?,
                    description = ?,
                    canonical_key = ?,
                    content_hash = ?,
                    last_seen_at = CURRENT_TIMESTAMP,
                    last_changed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP,
                    is_active = 1
                WHERE id = ?
                """,
                (
                    posting.company_key,
                    posting.source_type,
                    posting.source_job_id,
                    posting.source_url,
                    posting.title,
                    posting.location,
                    posting.remote_status,
                    posting.salary_text,
                    posting.description,
                    posting.canonical_key,
                    posting.content_hash,
                    existing["id"],
                ),
            )
            job_posting_id = existing["id"]
            result = "changed"
        else:
            connection.execute(
                """
                UPDATE job_postings
                SET
                    last_seen_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP,
                    is_active = 1
                WHERE id = ?
                """,
                (existing["id"],),
            )
            job_posting_id = existing["id"]
            result = "seen"

        if scan_run_id is not None:
            connection.execute(
                """
                INSERT INTO job_seen_events (
                    job_posting_id, scan_run_id, event_type
                ) VALUES (?, ?, ?)
                """,
                (job_posting_id, scan_run_id, result),
            )
        return result


def upsert_job_history_record_with_connection(
    connection: sqlite3.Connection,
    record: JobHistoryRecord,
    *,
    profile_id: str | None = None,
) -> str:
    existing = connection.execute(
        """
        SELECT id
        FROM job_history
        WHERE import_key = ? AND profile_id IS ?
        """,
        (record.import_key, profile_id),
    ).fetchone()

    values = (
        record.history_type,
        record.company,
        record.role,
        record.source,
        record.ats_platform,
        record.work_arrangement,
        record.location,
        record.comp_range,
        record.event_date,
        record.status,
        record.outcome_category,
        record.recruiter_contact,
        record.technical_match,
        record.hiring_probability,
        record.skills_signals,
        record.primary_blocker,
        record.secondary_blocker,
        record.revisit,
        1 if record.include_in_job_radar else 0,
        record.import_key,
        record.notes,
        record.applied_on,
        record.last_activity_on,
        record.follow_up_on,
    )

    if existing is None:
        connection.execute(
            """
            INSERT INTO job_history (
                profile_id,
                history_type,
                company,
                role,
                source,
                ats_platform,
                work_arrangement,
                location,
                comp_range,
                event_date,
                status,
                outcome_category,
                recruiter_contact,
                technical_match,
                hiring_probability,
                skills_signals,
                primary_blocker,
                secondary_blocker,
                revisit,
                include_in_job_radar,
                import_key,
                notes,
                applied_on,
                last_activity_on,
                follow_up_on
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (profile_id,) + values,
        )

        return "new"

    connection.execute(
        """
        UPDATE job_history
        SET
            history_type = ?,
            company = ?,
            role = ?,
            source = ?,
            ats_platform = ?,
            work_arrangement = ?,
            location = ?,
            comp_range = ?,
            event_date = ?,
            status = ?,
            outcome_category = ?,
            recruiter_contact = ?,
            technical_match = ?,
            hiring_probability = ?,
            skills_signals = ?,
            primary_blocker = ?,
            secondary_blocker = ?,
            revisit = ?,
            include_in_job_radar = ?,
            notes = ?,
            applied_on = ?,
            last_activity_on = ?,
            follow_up_on = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE import_key = ? AND profile_id IS ?
        """,
        values[:19] + values[20:] + (record.import_key, profile_id),
    )

    return "updated"


def upsert_job_history_record(
    database_path: str | Path,
    record: JobHistoryRecord,
    *,
    profile_id: str | None = None,
) -> str:
    db_path = Path(database_path)

    with connect_database(db_path) as connection:
        return upsert_job_history_record_with_connection(
            connection,
            record,
            profile_id=profile_id,
        )


def delete_job_history_record_with_connection(
    connection: sqlite3.Connection,
    import_key: str,
    *,
    profile_id: str | None = None,
) -> bool:
    cursor = connection.execute(
        """
        DELETE FROM job_history
        WHERE import_key = ? AND profile_id IS ?
        """,
        (import_key, profile_id),
    )

    return cursor.rowcount > 0


def delete_job_history_record(
    database_path: str | Path,
    import_key: str,
    *,
    profile_id: str | None = None,
) -> bool:
    db_path = Path(database_path)

    with connect_database(db_path) as connection:
        return delete_job_history_record_with_connection(
            connection,
            import_key,
            profile_id=profile_id,
        )


def fetch_included_job_history_records(
    database_path: str | Path,
    *,
    profile_id: str | None = None,
) -> list[JobHistoryRecord]:
    db_path = Path(database_path)

    with connect_database(db_path) as connection:
        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT
                history_type,
                company,
                role,
                source,
                ats_platform,
                work_arrangement,
                location,
                comp_range,
                event_date,
                status,
                outcome_category,
                recruiter_contact,
                technical_match,
                hiring_probability,
                skills_signals,
                primary_blocker,
                secondary_blocker,
                revisit,
                include_in_job_radar,
                import_key,
                notes,
                applied_on,
                last_activity_on,
                follow_up_on
            FROM job_history
            WHERE include_in_job_radar = 1 AND profile_id IS ?
            ORDER BY event_date DESC, company ASC, role ASC
            """,
            (profile_id,),
        ).fetchall()

    return [
        JobHistoryRecord(
            history_type=row["history_type"],
            company=row["company"],
            role=row["role"],
            source=row["source"],
            ats_platform=row["ats_platform"],
            work_arrangement=row["work_arrangement"],
            location=row["location"],
            comp_range=row["comp_range"],
            event_date=row["event_date"],
            status=row["status"],
            outcome_category=row["outcome_category"],
            recruiter_contact=row["recruiter_contact"],
            technical_match=row["technical_match"],
            hiring_probability=row["hiring_probability"],
            skills_signals=row["skills_signals"],
            primary_blocker=row["primary_blocker"],
            secondary_blocker=row["secondary_blocker"],
            revisit=row["revisit"],
            include_in_job_radar=bool(row["include_in_job_radar"]),
            import_key=row["import_key"],
            notes=row["notes"],
            applied_on=row["applied_on"],
            last_activity_on=row["last_activity_on"],
            follow_up_on=row["follow_up_on"],
        )
        for row in rows
    ]
