import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from job_radar.database import connect_database
from job_radar.job_history import JobHistoryRecord
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
    review_needed_count INTEGER NOT NULL DEFAULT 0
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


def _migrate_baseline_schema(connection: sqlite3.Connection) -> None:
    _migrate_scan_runs_table(connection)
    _migrate_job_history_table(connection)
    migrate_tracker_schema(connection)


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


def start_scan_run(
    database_path: str | Path,
    *,
    requested_at: str,
    companies_requested: int,
    companies_enabled: int,
    current_stage: str = "initialization",
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
                companies_enabled
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                requested_at,
                requested_at,
                requested_at,
                "running",
                current_stage,
                companies_requested,
                companies_enabled,
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


def upsert_job_posting(database_path: str | Path, posting: JobPosting) -> str:
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

            return "new"

        if existing["content_hash"] != posting.content_hash:
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

            return "changed"

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

        return "seen"


def upsert_job_history_record_with_connection(
    connection: sqlite3.Connection,
    record: JobHistoryRecord,
) -> str:
    existing = connection.execute(
        """
        SELECT id
        FROM job_history
        WHERE import_key = ?
        """,
        (record.import_key,),
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
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
        WHERE import_key = ?
        """,
        values[:19] + values[20:] + (record.import_key,),
    )

    return "updated"


def upsert_job_history_record(
    database_path: str | Path,
    record: JobHistoryRecord,
) -> str:
    db_path = Path(database_path)

    with connect_database(db_path) as connection:
        return upsert_job_history_record_with_connection(connection, record)


def delete_job_history_record_with_connection(
    connection: sqlite3.Connection,
    import_key: str,
) -> bool:
    cursor = connection.execute(
        """
        DELETE FROM job_history
        WHERE import_key = ?
        """,
        (import_key,),
    )

    return cursor.rowcount > 0


def delete_job_history_record(
    database_path: str | Path,
    import_key: str,
) -> bool:
    db_path = Path(database_path)

    with connect_database(db_path) as connection:
        return delete_job_history_record_with_connection(connection, import_key)


def fetch_included_job_history_records(
    database_path: str | Path,
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
            WHERE include_in_job_radar = 1
            ORDER BY event_date DESC, company ASC, role ASC
            """
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
