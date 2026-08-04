"""Exercise Junior's durable storage with realistic long-term data volumes.

The validator creates only fictional records in a temporary database. It
measures the profile-owned queries used by normal application pages and removes
the complete temporary workspace when finished.
"""

from __future__ import annotations

import argparse
import sqlite3
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from job_radar.database import connect_database
from job_radar.profile_models import ManagedProfile
from job_radar.profile_storage import create_profile, set_active_profile
from job_radar.storage import (
    fetch_included_job_history_records,
    initialize_database,
)
from job_radar.tracker.tracker_storage import list_applications
from job_radar.web_app import create_app


DEFAULT_COMPANIES = 100
DEFAULT_JOBS = 100_000
DEFAULT_PROFILES = 5
DEFAULT_HISTORY = 10_000
DEFAULT_TRACKER = 2_500
DEFAULT_QUERY_LIMIT_SECONDS = 3.0

T = TypeVar("T")


def _measure(label: str, operation: Callable[[], T]) -> tuple[T, float]:
    started = time.perf_counter()
    result = operation()
    elapsed = time.perf_counter() - started
    print(f"{label}: {elapsed:.3f}s")
    return result, elapsed


def _measure_repeated(
    label: str,
    operation: Callable[[], T],
    *,
    repetitions: int = 10,
) -> tuple[T, float]:
    """Exercise a normal GUI read repeatedly and report its slowest response."""

    result: T | None = None
    elapsed_samples: list[float] = []
    for _ in range(repetitions):
        started = time.perf_counter()
        result = operation()
        elapsed_samples.append(time.perf_counter() - started)
    slowest = max(elapsed_samples)
    average = sum(elapsed_samples) / len(elapsed_samples)
    print(
        f"{label}: average {average:.3f}s; slowest {slowest:.3f}s "
        f"across {repetitions} requests"
    )
    if result is None:
        raise RuntimeError("Repeated scale measurement produced no result.")
    return result, slowest


def _populate_scale_database(
    database_path: Path,
    *,
    companies: int,
    jobs: int,
    profiles: int,
    history: int,
    tracker: int,
) -> None:
    initialize_database(database_path)
    profile_ids = [f"profile_{index:08d}" for index in range(profiles)]

    # Use the real profile service so GUI measurements exercise valid records,
    # not an artificial partial schema that Junior itself could never create.
    for index, profile_id in enumerate(profile_ids):
        create_profile(
            database_path,
            ManagedProfile(
                profile_id=profile_id,
                display_name=f"Fictional Profile {index + 1}",
            ),
        )
    set_active_profile(database_path, profile_ids[0])

    with connect_database(database_path) as connection:
        connection.executemany(
            """
            INSERT INTO companies (
                company_key, name, source_type, enabled
            )
            VALUES (?, ?, 'greenhouse', 1)
            """,
            (
                (
                    f"fictional_company_{index:03d}",
                    f"Fictional Company {index + 1}",
                )
                for index in range(companies)
            ),
        )
        connection.executemany(
            """
            INSERT INTO job_postings (
                company_key,
                source_type,
                source_job_id,
                source_url,
                title,
                location,
                remote_status,
                description,
                canonical_key,
                content_hash,
                first_seen_at,
                last_seen_at
            )
            VALUES (?, 'greenhouse', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    f"fictional_company_{index % companies:03d}",
                    f"source-{index:06d}",
                    f"https://example.invalid/jobs/{index:06d}",
                    f"Fictional Role {index % 250}",
                    f"Fictional City {index % 40}",
                    "remote" if index % 3 == 0 else "onsite",
                    "Fictional responsibilities and qualifications.",
                    f"canonical-{index:06d}",
                    f"hash-{index:06d}",
                    f"{2020 + (index % 6)}-01-01T00:00:00Z",
                    f"{2020 + (index % 6)}-12-31T00:00:00Z",
                )
                for index in range(jobs)
            ),
        )
        connection.executemany(
            """
            INSERT INTO job_history (
                profile_id,
                history_type,
                company,
                role,
                event_date,
                status,
                outcome_category,
                include_in_job_radar,
                import_key,
                notes
            )
            VALUES (?, 'application', ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                (
                    profile_ids[index % profiles],
                    f"Fictional Company {index % companies + 1}",
                    f"Fictional Role {index % 250}",
                    f"{2020 + (index % 6)}-{index % 12 + 1:02d}-15",
                    "Applied" if index % 4 else "Passed",
                    (
                        "Pending / In Progress"
                        if index % 4
                        else "Rejected - No Interview"
                    ),
                    f"history-{index:06d}",
                    "Fictional historical note.",
                )
                for index in range(history)
            ),
        )
        connection.executemany(
            """
            INSERT INTO application_tracker (
                profile_id,
                job_radar_id,
                company_name,
                role_title,
                source_url,
                status,
                outcome,
                notes,
                applied_on,
                last_activity_on
            )
            VALUES (?, ?, ?, ?, ?, 'Applied', ?, ?, ?, ?)
            """,
            (
                (
                    profile_ids[index % profiles],
                    f"jr_scale_{index:06d}",
                    f"Fictional Company {index % companies + 1}",
                    f"Fictional Role {index % 250}",
                    f"https://example.invalid/applications/{index:06d}",
                    "Pending / In Progress",
                    "Fictional active-application note.",
                    f"2026-{index % 12 + 1:02d}-01",
                    f"2026-{index % 12 + 1:02d}-02",
                )
                for index in range(tracker)
            ),
        )


