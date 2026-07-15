import sqlite3
from pathlib import Path

from job_radar.database import connect_database
from job_radar.tracker.tracker_ids import build_manual_job_radar_id
from job_radar.tracker.tracker_models import ApplicationRecord


TRACKER_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS application_tracker (
    job_radar_id TEXT PRIMARY KEY,
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
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_application_tracker_status
ON application_tracker(status);

CREATE INDEX IF NOT EXISTS idx_application_tracker_follow_up_on
ON application_tracker(follow_up_on);
"""


def initialize_tracker_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(TRACKER_SCHEMA_SQL)


def migrate_tracker_schema(connection: sqlite3.Connection) -> None:
    _ensure_tracker_column(connection, "applied_on", "TEXT")
    _ensure_tracker_column(connection, "last_activity_on", "TEXT")
    _repair_url_backed_tracker_ids(connection)


def initialize_tracker_tables(database_path: str | Path) -> Path:
    db_path = Path(database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with connect_database(db_path) as connection:
        initialize_tracker_schema(connection)
        migrate_tracker_schema(connection)

    return db_path


def _ensure_tracker_column(
    connection: sqlite3.Connection,
    column_name: str,
    column_type: str,
) -> None:
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(application_tracker)")
    }

    if column_name in columns:
        return

    connection.execute(
        f"ALTER TABLE application_tracker ADD COLUMN {column_name} {column_type}"
    )


def _repair_url_backed_tracker_ids(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT job_radar_id, company_name, role_title, source_url
        FROM application_tracker
        WHERE job_radar_id LIKE 'posting-url:%'
        """
    ).fetchall()

    for old_job_radar_id, company_name, role_title, source_url in rows:
        new_job_radar_id = build_manual_job_radar_id(
            company_name=company_name,
            role_title=role_title,
            source_url=source_url,
            source_key=old_job_radar_id,
        )

        existing = connection.execute(
            """
            SELECT job_radar_id
            FROM application_tracker
            WHERE job_radar_id = ?
            """,
            (new_job_radar_id,),
        ).fetchone()

        if existing is not None:
            continue

        # Older spreadsheet imports used posting URLs as tracker primary keys.
        # Repair them once so the GUI shows app-owned Job Radar IDs instead.
        connection.execute(
            """
            UPDATE application_tracker
            SET job_radar_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE job_radar_id = ?
            """,
            (new_job_radar_id, old_job_radar_id),
        )


def upsert_application(
    database_path: str | Path,
    record: ApplicationRecord,
) -> str:
    db_path = Path(database_path)

    with connect_database(db_path) as connection:
        existing = connection.execute(
            """
            SELECT job_radar_id
            FROM application_tracker
            WHERE job_radar_id = ?
            """,
            (record.job_radar_id,),
        ).fetchone()

        if existing is None:
            connection.execute(
                """
                INSERT INTO application_tracker (
                    job_radar_id,
                    company_name,
                    role_title,
                    source_url,
                    status,
                    follow_up_on,
                    outcome,
                    notes,
                    applied_on,
                    last_activity_on
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.job_radar_id,
                    record.company_name,
                    record.role_title,
                    record.source_url,
                    record.status,
                    record.follow_up_on,
                    record.outcome,
                    record.notes,
                    record.applied_on,
                    record.last_activity_on,
                ),
            )

            return "new"

        connection.execute(
            """
            UPDATE application_tracker
            SET
                company_name = ?,
                role_title = ?,
                source_url = ?,
                status = ?,
                follow_up_on = ?,
                outcome = ?,
                notes = ?,
                applied_on = COALESCE(?, applied_on),
                last_activity_on = COALESCE(?, last_activity_on),
                updated_at = CURRENT_TIMESTAMP
            WHERE job_radar_id = ?
            """,
            (
                record.company_name,
                record.role_title,
                record.source_url,
                record.status,
                record.follow_up_on,
                record.outcome,
                record.notes,
                record.applied_on,
                record.last_activity_on,
                record.job_radar_id,
            ),
        )

        return "updated"


def delete_application(
    database_path: str | Path,
    job_radar_id: str,
) -> bool:
    db_path = Path(database_path)

    with connect_database(db_path) as connection:
        cursor = connection.execute(
            """
            DELETE FROM application_tracker
            WHERE job_radar_id = ?
            """,
            (job_radar_id,),
        )

        return cursor.rowcount > 0


def update_application_status(
    database_path: str | Path,
    *,
    job_radar_id: str,
    status: str,
    follow_up_on: str | None = None,
    outcome: str | None = None,
    notes: str | None = None,
    applied_on: str | None = None,
    last_activity_on: str | None = None,
) -> bool:
    db_path = Path(database_path)

    with connect_database(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE application_tracker
            SET
                status = ?,
                follow_up_on = ?,
                outcome = ?,
                notes = ?,
                applied_on = COALESCE(?, applied_on),
                last_activity_on = COALESCE(?, last_activity_on),
                updated_at = CURRENT_TIMESTAMP
            WHERE job_radar_id = ?
            """,
            (
                status,
                follow_up_on,
                outcome,
                notes,
                applied_on,
                last_activity_on,
                job_radar_id,
            ),
        )

        return cursor.rowcount > 0


def list_applications(database_path: str | Path) -> list[ApplicationRecord]:
    db_path = Path(database_path)

    with connect_database(db_path) as connection:
        _repair_url_backed_tracker_ids(connection)
        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT
                job_radar_id,
                company_name,
                role_title,
                source_url,
                status,
                follow_up_on,
                outcome,
                notes,
                applied_on,
                last_activity_on,
                created_at,
                updated_at
            FROM application_tracker
            ORDER BY updated_at DESC, company_name ASC, role_title ASC
            """
        ).fetchall()

    return [_row_to_application_record(row) for row in rows]


def get_application(
    database_path: str | Path,
    job_radar_id: str,
) -> ApplicationRecord | None:
    db_path = Path(database_path)

    with connect_database(db_path) as connection:
        _repair_url_backed_tracker_ids(connection)
        connection.row_factory = sqlite3.Row

        row = connection.execute(
            """
            SELECT
                job_radar_id,
                company_name,
                role_title,
                source_url,
                status,
                follow_up_on,
                outcome,
                notes,
                applied_on,
                last_activity_on,
                created_at,
                updated_at
            FROM application_tracker
            WHERE job_radar_id = ?
            """,
            (job_radar_id,),
        ).fetchone()

    if row is None:
        return None

    return _row_to_application_record(row)


def _row_to_application_record(row: sqlite3.Row) -> ApplicationRecord:
    return ApplicationRecord(
        job_radar_id=row["job_radar_id"],
        company_name=row["company_name"],
        role_title=row["role_title"],
        source_url=row["source_url"],
        status=row["status"],
        follow_up_on=row["follow_up_on"],
        outcome=row["outcome"],
        notes=row["notes"],
        applied_on=row["applied_on"],
        last_activity_on=row["last_activity_on"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
