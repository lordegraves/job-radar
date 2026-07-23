"""Validate, store, and explain Junior's application-wide scan schedule."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
import json
from pathlib import Path

from job_radar.database import connect_database
from job_radar.storage import initialize_database


WEEKDAYS = (
    ("monday", "Monday"),
    ("tuesday", "Tuesday"),
    ("wednesday", "Wednesday"),
    ("thursday", "Thursday"),
    ("friday", "Friday"),
    ("saturday", "Saturday"),
    ("sunday", "Sunday"),
)
_WEEKDAY_INDEX = {name: index for index, (name, _label) in enumerate(WEEKDAYS)}


class ScheduleError(ValueError):
    """Report a schedule problem in language suitable for the Settings page."""


@dataclass(frozen=True)
class ScanSchedule:
    enabled: bool
    run_time: str
    weekdays: tuple[str, ...]
    email_delivery: bool


@dataclass(frozen=True)
class ScheduledRunSummary:
    status: str
    tone: str
    finished_at: str | None
    message: str


@dataclass(frozen=True)
class ScheduleView:
    schedule: ScanSchedule
    weekday_options: tuple[tuple[str, str], ...]
    next_run: str
    last_run: ScheduledRunSummary


def load_scan_schedule(database_path: str | Path) -> ScanSchedule:
    """Load the singleton schedule after ensuring its migration is present."""
    initialize_database(database_path)
    with connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT enabled, run_time, weekdays_json, email_delivery
            FROM scan_schedule
            WHERE singleton_id = 1
            """
        ).fetchone()

    if row is None:
        raise ScheduleError("Junior could not load the scan schedule.")

    try:
        weekdays = tuple(json.loads(row[2]))
    except (TypeError, ValueError):
        weekdays = ()

    return ScanSchedule(
        enabled=bool(row[0]),
        run_time=str(row[1]),
        weekdays=weekdays,
        email_delivery=bool(row[3]),
    )


def save_scan_schedule(
    database_path: str | Path,
    *,
    enabled: bool,
    run_time: str,
    weekdays: list[str],
    email_delivery: bool,
) -> ScanSchedule:
    """Validate and atomically replace the singleton schedule."""
    schedule = _validated_schedule(
        enabled=enabled,
        run_time=run_time,
        weekdays=weekdays,
        email_delivery=email_delivery,
    )
    initialize_database(database_path)
    with connect_database(database_path) as connection:
        connection.execute(
            """
            UPDATE scan_schedule
            SET enabled = ?,
                run_time = ?,
                weekdays_json = ?,
                email_delivery = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE singleton_id = 1
            """,
            (
                int(schedule.enabled),
                schedule.run_time,
                json.dumps(schedule.weekdays),
                int(schedule.email_delivery),
            ),
        )
    return schedule


def build_schedule_view(
    database_path: str | Path,
    *,
    now: datetime | None = None,
) -> ScheduleView:
    schedule = load_scan_schedule(database_path)
    next_run_at = calculate_next_run(schedule, now=now)
    return ScheduleView(
        schedule=schedule,
        weekday_options=WEEKDAYS,
        next_run=(
            _format_local_datetime(next_run_at)
            if next_run_at is not None
            else "Scheduling is off"
        ),
        last_run=_load_last_scheduled_run(database_path),
    )


def calculate_next_run(
    schedule: ScanSchedule,
    *,
    now: datetime | None = None,
) -> datetime | None:
    """Return the next selected local day/time without invoking a scheduler."""
    if not schedule.enabled or not schedule.weekdays:
        return None

    current = now or datetime.now().astimezone()
    local_now = current.astimezone() if current.tzinfo is not None else current
    hour, minute = (int(part) for part in schedule.run_time.split(":"))

    for offset in range(8):
        candidate_date = local_now.date() + timedelta(days=offset)
        weekday_name = WEEKDAYS[candidate_date.weekday()][0]
        if weekday_name not in schedule.weekdays:
            continue
        candidate = datetime.combine(candidate_date, time(hour, minute))
        if local_now.tzinfo is not None:
            candidate = candidate.astimezone()
        if candidate > local_now:
            return candidate
    return None


def _validated_schedule(
    *,
    enabled: bool,
    run_time: str,
    weekdays: list[str],
    email_delivery: bool,
) -> ScanSchedule:
    normalized_time = run_time.strip()
    try:
        parsed_time = time.fromisoformat(normalized_time)
    except ValueError as error:
        raise ScheduleError("Choose a valid scan time.") from error
    if parsed_time.second or parsed_time.microsecond:
        raise ScheduleError("Choose a scan time using hours and minutes.")

    normalized_weekdays = tuple(
        name for name, _label in WEEKDAYS if name in set(weekdays)
    )
    unknown_weekdays = set(weekdays) - set(_WEEKDAY_INDEX)
    if unknown_weekdays:
        raise ScheduleError("Choose only the available weekdays.")
    if enabled and not normalized_weekdays:
        raise ScheduleError(
            "Choose at least one weekday before turning scheduling on."
        )

    return ScanSchedule(
        enabled=enabled,
        run_time=parsed_time.strftime("%H:%M"),
        weekdays=normalized_weekdays,
        email_delivery=email_delivery,
    )


def _load_last_scheduled_run(
    database_path: str | Path,
) -> ScheduledRunSummary:
    with connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT status, finished_at, failure_summary
            FROM scan_runs
            WHERE trigger_source = 'scheduled'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    if row is None:
        return ScheduledRunSummary(
            status="Not run yet",
            tone="neutral",
            finished_at=None,
            message="No scheduled scan has run yet.",
        )

    status = str(row[0])
    finished_at = str(row[1]) if row[1] else None
    if status == "failed":
        return ScheduledRunSummary(
            status="Failed",
            tone="error",
            finished_at=_format_stored_datetime(finished_at),
            message=(
                "The last scheduled scan did not finish. "
                "Open Scan for safe failure details."
            ),
        )
    if status == "running":
        return ScheduledRunSummary(
            status="Running",
            tone="warning",
            finished_at=None,
            message="A scheduled scan is currently running.",
        )
    return ScheduledRunSummary(
        status=(
            "Completed with warnings"
            if status == "completed_with_warnings"
            else "Completed"
        ),
        tone="success" if status == "completed" else "warning",
        finished_at=_format_stored_datetime(finished_at),
        message=(
            "The scan finished with source warnings."
            if status == "completed_with_warnings"
            else "The scheduled scan finished successfully."
        ),
    )


def _format_local_datetime(value: datetime) -> str:
    return value.strftime("%A, %B %d at %I:%M %p").replace(" 0", " ")


def _format_stored_datetime(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return "Time unavailable"
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone()
    return _format_local_datetime(parsed)
