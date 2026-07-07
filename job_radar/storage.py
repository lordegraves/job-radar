import sqlite3
from pathlib import Path

from job_radar.job_history import JobHistoryRecord
from job_radar.models import JobPosting
from job_radar.tracker.tracker_storage import initialize_tracker_tables


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
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'completed',
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


def initialize_database(database_path: str | Path) -> Path:
    db_path = Path(database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as connection:
        connection.executescript(SCHEMA_SQL)
        _migrate_scan_runs_table(connection)

    initialize_tracker_tables(db_path)

    return db_path


def _migrate_scan_runs_table(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(scan_runs)").fetchall()
    }

    required_columns = {
        "generated_at": "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
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

    with sqlite3.connect(db_path) as connection:
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


def upsert_job_posting(database_path: str | Path, posting: JobPosting) -> str:
    db_path = Path(database_path)

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row

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


def upsert_job_history_record(
    database_path: str | Path,
    record: JobHistoryRecord,
) -> str:
    db_path = Path(database_path)

    with sqlite3.connect(db_path) as connection:
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
                    notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                updated_at = CURRENT_TIMESTAMP
            WHERE import_key = ?
            """,
            values[:-2] + (record.notes, record.import_key),
        )

        return "updated"


def delete_job_history_record(
    database_path: str | Path,
    import_key: str,
) -> bool:
    db_path = Path(database_path)

    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            """
            DELETE FROM job_history
            WHERE import_key = ?
            """,
            (import_key,),
        )

        return cursor.rowcount > 0


def fetch_included_job_history_records(
    database_path: str | Path,
) -> list[JobHistoryRecord]:
    db_path = Path(database_path)

    with sqlite3.connect(db_path) as connection:
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
                notes
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
        )
        for row in rows
    ]
