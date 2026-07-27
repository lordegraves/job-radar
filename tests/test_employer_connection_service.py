"""Verify connection tests are bounded, non-importing, and safely reported."""

import sqlite3
from pathlib import Path

import requests

from job_radar.collectors.greenhouse import CollectorError
from job_radar.employer_admin_service import create_employer
from job_radar.employer_admin_service import update_employer
from job_radar.employer_connection_service import (
    get_employer_connection_health,
    record_scan_connection_result,
    test_employer_connection as run_employer_connection_test,
)
from job_radar.models import JobPosting


def _create_test_employer(database_path: Path, **source_config: str) -> str:
    record = create_employer(
        database_path,
        name="Example Kitchens",
        source_type="greenhouse",
        source_config=source_config,
        notes="Fictional test employer.",
    )
    return record.employer.employer_id


def test_connection_success_stores_count_without_importing_jobs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    employer_id = _create_test_employer(
        database_path,
        source_slug="example-kitchens",
    )
    posting = JobPosting(
        company_key=employer_id,
        company_name="Example Kitchens",
        source_type="greenhouse",
        source_job_id="job-1",
        canonical_key="example-kitchens|cook|example",
        title="Cook",
        location="Example City",
        description="Prepare meals.",
        source_url="https://example.invalid/jobs/1",
        content_hash="example-hash",
    )
    received_config = {}

    def collect(config):
        received_config.update(config)
        return [posting]

    monkeypatch.setattr(
        "job_radar.employer_connection_service.collect_jobs_for_company",
        collect,
    )

    result = run_employer_connection_test(database_path, employer_id)

    assert result.state == "success"
    assert result.job_count == 1
    assert result.last_success_at is not None
    assert result.last_error_at is None
    assert result.message == "Connection succeeded and returned 1 job."
    assert received_config["max_pages"] == 1
    assert received_config["connection_test"] is True
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM job_postings"
        ).fetchone()[0] == 0


def test_connection_failure_sanitizes_raw_network_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    employer_id = _create_test_employer(
        database_path,
        source_slug="example-kitchens",
    )
    secret_text = "token=do-not-store"

    def fail(_config):
        request_error = requests.ConnectionError(secret_text)
        raise CollectorError(f"raw failure {secret_text}") from request_error

    monkeypatch.setattr(
        "job_radar.employer_connection_service.collect_jobs_for_company",
        fail,
    )

    result = run_employer_connection_test(database_path, employer_id)

    assert result.state == "error"
    assert result.category == "network"
    assert result.last_error_at is not None
    assert secret_text not in (result.message or "")
    with sqlite3.connect(database_path) as connection:
        stored = connection.execute(
            """
            SELECT last_connection_message
            FROM employer_sources
            WHERE employer_id = ?
            """,
            (employer_id,),
        ).fetchone()[0]
    assert secret_text not in stored


def test_successful_scan_replaces_an_older_connection_failure(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    employer_id = _create_test_employer(
        database_path,
        source_slug="example-kitchens",
    )
    record_scan_connection_result(
        database_path,
        employer_id,
        failure_category="network",
        failure_message="The public source could not be reached.",
    )

    record_scan_connection_result(database_path, employer_id, job_count=14)
    result = get_employer_connection_health(database_path, employer_id)

    assert result.state == "success"
    assert result.job_count == 14
    assert result.message == "Scan succeeded and returned 14 jobs."
    assert result.last_success_at is not None
    assert result.last_error_at is None


def test_configuration_problem_does_not_call_collector(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    employer_id = _create_test_employer(database_path)

    def should_not_run(_config):
        raise AssertionError("collector must not run")

    monkeypatch.setattr(
        "job_radar.employer_connection_service.collect_jobs_for_company",
        should_not_run,
    )

    result = run_employer_connection_test(database_path, employer_id)
    reloaded = get_employer_connection_health(database_path, employer_id)

    assert result.category == "configuration"
    assert reloaded == result


def test_usajobs_missing_local_api_access_has_specific_safe_guidance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    record = create_employer(
        database_path,
        name="Example Federal Agency",
        source_type="usajobs",
        source_config={"organization": "EX"},
        notes="Fictional test agency.",
    )
    monkeypatch.delenv("USAJOBS_USER_AGENT", raising=False)
    monkeypatch.delenv("USAJOBS_AUTHORIZATION_KEY", raising=False)

    result = run_employer_connection_test(
        database_path,
        record.employer.employer_id,
    )

    assert result.state == "error"
    assert result.category == "configuration"
    assert "USAJobs API access is not configured" in (result.message or "")
    assert "USAJOBS_AUTHORIZATION_KEY" not in (result.message or "")


def test_source_edit_clears_stale_connection_health(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "junior.sqlite3"
    employer_id = _create_test_employer(
        database_path,
        source_slug="example-kitchens",
    )
    monkeypatch.setattr(
        "job_radar.employer_connection_service.collect_jobs_for_company",
        lambda config: [],
    )
    run_employer_connection_test(database_path, employer_id)

    update_employer(
        database_path,
        employer_id,
        name="Example Kitchens",
        source_type="greenhouse",
        source_config={"source_slug": "changed-example-kitchens"},
        notes="",
    )

    health = get_employer_connection_health(database_path, employer_id)
    assert health.state == "not_tested"
    assert health.tested_at is None
    assert health.last_success_at is None