def _query_plan_uses(
    connection: sqlite3.Connection,
    query: str,
    parameters: tuple[object, ...],
    index_name: str,
) -> bool:
    plan = connection.execute(
        f"EXPLAIN QUERY PLAN {query}",
        parameters,
    ).fetchall()
    return any(index_name in str(row) for row in plan)


def run_validation(
    *,
    companies: int = DEFAULT_COMPANIES,
    jobs: int = DEFAULT_JOBS,
    profiles: int = DEFAULT_PROFILES,
    history: int = DEFAULT_HISTORY,
    tracker: int = DEFAULT_TRACKER,
    query_limit_seconds: float = DEFAULT_QUERY_LIMIT_SECONDS,
) -> dict[str, float]:
    if min(companies, jobs, profiles, history, tracker) < 1:
        raise ValueError("Scale validation counts must all be positive.")

    with tempfile.TemporaryDirectory(prefix="junior-scale-") as temporary:
        database_path = Path(temporary) / "job_radar.sqlite3"
        _, population_seconds = _measure(
            "Populate fictional scale database",
            lambda: _populate_scale_database(
                database_path,
                companies=companies,
                jobs=jobs,
                profiles=profiles,
                history=history,
                tracker=tracker,
            ),
        )
        profile_id = "profile_00000000"

        with connect_database(database_path) as connection:
            job_result, job_lookup_seconds = _measure(
                "Locate one job among all stored jobs",
                lambda: connection.execute(
                    """
                    SELECT id, title
                    FROM job_postings
                    WHERE source_type = ? AND source_job_id = ?
                    """,
                    ("greenhouse", f"source-{jobs - 1:06d}"),
                ).fetchone(),
            )
            company_result, company_jobs_seconds = _measure(
                "List one company's active jobs",
                lambda: connection.execute(
                    """
                    SELECT id, title
                    FROM job_postings
                    WHERE company_key = ? AND is_active = 1
                    ORDER BY last_seen_at DESC
                    LIMIT 100
                    """,
                    ("fictional_company_000",),
                ).fetchall(),
            )
            required_plans = (
                (
                    """
                    SELECT job_radar_id
                    FROM application_tracker
                    WHERE profile_id = ?
                    ORDER BY updated_at DESC
                    LIMIT 100
                    """,
                    (profile_id,),
                    "idx_tracker_profile_updated",
                ),
                (
                    """
                    SELECT import_key
                    FROM job_history
                    WHERE profile_id = ? AND include_in_job_radar = 1
                    ORDER BY event_date DESC
                    LIMIT 100
                    """,
                    (profile_id,),
                    "idx_history_profile_included_event",
                ),
                (
                    """
                    SELECT id
                    FROM job_postings
                    WHERE company_key = ? AND is_active = 1
                    ORDER BY last_seen_at DESC
                    LIMIT 100
                    """,
                    ("fictional_company_000",),
                    "idx_job_postings_company_active_seen",
                ),
            )
            for query, parameters, index_name in required_plans:
                if not _query_plan_uses(
                    connection,
                    query,
                    parameters,
                    index_name,
                ):
                    raise RuntimeError(
                        f"SQLite did not use required scale index: {index_name}"
                    )

        history_result, history_seconds = _measure(
            "Load one profile's application history",
            lambda: fetch_included_job_history_records(
                database_path,
                profile_id=profile_id,
            ),
        )
        tracker_result, tracker_seconds = _measure(
            "Load one profile's active applications",
            lambda: list_applications(
                database_path,
                profile_id=profile_id,
            ),
        )

        settings_path = Path(temporary) / "settings.yaml"
        settings_path.write_text(
            "database_path: " + database_path.as_posix() + "\n"
            "reports_path: " + (Path(temporary) / "reports").as_posix() + "\n"
            "logs_path: " + (Path(temporary) / "logs").as_posix() + "\n",
            encoding="utf-8",
        )
        client = create_app(settings_path=str(settings_path)).test_client()

        tracker_page, tracker_page_seconds = _measure_repeated(
            "Render one profile's Active Applications page",
            lambda: client.get("/tracker"),
        )
        history_page, history_page_seconds = _measure_repeated(
            "Render one profile's Application History page",
            lambda: client.get("/history"),
        )

        expected_history = sum(
            1 for index in range(history) if index % profiles == 0
        )
        expected_tracker = sum(
            1 for index in range(tracker) if index % profiles == 0
        )
        if job_result is None or len(company_result) == 0:
            raise RuntimeError("Scale validation could not retrieve stored jobs.")
        if len(history_result) != expected_history:
            raise RuntimeError("Profile-owned history count changed at scale.")
        if len(tracker_result) != expected_tracker:
            raise RuntimeError("Profile-owned tracker count changed at scale.")
        if tracker_page.status_code != 200 or history_page.status_code != 200:
            raise RuntimeError("A profile-owned GUI page failed at scale.")

        timings = {
            "population": population_seconds,
            "job_lookup": job_lookup_seconds,
            "company_jobs": company_jobs_seconds,
            "profile_history": history_seconds,
            "profile_tracker": tracker_seconds,
            "tracker_page": tracker_page_seconds,
            "history_page": history_page_seconds,
        }
        slow_queries = {
            name: elapsed
            for name, elapsed in timings.items()
            if name != "population" and elapsed > query_limit_seconds
        }
        if slow_queries:
            details = ", ".join(
                f"{name}={elapsed:.3f}s"
                for name, elapsed in slow_queries.items()
            )
            raise RuntimeError(
                "Junior exceeded the scale query limit: " + details
            )

        database_size_mib = database_path.stat().st_size / (1024 * 1024)
        print(
            "Scale validation passed: "
            f"{companies} companies, {jobs} jobs, {history} history records, "
            f"{tracker} active applications, {profiles} profiles, "
            f"{database_size_mib:.1f} MiB."
        )
        return timings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate Junior against fictional long-term data volumes."
    )
    parser.add_argument("--companies", type=int, default=DEFAULT_COMPANIES)
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS)
    parser.add_argument("--profiles", type=int, default=DEFAULT_PROFILES)
    parser.add_argument("--history", type=int, default=DEFAULT_HISTORY)
    parser.add_argument("--tracker", type=int, default=DEFAULT_TRACKER)
    parser.add_argument(
        "--query-limit-seconds",
        type=float,
        default=DEFAULT_QUERY_LIMIT_SECONDS,
    )
    arguments = parser.parse_args()
    run_validation(
        companies=arguments.companies,
        jobs=arguments.jobs,
        profiles=arguments.profiles,
        history=arguments.history,
        tracker=arguments.tracker,
        query_limit_seconds=arguments.query_limit_seconds,
    )


if __name__ == "__main__":
    main()
